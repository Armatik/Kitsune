# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def _atomic_write_json(path: Path, data, *, ensure_ascii: bool = True):
    """Atomically write JSON data to *path* (mkstemp -> write -> replace).

    Handles the fd lifecycle correctly: if os.close succeeds but
    os.replace fails, the fd is not double-closed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    closed = False
    try:
        os.write(fd, json.dumps(data, ensure_ascii=ensure_ascii).encode())
        os.close(fd)
        closed = True
        os.replace(tmp, path)
    except BaseException:
        if not closed:
            os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


from kitsune.storage import release_cache, tags_store, watch_positions  # noqa: E402, F401
