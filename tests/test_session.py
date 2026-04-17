# tests/test_session.py
# SPDX-License-Identifier: GPL-3.0-or-later

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from unittest.mock import patch, MagicMock
from kitsune.auth.session import SessionManager


class FakeClient:
    def __init__(self):
        self._token_getter = None
        self._token_expired_handler = None

    def set_token_getter(self, getter):
        self._token_getter = getter

    def set_token_expired_handler(self, handler):
        self._token_expired_handler = handler

    def login(self, login, password, callback=None):
        if login == 'good' and password == 'pass':
            callback('token-abc', None)
        else:
            callback(None, 'HTTP 401')

    def logout(self, callback=None):
        callback({'token': None}, None)

    def get_profile(self, callback=None):
        callback(MagicMock(id=1, nickname='Test'), None)

    def get_otp(self, device_id, callback=None):
        callback({'otp': {'code': '058701'}, 'remaining_time': 120}, None)

    def login_otp(self, code, device_id, callback=None):
        if code == 58701:
            callback('token-otp', None)
        else:
            callback(None, 'HTTP 404')


@patch('kitsune.auth.session.token_store')
def test_login_success(mock_store):
    mock_store.load_token.return_value = None
    sm = SessionManager(FakeClient())
    results = []
    sm.login_with_credentials('good', 'pass', lambda ok, err: results.append((ok, err)))
    assert results[0] == (True, None)
    mock_store.save_token.assert_called_with('token-abc')
    assert sm.is_logged_in()


@patch('kitsune.auth.session.token_store')
def test_login_failure(mock_store):
    mock_store.load_token.return_value = None
    sm = SessionManager(FakeClient())
    results = []
    sm.login_with_credentials('bad', 'bad', lambda ok, err: results.append((ok, err)))
    assert results[0] == (False, 'HTTP 401')
    assert not sm.is_logged_in()


@patch('kitsune.auth.session.token_store')
def test_logout(mock_store):
    mock_store.load_token.return_value = 'existing-token'
    sm = SessionManager(FakeClient())
    sm.logout(lambda ok, err: None)
    mock_store.delete_token.assert_called_once()
    assert not sm.is_logged_in()


@patch('kitsune.auth.session.token_store')
def test_restore_session(mock_store):
    mock_store.load_token.return_value = 'saved-token'
    sm = SessionManager(FakeClient())
    assert sm.is_logged_in()
    assert sm.get_token() == 'saved-token'


@patch('kitsune.auth.session.token_store')
def test_no_saved_token(mock_store):
    mock_store.load_token.return_value = None
    sm = SessionManager(FakeClient())
    assert not sm.is_logged_in()


@patch('kitsune.auth.session.token_store')
def test_otp_login(mock_store):
    mock_store.load_token.return_value = None
    sm = SessionManager(FakeClient())
    results = []
    sm.login_with_otp(58701, 'device-1', lambda ok, err: results.append((ok, err)))
    assert results[0] == (True, None)
    mock_store.save_token.assert_called_with('token-otp')


# --- Stage 6: expired state ---

@pytest.fixture
def client_stub():
    """FakeClient instance with token_store patched to return None."""
    with patch('kitsune.auth.session.token_store') as mock_store:
        mock_store.load_token.return_value = None
        yield FakeClient()


def test_is_expired_false_by_default(client_stub):
    from kitsune.auth.session import SessionManager
    sm = SessionManager(client_stub)
    assert sm.is_expired() is False


def test_on_token_expired_sets_flag(client_stub):
    from kitsune.auth.session import SessionManager
    sm = SessionManager(client_stub)
    sm._on_token_expired()
    assert sm.is_expired() is True


def test_on_token_expired_is_idempotent(client_stub):
    from kitsune.auth.session import SessionManager
    sm = SessionManager(client_stub)
    emitted = []
    sm.connect_session_expired(lambda: emitted.append(True))
    sm._on_token_expired()
    sm._on_token_expired()
    sm._on_token_expired()
    assert len(emitted) == 1
    assert sm.is_expired() is True


def test_clear_expired_resets_flag_and_emits_restored(client_stub):
    from kitsune.auth.session import SessionManager
    sm = SessionManager(client_stub)
    emitted = []
    sm.connect_session_restored(lambda: emitted.append(True))
    sm._on_token_expired()
    sm.clear_expired()
    assert sm.is_expired() is False
    assert emitted == [True]


def test_clear_expired_noop_when_not_expired(client_stub):
    from kitsune.auth.session import SessionManager
    sm = SessionManager(client_stub)
    emitted = []
    sm.connect_session_restored(lambda: emitted.append(True))
    sm.clear_expired()
    assert sm.is_expired() is False
    assert emitted == []


def test_is_logged_in_still_true_when_expired(client_stub):
    from kitsune.auth.session import SessionManager
    sm = SessionManager(client_stub)
    sm._token = 'some-token'
    sm._on_token_expired()
    assert sm.is_logged_in() is True
    assert sm.is_expired() is True


def test_session_registers_token_expired_handler_with_client(client_stub):
    from kitsune.auth.session import SessionManager
    sm = SessionManager(client_stub)
    assert sm.is_expired() is False
    assert client_stub._token_expired_handler is not None
    client_stub._token_expired_handler()
    assert sm.is_expired() is True


