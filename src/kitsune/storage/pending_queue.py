# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from kitsune.storage import _atomic_write_json

log = logging.getLogger('kitsune.pending_queue')

_PENDING_OPS_FILE = Path(
    os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
) / 'kitsune' / 'pending_ops.json'

VERSION = 1

# Retry backoff table (seconds). After 6 failures the interval stays at 600s
# and retries continue indefinitely — ops are never given up on.
BACKOFF_STEPS = [10, 30, 60, 120, 300, 600]

# Truncate error messages to avoid bloating the file
MAX_ERROR_LEN = 200

# Operation kind constants — used instead of an enum for simpler JSON round-trip
OP_ADD_FAVORITE = 'add_favorite'
OP_REMOVE_FAVORITE = 'remove_favorite'
OP_ADD_COLLECTION = 'add_collection'
OP_REMOVE_COLLECTION = 'remove_collection'
OP_SAVE_TIMECODE = 'save_timecode'


@dataclass
class Op:
    id: str
    op: str
    release_id: int
    user_id: int
    payload: dict
    created_at: float
    attempt_count: int = 0
    next_retry_at: float = 0.0
    last_error: str | None = None


class PendingQueue:
    def __init__(self, path: Path | None = None):
        self._path = Path(path) if path is not None else _PENDING_OPS_FILE
        self._ops: list[Op] = []
        self._in_flight: set[str] = set()

    @classmethod
    def load(cls, path: Path | None = None) -> PendingQueue:
        q = cls(path)
        q._load_from_disk()
        return q

    def _load_from_disk(self):
        try:
            raw = json.loads(self._path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            self._ops = []
            return
        if not isinstance(raw, dict) or raw.get('version') != VERSION:
            log.warning(
                'pending_ops.json has unknown format or version, dropping contents'
            )
            self._ops = []
            return
        raw_ops = raw.get('ops', [])
        if not isinstance(raw_ops, list):
            self._ops = []
            return
        self._ops = []
        for op_dict in raw_ops:
            try:
                self._ops.append(Op(**op_dict))
            except TypeError:
                log.warning('Dropping malformed pending op: %s', op_dict)

    def _save(self):
        data = {
            'version': VERSION,
            'ops': [asdict(op) for op in self._ops],
        }
        _atomic_write_json(self._path, data)

    def enqueue(
        self,
        op_kind: str,
        release_id: int,
        user_id: int,
        payload: dict | None = None,
    ) -> str | None:
        """Add a new op to the queue and persist.

        Returns the new op id, or None if the op was coalesced into an
        existing one (coalescing is implemented in a later task).
        """
        if payload is None:
            payload = {}
        new_op = Op(
            id=str(uuid.uuid4()),
            op=op_kind,
            release_id=release_id,
            user_id=user_id,
            payload=dict(payload),
            created_at=time.time(),
        )
        self._ops.append(new_op)
        self._save()
        return new_op.id

    def size(self) -> int:
        return len(self._ops)
