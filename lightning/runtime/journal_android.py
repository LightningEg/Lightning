"""Bridge Android background requests to the unlocked journal runtime's owning event loop.

Android may call this from a JobService thread, but the journal session and SQLite connection belong to the
phone server's event-loop thread. The registry never opens profiles or unlocks them by itself.
"""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Awaitable, Callable

_guard = threading.RLock()
_active: dict[str, tuple[object, asyncio.AbstractEventLoop, Callable[[], Awaitable[str]]]] = {}


def _key(files_dir) -> str:
    return str(Path(files_dir).expanduser().resolve())


def register(files_dir, runtime, loop: asyncio.AbstractEventLoop,
             synchronize: Callable[[], Awaitable[str]]) -> None:
    """Expose one already-unlocked phone runtime to Android's scheduled sync hook."""
    if loop.is_closed():
        raise RuntimeError("cannot register journal sync on a closed event loop")
    with _guard:
        _active[_key(files_dir)] = (runtime, loop, synchronize)


def unregister(files_dir, runtime) -> None:
    """Remove the runtime only if this exact session still owns the registration."""
    with _guard:
        key = _key(files_dir)
        current = _active.get(key)
        if current is not None and current[0] is runtime:
            del _active[key]


async def sync_once(files_dir) -> str:
    """Catch up on the session's own loop; a locked or closed profile is never opened here."""
    with _guard:
        entry = _active.get(_key(files_dir))
    if entry is None:
        return "locked"

    _runtime, loop, synchronize = entry
    if loop.is_closed() or not loop.is_running():
        return "locked"

    try:
        if asyncio.get_running_loop() is loop:
            result = await synchronize()
        else:
            pending = asyncio.run_coroutine_threadsafe(synchronize(), loop)
            result = await asyncio.wrap_future(pending)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - the native scheduler will retry on the next network window
        return "offline"

    return result if result in {"synced", "idle", "offline", "locked", "syncing"} else "offline"
