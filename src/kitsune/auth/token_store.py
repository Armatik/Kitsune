# src/kitsune/auth/token_store.py
# SPDX-License-Identifier: GPL-3.0-or-later

import gi
gi.require_version('Secret', '1')
from gi.repository import Secret

TOKEN_SCHEMA = Secret.Schema.new(
    'net.armatik.Kitsune.auth',
    Secret.SchemaFlags.NONE,
    {'token-type': Secret.SchemaAttributeType.STRING},
)

_ATTRIBUTES = {'token-type': 'session'}


def save_token(token):
    Secret.password_store_sync(
        TOKEN_SCHEMA,
        _ATTRIBUTES,
        Secret.COLLECTION_DEFAULT,
        'Kitsune AniLibria session',
        token,
        None,
    )


def load_token():
    return Secret.password_lookup_sync(TOKEN_SCHEMA, _ATTRIBUTES, None)


def delete_token():
    Secret.password_clear_sync(TOKEN_SCHEMA, _ATTRIBUTES, None)
