# tests/test_token_store.py
# SPDX-License-Identifier: GPL-3.0-or-later

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unittest.mock import patch, MagicMock
from kitsune.auth import token_store


def test_save_and_load_token():
    with patch.object(token_store, 'Secret', create=True) as mock_secret:
        mock_secret.password_store_sync = MagicMock()
        mock_secret.password_lookup_sync = MagicMock(return_value='test-token-123')

        token_store.save_token('test-token-123')
        mock_secret.password_store_sync.assert_called_once()

        token = token_store.load_token()
        assert token == 'test-token-123'


def test_load_token_none():
    with patch.object(token_store, 'Secret', create=True) as mock_secret:
        mock_secret.password_lookup_sync = MagicMock(return_value=None)
        assert token_store.load_token() is None


def test_delete_token():
    with patch.object(token_store, 'Secret', create=True) as mock_secret:
        mock_secret.password_clear_sync = MagicMock(return_value=True)
        token_store.delete_token()
        mock_secret.password_clear_sync.assert_called_once()


def test_schema_attributes():
    assert token_store.TOKEN_SCHEMA is not None
