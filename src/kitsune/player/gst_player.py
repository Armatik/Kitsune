# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging

import gi

gi.require_version('Gst', '1.0')
gi.require_version('Gtk', '4.0')

from gi.repository import GLib, GObject, Gst


log = logging.getLogger('kitsune.player')


class GstPlayer(GObject.Object):

    __gsignals__ = {
        'state-changed': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'position-updated': (GObject.SignalFlags.RUN_LAST, None, (int, int)),
        'error': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'eos': (GObject.SignalFlags.RUN_LAST, None, ()),
        'buffering': (GObject.SignalFlags.RUN_LAST, None, (int,)),
    }

    def __init__(self):
        super().__init__()
        self._playbin = Gst.ElementFactory.make('playbin3', 'playbin')
        if self._playbin:
            log.debug('created playbin3')
        else:
            self._playbin = Gst.ElementFactory.make('playbin', 'playbin')
            if self._playbin:
                log.debug('created playbin (fallback)')
            else:
                raise RuntimeError(
                    'GStreamer playbin not available. '
                    'Install gstreamer1.0-plugins-base.'
                )

        self._paintable = None
        self._setup_video_sink()
        self._target_state = Gst.State.NULL
        self._is_buffering = False

        bus = self._playbin.get_bus()
        bus.add_signal_watch()
        self._bus_handler_ids = [
            bus.connect('message::error', self._on_error),
            bus.connect('message::eos', self._on_eos),
            bus.connect('message::state-changed', self._on_state_changed),
            bus.connect('message::buffering', self._on_buffering),
        ]

        self._position_timer = 0
        self._cleaned_up = False

    def _setup_video_sink(self):
        sink = Gst.ElementFactory.make('gtk4paintablesink', 'gtksink')
        if sink:
            self._paintable = sink.get_property('paintable')
            gl_sink = Gst.ElementFactory.make('glsinkbin', 'glsink')
            if gl_sink:
                gl_sink.set_property('sink', sink)
                self._playbin.set_property('video-sink', gl_sink)
                log.debug('video sink: glsinkbin → gtk4paintablesink')
            else:
                self._playbin.set_property('video-sink', sink)
                log.debug('video sink: gtk4paintablesink (no GL)')
        else:
            log.warning('gtk4paintablesink not available')

    @property
    def paintable(self):
        return self._paintable

    def play_uri(self, uri: str):
        if not uri or not uri.startswith(('https://', 'http://')):
            log.error('refusing non-HTTP URI: %s', uri)
            self.emit('error', 'Invalid stream URL')
            return
        log.debug('play_uri: %s', uri)
        self._playbin.set_state(Gst.State.NULL)
        self._playbin.set_property('uri', uri)
        self._target_state = Gst.State.PLAYING
        self._is_buffering = False
        self._playbin.set_state(Gst.State.PLAYING)
        self._start_position_timer()

    def play(self):
        log.debug('play')
        self._target_state = Gst.State.PLAYING
        self._playbin.set_state(Gst.State.PLAYING)
        self._start_position_timer()

    def pause(self):
        log.debug('pause')
        self._target_state = Gst.State.PAUSED
        self._playbin.set_state(Gst.State.PAUSED)
        self._stop_position_timer()

    def stop(self):
        log.debug('stop')
        self._stop_position_timer()
        self._target_state = Gst.State.NULL
        self._is_buffering = False
        self._playbin.set_state(Gst.State.NULL)

    def toggle_play_pause(self):
        _, state, _ = self._playbin.get_state(0)
        if state == Gst.State.PLAYING:
            self.pause()
        else:
            self.play()

    def seek(self, position_seconds: float):
        position_seconds = max(0.0, position_seconds)
        log.debug('seek → %.1fs', position_seconds)
        self._playbin.seek_simple(
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
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
        log.error('pipeline error: %s (debug: %s)', err.message, debug)
        self.emit('error', err.message)
        self.stop()

    def _on_eos(self, _bus, _msg):
        log.debug('eos')
        self.emit('eos')
        self.stop()

    def _on_buffering(self, _bus, msg):
        percent = msg.parse_buffering()
        log.debug('buffering %d%%', percent)
        self.emit('buffering', percent)
        if percent < 100:
            if not self._is_buffering:
                self._is_buffering = True
                log.debug('buffering: pausing pipeline')
                self._playbin.set_state(Gst.State.PAUSED)
        else:
            self._is_buffering = False
            if self._target_state == Gst.State.PLAYING:
                log.debug('buffering done: resuming pipeline')
                self._playbin.set_state(Gst.State.PLAYING)

    def _on_state_changed(self, _bus, msg):
        if msg.src != self._playbin:
            return
        old, new, pending = msg.parse_state_changed()
        state_names = {
            Gst.State.NULL: 'stopped',
            Gst.State.PAUSED: 'paused',
            Gst.State.PLAYING: 'playing',
        }
        sn = state_names.get
        log.debug('state: %s → %s (pending: %s)',
                  sn(old, '?'), sn(new, '?'), sn(pending, 'none'))
        self.emit('state-changed', state_names.get(new, 'unknown'))

    def get_buffered_end(self) -> float:
        try:
            query = Gst.Query.new_buffering(Gst.Format.TIME)
            if not self._playbin.query(query):
                return -1
            n = query.get_n_buffering_ranges()
            max_end = 0
            for i in range(n):
                ok, start, stop = query.parse_nth_buffering_range(i)
                if stop > max_end:
                    max_end = stop
            return max_end / Gst.SECOND if max_end > 0 else -1
        except Exception:
            return -1

    def get_volume(self) -> float:
        return self._playbin.get_property('volume')

    def set_volume(self, volume: float):
        self._playbin.set_property('volume', max(0.0, min(1.0, volume)))

    def cleanup(self):
        if self._cleaned_up:
            return
        self._cleaned_up = True
        log.debug('cleanup')
        bus = self._playbin.get_bus()
        if bus:
            for hid in self._bus_handler_ids:
                bus.disconnect(hid)
            self._bus_handler_ids.clear()
            bus.remove_signal_watch()
        self.stop()
        self._playbin.set_state(Gst.State.NULL)
