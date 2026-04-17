# src/kitsune/auth/session.py
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from kitsune.auth import token_store


class SessionManager:
    def __init__(self, client):
        self._client = client
        self._token = token_store.load_token()
        self._user = None
        self._device_id = str(uuid.uuid4())
        self._expired = False
        self._on_logged_in = []
        self._on_logged_out = []
        self._on_session_expired = []
        self._on_session_restored = []

        client.set_token_getter(self.get_token)
        if hasattr(client, 'set_token_expired_handler'):
            client.set_token_expired_handler(self._on_token_expired)

    def is_logged_in(self):
        return self._token is not None

    def get_token(self):
        return self._token

    def get_user(self):
        return self._user

    def connect_logged_in(self, callback):
        self._on_logged_in.append(callback)

    def connect_logged_out(self, callback):
        self._on_logged_out.append(callback)

    def is_expired(self):
        return self._expired

    def connect_session_expired(self, callback):
        """callback() — fired when server rejects our token (401)."""
        self._on_session_expired.append(callback)

    def connect_session_restored(self, callback):
        """callback() — fired when expired session is cleared (re-login)."""
        self._on_session_restored.append(callback)

    def _emit_session_expired(self):
        for cb in self._on_session_expired:
            cb()

    def _emit_session_restored(self):
        for cb in self._on_session_restored:
            cb()

    def _on_token_expired(self):
        """Called by ApiClient when the server returns 401.

        Idempotent — repeated 401s during a single expired window only
        emit session-expired once.
        """
        if self._expired:
            return
        self._expired = True
        self._emit_session_expired()

    def clear_expired(self):
        """Reset the expired flag after a successful re-login. No-op
        if the session was never expired."""
        if not self._expired:
            return
        self._expired = False
        self._emit_session_restored()

    def _set_token(self, token):
        self._token = token
        token_store.save_token(token)
        for cb in self._on_logged_in:
            cb()

    def _clear_token(self):
        self._token = None
        self._user = None
        # Logout is terminal: wipe expired flag so a reused SessionManager
        # starts fresh. No session-restored emit — the session is gone,
        # not restored.
        self._expired = False
        token_store.delete_token()
        for cb in self._on_logged_out:
            cb()

    def login_with_credentials(self, login, password, callback=None):
        def on_result(token, error):
            if error or not token:
                if callback:
                    callback(False, error)
                return
            self._set_token(token)
            if callback:
                callback(True, None)
        self._client.login(login, password, on_result)

    def login_with_otp(self, code, device_id, callback=None):
        def on_result(token, error):
            if error or not token:
                if callback:
                    callback(False, error)
                return
            self._set_token(token)
            if callback:
                callback(True, None)
        self._client.login_otp(code, device_id, on_result)

    def start_otp(self, callback=None):
        self._client.get_otp(self._device_id, callback)

    def get_device_id(self):
        return self._device_id

    def start_social_login(self, provider, callback=None):
        self._client.get_social_login_url(provider, callback)

    def poll_social_login(self, state, callback=None):
        def on_result(token, error):
            if error or not token:
                if callback:
                    callback(False, error)
                return
            self._set_token(token)
            if callback:
                callback(True, None)
        self._client.poll_social_auth(state, on_result)

    def logout(self, callback=None):
        def on_result(data, error):
            self._clear_token()
            if callback:
                callback(True, None)
        self._client.logout(on_result)

    def force_logout_cleanup(self):
        """Clear synced local data without calling the server.

        Used by the account-switch path (Stage 7): when re-login brings a
        different user, we must wipe the previous account's synced data
        locally because the token from the OLD session has already been
        rejected (calling server logout would just 401). This is a
        destructive operation — custom (non-builtin) tags are preserved.
        """
        # Local imports to avoid a circular dependency: sync_manager already
        # imports from kitsune.storage, and importing SYNCED_TAGS at module
        # top would create a cycle at startup.
        from kitsune.storage import tags_store, watch_positions, episode_index
        from kitsune.storage.sync_manager import SYNCED_TAGS
        # Clear releases in synced built-in tags (but keep the tags themselves)
        for tag_id in SYNCED_TAGS:
            for rid in list(tags_store.get_release_ids_for_tag(tag_id)):
                tags_store.remove_release(tag_id, rid)
        watch_positions.clear_all()
        episode_index.clear()

    def validate_session(self, callback=None):
        if not self._token:
            if callback:
                callback(False, None)
            return
        def on_profile(user, error):
            if error:
                self._clear_token()
                if callback:
                    callback(False, error)
                return
            self._user = user
            if callback:
                callback(True, None)
        self._client.get_profile(on_profile)

    def fetch_profile(self, callback=None):
        def on_profile(user, error):
            if error:
                if callback:
                    callback(None, error)
                return
            self._user = user
            if callback:
                callback(user, None)
        self._client.get_profile(on_profile)
