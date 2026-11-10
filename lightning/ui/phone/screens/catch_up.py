"""Catch up (IV-3AY6, guideline C13; owner decision D3, 2026-11-06): after days away, one question instead of a wall of
red rows. In order: the bills that went long overdue ("Did you pay these?": a tap opens that bill's pay sheet; what is
left stays here, not on Home's list), then bank messages, then a statement, then Later. The bills are the one bill
state's late-and-stale rows, so Home's To do row, the Bills page and this screen count the same ones."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from lightning.planning import bill_state
from lightning.planning.bill_state import BillRow, BillState


@dataclass(frozen=True)
class CatchUpScreen:
    away: bool                   # False: nothing to catch up on, the screen says so and leads back Home
    days: int | None             # days since anything was recorded; None on a profile with no entries
    last_entry: str              # the day of the last recording, "" when there is none
    bills: tuple[BillRow, ...]   # long overdue, oldest first
    has_sms: bool                # this phone can read bank messages itself (else the row says Paste)


def build(c, day: date, has_sms: bool = False) -> CatchUpScreen:
    rows = bill_state.unpaid_bills(c.planning, day)
    away = bill_state.catch_up(c, day, rows)
    stale = tuple(sorted((r for r in rows if r.state == BillState.LATE_STALE), key=lambda r: r.payment.due_date))
    return CatchUpScreen(away=away.away, days=away.days_since_entry, last_entry=away.last_entry or "", bills=stale,
                         has_sms=has_sms)
