# src/kitsune/auth/token_store.py
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

import keyring
from keyring.errors import KeyringError

log = logging.getLogger('kitsune.auth.token_store')

SERVICE_NAME = 'net.armatik.Kitsune'
ACCOUNT_NAME = 'session'


def save_token(token):
    try:
        keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, token)
    except KeyringError as e:
        log.warning('No keyring backend, token not saved: %s', e)


def load_token():
    try:
        return keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
    except KeyringError as e:
        log.warning('No keyring backend, treating as logged out: %s', e)
        return None


def delete_token():
    try:
        keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
    except KeyringError as e:
        log.debug('Token delete skipped: %s', e)
