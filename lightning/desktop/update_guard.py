"""When an update must not start (NF-9B3): a borrowed profile is on this PC, or a journal move-home is unfinished.

Reason: ai/ARCHITECTURE and issues NF-4B "Compatibility and updates": swapping the program while a phone's ledger is lent
to this PC, or while a home is moving, could strand data. `PREFETCHED`, `HANDED_BACK` and `ABORTED` are fine.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from lightning.sync.state import BorrowerState

BLOCKING = frozenset({BorrowerState.BORROW_PREPARED, BorrowerState.BORROWING, BorrowerState.SEALED,
                      BorrowerState.RETURNING, BorrowerState.NEEDS_REPAIR})


@dataclass(frozen=True)
class Refusal:
    kind: str            # "lend" or "move"
    names: tuple[str, ...]  # profile names, for the sentence "Hand <name> back to your phone first"


def _name(folder: Path) -> str:
    try:
        return json.loads((folder / "profile.json").read_text(encoding="utf-8"))["name"]
    except (OSError, ValueError, KeyError, TypeError):
        return "a borrowed profile"


def refusals(devices, profiles_root: Path | None, borrowed_root: Path | None = None) -> list[Refusal]:
    """`devices`: the app's `Devices` (its `borrowed()` list). `profiles_root`: the folder holding the profile folders.
    `borrowed_root`: `<app data>/borrowed`; a borrowed folder `devices` cannot read (a damaged control store) is
    treated as lent, never skipped: guessing "fine" there could strand a phone's data."""
    found = []
    try:
        borrowed = devices.borrowed()
    except Exception:  # a damaged control store: nothing can be trusted to be idle
        borrowed = []
    lent = [b.name for b in borrowed if b.state in BLOCKING]
    if borrowed_root is not None and borrowed_root.is_dir():
        readable = {b.profile_id for b in borrowed}
        lent += [_name(p.parent) for p in sorted(borrowed_root.glob("*/profile.json")) if p.parent.name not in readable]
    if lent:
        found.append(Refusal("lend", tuple(lent)))
    if profiles_root is not None and profiles_root.is_dir():
        moving = tuple(sorted(p.name for p in profiles_root.iterdir()
                              if (p / ".journal-move" / "client.state").exists()))
        if moving:
            found.append(Refusal("move", moving))
    return found
