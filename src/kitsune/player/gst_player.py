# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gst', '1.0')
gi.require_version('Gtk', '4.0')

from gi.repository import GLib, GObject, Gst


class GstPlayer(GObject.Object):

    __gsignals__ = {
        'state-changed': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'position-updated': (GObject.SignalFlags.RUN_LAST, None, (int, int)),
        'error': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'eos': (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self):
        super().__init__()
        self._playbin = Gst.ElementFactory.make('playbin3', 'playbin')
        if not self._playbin:
            self._playbin = Gst.ElementFactory.make('playbin', 'playbin')

        self._paintable = None
        self._setup_video_sink()

        bus = self._playbin.get_bus()
        bus.add_signal_watch()
        bus.connect('message::error', self._on_error)
        bus.connect('message::eos', self._on_eos)
        bus.connect('message::state-changed', self._on_state_changed)

        self._position_timer = 0

    def _setup_video_sink(self):
        sink = Gst.ElementFactory.make('gtk4paintablesink', 'gtksink')
        if sink:
            self._paintable = sink.get_property('paintable')
            gl_sink = Gst.ElementFactory.make('glsinkbin', 'glsink')
            if gl_sink:
                gl_sink.set_property('sink', sink)
                self._playbin.set_property('video-sink', gl_sink)
            else:
                self._playbin.set_property('video-sink', sink)

    @property
    def paintable(self):
        return self._paintable

    def play_uri(self, uri: str):
        self._playbin.set_state(Gst.State.NULL)
        self._playbin.set_property('uri', uri)
        self._playbin.set_state(Gst.State.PLAYING)
        self._start_position_timer()

    def play(self):
        self._playbin.set_state(Gst.State.PLAYING)
        self._start_position_timer()

    def pause(self):
        self._playbin.set_state(Gst.State.PAUSED)
        self._stop_position_timer()

    def stop(self):
        self._stop_position_timer()
        self._playbin.set_state(Gst.State.NULL)

    def toggle_play_pause(self):
        _, state, _ = self._playbin.get_state(0)
        if state == Gst.State.PLAYING:
            self.pause()
        else:
            self.play()

    def seek(self, position_seconds: float):
        self._playbin.seek_simple(
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
            int(position_seconds * Gst.SECOND),
        )

    def get_position(self) -> float:
        ok, pos = self._playbin.query_position(Gst.Format.TIME)
        return pos / Gst.SECOND if ok else 0

    def get_duration(self) -> float:
        ok, dur = self._playbin.query_duration(Gst.Format.TIME)
        return dur / Gst.SECOND if ok else 0

    @property
    def is_playing(self) -> bool:
        _, state, _ = self._playbin.get_state(0)
        return state == Gst.State.PLAYING

    def _start_position_timer(self):
        if not self._position_timer:
            self._position_timer = GLib.timeout_add(500, self._update_position)

    def _stop_position_timer(self):
        if self._position_timer:
            GLib.source_remove(self._position_timer)
            self._position_timer = 0

    def _update_position(self):
        pos = self.get_position()
        dur = self.get_duration()
        self.emit('position-updated', int(pos), int(dur))
        return GLib.SOURCE_CONTINUE

    def _on_error(self, _bus, msg):
        err, debug = msg.parse_error()
        self.emit('error', err.message)
        self.stop()

    def _on_eos(self, _bus, _msg):
        self.emit('eos')
        self.stop()

    def _on_state_changed(self, _bus, msg):
        if msg.src != self._playbin:
            return
        _old, new, _pending = msg.parse_state_changed()
        state_names = {
            Gst.State.NULL: 'stopped',
            Gst.State.PAUSED: 'paused',
            Gst.State.PLAYING: 'playing',
        }
        self.emit('state-changed', state_names.get(new, 'unknown'))

    def cleanup(self):
        self.stop()
        self._playbin.set_state(Gst.State.NULL)
