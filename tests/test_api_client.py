# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests for the pure-Python helpers in kitsune.api.client.

Does not exercise the Soup HTTP stack — those paths are integration-
tested via FakeApiClient in test_sync_manager.py.
"""

from kitsune.api.client import _parse_success_body


def test_parse_success_body_empty_is_success():
    """AniLibria write endpoints (POST /views/timecodes) return 200 with
    a 0-byte body on success. Must not surface as error — doing so left
    queued ops in-flight forever."""
    data, err = _parse_success_body(b'')
    assert data is None
    assert err is None


def test_parse_success_body_valid_json():
    data, err = _parse_success_body(b'{"ok": 1}')
    assert data == {'ok': 1}
    assert err is None


def test_parse_success_body_valid_json_list():
    data, err = _parse_success_body(b'[1, 2, 3]')
    assert data == [1, 2, 3]
    assert err is None


def test_parse_success_body_malformed_json_is_error():
    """Malformed JSON on 200 must produce an error (not a silent success
    with data=None), otherwise callers would treat garbage as success."""
    data, err = _parse_success_body(b'{not json')
    assert data is None
    assert err is not None
    assert 'invalid JSON' in err


def test_parse_success_body_none_bytes_is_error():
    data, err = _parse_success_body(None)
    assert data is None
    assert err == 'Empty response'


def test_parse_success_body_too_large_is_error():
    huge = b'x' * (10 * 1024 * 1024 + 1)
    data, err = _parse_success_body(huge)
    assert data is None
    assert err == 'Response too large'


def test_expired_handler_fires_on_401_with_auth_header():
    """Requests that carried a Bearer token and got 401 → token rejected,
    the expired handler must fire."""
    from gi.repository import Soup
    from kitsune.api.client import AniLibriaClient

    client = AniLibriaClient()
    fired = []
    client.set_token_expired_handler(lambda: fired.append(True))
    msg = Soup.Message.new('GET', 'https://example.com/accounts/users/me/profile')
    msg.get_request_headers().append('Authorization', 'Bearer abc')
    client._maybe_fire_token_expired(msg, Soup.Status.UNAUTHORIZED)
    assert fired == [True]


def test_expired_handler_fires_on_403_account_endpoint():
    """Live AniLibria answers 403 (not 401) to an expired/invalid token —
    the expired handler must fire for 403 on /accounts/ endpoints too,
    or session expiry is never detected in production."""
    from gi.repository import Soup
    from kitsune.api.client import AniLibriaClient

    client = AniLibriaClient()
    fired = []
    client.set_token_expired_handler(lambda: fired.append(True))
    msg = Soup.Message.new('GET', 'https://example.com/accounts/users/me/profile')
    msg.get_request_headers().append('Authorization', 'Bearer abc')
    client._maybe_fire_token_expired(msg, Soup.Status.FORBIDDEN)
    assert fired == [True]


def test_expired_handler_skipped_on_403_public_endpoint():
    """403 on public /anime/* endpoints is a content block (geo/copyright),
    not a session expiry — even with a token attached."""
    from gi.repository import Soup
    from kitsune.api.client import AniLibriaClient

    client = AniLibriaClient()
    fired = []
    client.set_token_expired_handler(lambda: fired.append(True))
    msg = Soup.Message.new('GET', 'https://example.com/anime/releases/123')
    msg.get_request_headers().append('Authorization', 'Bearer abc')
    client._maybe_fire_token_expired(msg, Soup.Status.FORBIDDEN)
    assert fired == []


def test_expired_handler_skipped_on_401_without_auth_header():
    """Requests without a token (login attempts) getting 401 mean wrong
    credentials, not an expired session — handler must NOT fire."""
    from gi.repository import Soup
    from kitsune.api.client import AniLibriaClient

    client = AniLibriaClient()
    fired = []
    client.set_token_expired_handler(lambda: fired.append(True))
    msg = Soup.Message.new('POST', 'https://example.com/accounts/users/auth/login')
    client._maybe_fire_token_expired(msg, Soup.Status.UNAUTHORIZED)
    assert fired == []


def test_make_callback_parser_exception_becomes_terminal_error():
    """BUG-010: a raising parser must surface as (None, error) — the caller
    must never be left without a terminal callback (infinite spinner)."""
    from kitsune.api.client import _make_callback

    calls = []

    def bad_parser(data):
        raise TypeError('genres: null')

    cb = _make_callback(lambda d, e: calls.append((d, e)), bad_parser)
    cb({'some': 'data'}, None)
    assert len(calls) == 1
    data, err = calls[0]
    assert data is None
    assert 'parse error' in err


def test_make_callback_parser_exception_after_success_path_not_swallowed():
    """Parser receives only successful data; errors bypass the parser."""
    from kitsune.api.client import _make_callback

    calls = []
    cb = _make_callback(lambda d, e: calls.append((d, e)),
                        lambda d: ('parsed', d))
    cb(None, 'timeout')
    assert calls == [(None, 'timeout')]
    cb({'x': 1}, None)
    assert calls[1] == (('parsed', {'x': 1}), None)
