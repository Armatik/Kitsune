# tests/test_netutil.py
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gi.repository import Gio, GLib

from kitsune.netutil import read_stream_capped


def _drain(done):
    ctx = GLib.MainContext.default()
    while not done:
        ctx.iteration(True)


def test_assembles_small_body():
    payload = b'{"hello": "world"}' * 100
    stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(payload))
    done = []
    read_stream_capped(stream, 10 * 1024 * 1024, None,
                       lambda gbytes, err: done.append((gbytes, err)))
    _drain(done)
    gbytes, err = done[0]
    assert err is None
    assert gbytes.get_data() == payload


def test_empty_body_is_empty_bytes_not_error():
    stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(b''))
    done = []
    read_stream_capped(stream, 1024, None,
                       lambda gbytes, err: done.append((gbytes, err)))
    _drain(done)
    gbytes, err = done[0]
    assert err is None
    assert gbytes.get_data() == b''


def test_aborts_mid_stream_when_cap_exceeded():
    """SEC-005: the download must abort as soon as the cap is crossed —
    not after the whole hostile body is buffered in memory."""
    payload = b'x' * (1024 * 1024)
    stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(payload))
    done = []
    read_stream_capped(stream, 100 * 1024, None,
                       lambda gbytes, err: done.append((gbytes, err)))
    _drain(done)
    gbytes, err = done[0]
    assert gbytes is None
    assert err == 'too large'


def test_exact_cap_is_accepted():
    payload = b'y' * (100 * 1024)
    stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(payload))
    done = []
    read_stream_capped(stream, 100 * 1024, None,
                       lambda gbytes, err: done.append((gbytes, err)))
    _drain(done)
    gbytes, err = done[0]
    assert err is None
    assert gbytes.get_data() == payload


def test_on_done_called_exactly_once():
    payload = b'z' * (300 * 1024)
    stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(payload))
    done = []
    read_stream_capped(stream, 1024, None,
                       lambda gbytes, err: done.append((gbytes, err)))
    _drain(done)
    assert len(done) == 1


class _FakeSession:
    """Mimics libsoup3's send_async callback contract: (session, result,
    user_data) — the arity a real Soup.Session invokes with."""

    def __init__(self, payload):
        self._stream = Gio.MemoryInputStream.new_from_bytes(
            GLib.Bytes.new(payload))

    def send_async(self, msg, prio, cancellable, callback, *user_data):
        callback(self, 'fake-result', *user_data)

    def send_finish(self, result):
        return self._stream


def test_send_and_read_capped_full_send_path():
    """Regression: send_async callbacks must accept (session, result,
    user_data) — a 2-arg callback dies with TypeError on a real session."""
    from kitsune.netutil import send_and_read_capped

    payload = b'{"ok": 1}'
    done = []
    send_and_read_capped(_FakeSession(payload), None, 1024, None,
                         lambda g, e: done.append((g, e)))
    _drain(done)
    gbytes, err = done[0]
    assert err is None
    assert gbytes.get_data() == payload


class _ErrorStream:
    def __init__(self, error):
        self._error = error

    def read_bytes_async(self, count, prio, cancellable, callback):
        GLib.idle_add(lambda: callback(self, 'result'))

    def read_bytes_finish(self, result):
        raise self._error

    def close_async(self, *args):
        pass


def test_glib_error_passed_through_as_object():
    """Callers must be able to match CANCELLED against the raw GLib.Error
    — stringifying it in netutil would make that impossible."""
    err = GLib.Error.new_literal(
        Gio.io_error_quark(), 'Operation was cancelled',
        Gio.IOErrorEnum.CANCELLED)
    done = []
    read_stream_capped(_ErrorStream(err), 1024, None,
                       lambda g, e: done.append((g, e)))
    _drain(done)
    gbytes, e = done[0]
    assert gbytes is None
    assert e is err
    assert e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED)
