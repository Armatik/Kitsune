# src/kitsune/netutil.py
# SPDX-License-Identifier: GPL-3.0-or-later

"""HTTP body download with a hard size cap.

Soup's send_and_read buffers the entire response before returning, so a
size check applied to the result cannot prevent memory exhaustion when a
hostile (or compromised) server streams gigabytes. Reading the response
stream in chunks aborts the download as soon as the cap is crossed.
"""

import logging

import gi

gi.require_version('GLib', '2.0')

from gi.repository import GLib

log = logging.getLogger('kitsune.netutil')

MAX_IMAGE_BYTES = 30 * 1024 * 1024

_CHUNK_SIZE = 64 * 1024


def read_stream_capped(stream, max_bytes, cancellable, on_done):
    """Read a GInputStream fully, aborting when `max_bytes` is exceeded.

    `on_done(gbytes, error)` is invoked exactly once: with (GLib.Bytes,
    None) on success, (None, 'too large') when the cap was crossed
    mid-stream, or (None, str(GLib.Error)) on a read failure.
    """
    chunks = []
    total = [0]
    finished = [False]

    def finish(gbytes, error):
        if finished[0]:
            return
        finished[0] = True
        on_done(gbytes, error)

    def on_chunk(stream, result):
        try:
            gbytes = stream.read_bytes_finish(result)
        except GLib.Error as e:
            finish(None, str(e))
            return
        data = gbytes.get_data()
        if not data:
            finish(GLib.Bytes.new(b''.join(chunks)), None)
            return
        total[0] += len(data)
        if total[0] > max_bytes:
            log.warning('aborting download: exceeded %d bytes', max_bytes)
            stream.close_async(GLib.PRIORITY_DEFAULT, None, None, None)
            finish(None, 'too large')
            return
        chunks.append(data)
        read_next()

    def read_next():
        stream.read_bytes_async(
            _CHUNK_SIZE, GLib.PRIORITY_DEFAULT, cancellable, on_chunk)

    read_next()


def send_and_read_capped(session, msg, max_bytes, cancellable, on_done):
    """send_async + read_stream_capped, one terminal on_done call.

    HTTP status is NOT inspected here — callers handle response semantics.
    """
    def on_sent(session, result, _user_data):
        try:
            stream = session.send_finish(result)
        except GLib.Error as e:
            on_done(None, str(e))
            return
        read_stream_capped(stream, max_bytes, cancellable, on_done)

    session.send_async(msg, GLib.PRIORITY_DEFAULT, cancellable, on_sent, None)
