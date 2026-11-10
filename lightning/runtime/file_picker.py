"""The Windows Open dialog for "Choose a backup file…" (IT-2C3).

The desktop window registers a picker while it runs; browser mode and the phone never do, so the route that uses it
answers 404 there. Python opens the dialog itself: no page script reaches native code (the window keeps
``js_api=None``)."""
from __future__ import annotations

import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

Picker = Callable[[], "str | None"]

_lock = threading.Lock()
_picker: Picker | None = None
PICKED_SUFFIX = "_picked.db"


def register(picker: Picker | None) -> None:
    """Set (or, with None, remove) the process's picker."""
    global _picker
    with _lock:
        _picker = picker


def current() -> Picker | None:
    with _lock:
        return _picker


def copy_into_backups(chosen: str | Path, backups_dir: Path, database: Path) -> Path:
    """Copy a picked file into the profile's backups folder under a name ``list_backups`` accepts.
    The original is only read. Raises ValueError for anything that is not a plain, non-empty file."""
    source = Path(chosen)
    if source.is_symlink() or not source.is_file() or source.stat().st_size == 0:
        raise ValueError("not a backup file")
    backups_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target = backups_dir / f"{database.stem}_backup_{day}_999_{uuid4().hex[:8]}{PICKED_SUFFIX}"
    partial = target.with_name(f".{target.name}.partial")
    try:
        with source.open("rb") as reader, open(partial, "xb") as writer:
            shutil.copyfileobj(reader, writer, 1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    return target
