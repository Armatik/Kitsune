# tests/test_session.py
# SPDX-License-Identifier: GPL-3.0-or-later

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unittest.mock import patch, MagicMock
from kitsune.auth.session import SessionManager


class FakeClient:
    def set_token_getter(self, getter):
        self._token_getter = getter

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