def test_clear_token_wipes_expired_flag(client_stub):
    """Logout wipes the expired flag so a reused SessionManager starts fresh.

    This is a latent-bug regression test: without clearing _expired on
    logout, a reused SessionManager would report is_expired()=True after
    a subsequent fresh login until something explicitly cleared the flag.
    """
    from kitsune.auth.session import SessionManager
    sm = SessionManager(client_stub)
    sm._token = 'some-token'
    sm._on_token_expired()
    assert sm.is_expired() is True
    # Simulate logout via _clear_token
    restored_events = []
    sm.connect_session_restored(lambda: restored_events.append(True))
    sm._clear_token()
    assert sm.is_expired() is False
    # Logout is terminal — no session-restored emit
    assert restored_events == []


def test_force_logout_cleanup_clears_synced_tags(client_stub, mock_tags):
    """Synced tags (favorites, watching, etc.) are cleared; custom tags stay."""
    from kitsune.auth.session import SessionManager
    from kitsune.storage import tags_store
    tags_store.add_release('favorites', 9275)
    tags_store.add_release('watching', 9276)
    tags_store.create_tag('Custom', 'emoji', '🔥')
    custom_id = [t['id'] for t in tags_store.get_all_tags()
                 if not t.get('builtin')][0]
    tags_store.add_release(custom_id, 8888)

    sm = SessionManager(client_stub)
    sm.force_logout_cleanup()

    assert tags_store.get_release_ids_for_tag('favorites') == []
    assert tags_store.get_release_ids_for_tag('watching') == []
    # Custom tag preserved
    assert 8888 in tags_store.get_release_ids_for_tag(custom_id)


def test_force_logout_cleanup_clears_watch_positions(
        client_stub, monkeypatch, tmp_path):
    from kitsune.auth.session import SessionManager
    from kitsune.storage import watch_positions
    wp_file = tmp_path / 'wp.json'
    monkeypatch.setattr(watch_positions, '_POSITIONS_FILE', wp_file)
    watch_positions.save_position(9275, 1.0, 60.0, episode_id='ep.0')
    assert wp_file.exists()

    sm = SessionManager(client_stub)
    sm.force_logout_cleanup()

    assert not wp_file.exists()


def test_force_logout_cleanup_clears_episode_index(
        client_stub, monkeypatch, tmp_path):
    from kitsune.auth.session import SessionManager
    from kitsune.storage import episode_index
    idx_file = tmp_path / 'idx.json'
    monkeypatch.setattr(episode_index, '_INDEX_FILE', idx_file)
    monkeypatch.setattr(episode_index, '_cache', None)
    episode_index.add_from_release_data(
        9275, {'episodes': [{'id': 'ep.0', 'ordinal': 1.0}]})
    assert idx_file.exists()

    sm = SessionManager(client_stub)
    sm.force_logout_cleanup()

    assert not idx_file.exists()


def test_force_logout_cleanup_does_not_call_server_logout(client_stub):
    """force_logout_cleanup must NOT call client.logout() — the token
    is already rejected, a server logout call would just 401."""
    from kitsune.auth.session import SessionManager
    calls = []

    # Extend the stub with a logout method that records calls
    original_cls = type(client_stub)

    class InstrumentedStub(original_cls):
        def logout(self, callback=None):
            calls.append('logout')
            if callback:
                callback(None, None)

    stub = InstrumentedStub()
    sm = SessionManager(stub)
    sm.force_logout_cleanup()
    assert calls == []


# --- Stage 6 post-review coverage ---

def test_concurrent_401_storm_emits_session_expired_once(client_stub):
    """Three rapid 401s (e.g. _sync_favorites, _sync_collections,
    pull_timecodes all failing in startup validation) must coalesce
    into exactly ONE session-expired emit."""
    from kitsune.auth.session import SessionManager
    sm = SessionManager(client_stub)
    emitted = []
    sm.connect_session_expired(lambda: emitted.append(True))
    # Three 401s as would arrive from concurrent in-flight requests
    client_stub._token_expired_handler()
    client_stub._token_expired_handler()
    client_stub._token_expired_handler()
    assert len(emitted) == 1
    assert sm.is_expired() is True


def test_expired_to_restored_chain_fires_session_restored(client_stub):
    """End-to-end restore chain: _on_token_expired → clear_expired →
    session-restored subscribers fire. Stage 7's auth_dialog will drive
    this chain after successful re-login."""
    from kitsune.auth.session import SessionManager
    sm = SessionManager(client_stub)
    expired_events = []
    restored_events = []
    sm.connect_session_expired(lambda: expired_events.append(True))
    sm.connect_session_restored(lambda: restored_events.append(True))
    # Simulate: server 401
    client_stub._token_expired_handler()
    assert expired_events == [True]
    assert restored_events == []
    # Simulate: successful re-login by the same user
    sm.clear_expired()
    assert restored_events == [True]
    assert sm.is_expired() is False


def test_logged_out_during_401_flow_leaves_clean_state(client_stub):
    """Startup 401 scenario: validate_session fails, _clear_token fires
    logged_out. Expired flag must be False after logged_out so any
    future login starts fresh."""
    from kitsune.auth.session import SessionManager
    sm = SessionManager(client_stub)
    sm._token = 'expiring-token'
    logged_out_events = []
    sm.connect_logged_out(lambda: logged_out_events.append(True))
    # Server returns 401 on the validation request
    client_stub._token_expired_handler()
    assert sm.is_expired() is True
    # Then validate_session's error callback runs _clear_token
    sm._clear_token()
    # Logged out → expired flag wiped → any subsequent fresh login
    # starts clean
    assert sm.is_expired() is False
    assert sm.is_logged_in() is False
    assert logged_out_events == [True]
