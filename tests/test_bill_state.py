"""3AY5: one bill state. On Mohab's year, and on the same profile a week and three weeks later with nothing recorded,
what the screens count agrees: What you owe, Needs you, More's next 14 days and the forecast's "before payday"."""
from __future__ import annotations

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.core.figures import label
from lightning.planning import bill_state as bs
from lightning.samples import load_mohab_2026
from lightning.ui.routes import dashboard
from lightning.ui.web import create_app
from lightning.workflows.review import ReviewInbox

DAYS = ("2026-10-04", "2026-10-11", "2026-10-25")


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
        patch.setenv("LIGHTNING_TODAY", DAYS[0])
        c = build(tmp_path_factory.mktemp("bills") / "t.db")
        load_mohab_2026(c)
        yield c, patch
        c.db.close()


@pytest.mark.parametrize("today", DAYS)
def test_every_surface_reads_the_same_bills(sample, today):
    c, patch = sample
    patch.setenv("LIGHTNING_TODAY", today)
    day = date.fromisoformat(today)
    rows = bs.open_bills(c.planning, day, 60)
    # What you owe: everything due today or late.
    owed = {(r.payment.item.id, r.due_date) for r in rows if r.due_date <= today}
    assert owed == {(p.item.id, p.due_date) for p in c.planning.what_you_owe(day).bills_due_items}
    # Needs you: late, stale or due within three days.
    soon = dashboard._due_soon(c)
    wanted = [r for r in rows if r.state in bs.NEEDS_ACTION]
    assert (soon["count"] if soon else 0) == len(wanted)
    # The forecast's "payments before next income": the rows after today and before the next income.
    inbox = ReviewInbox(c)
    inbox.items(day)
    nxt = bs.next_income_date(c.planning, day)
    before = [r for r in rows if r.due_date > today and nxt and r.due_date < nxt]
    total = sum(c.planning.amount_in_base(r.payment, r.payment.still_owed, day) for r in before)
    assert dict(inbox.forecast.safe_to_spend_parts)[label("payments_before_next_income")] == -total
    # More: the next 14 days, five shown and the rest counted.
    inner = create_app(c)

    async def phone(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await inner(scope, receive, send)
    html = TestClient(phone).get("/more").text
    shown = len(re.findall(r"class=.phone-row phone-hub-bill[ \"]", html))
    more = re.search(r">(\d+) more<", html)
    fortnight = bs.open_bills(c.planning, day, 14)
    assert shown + (int(more.group(1)) if more else 0) == len(fortnight)


def test_a_week_with_nothing_recorded_is_the_catch_up_state(sample):
    c, patch = sample
    patch.setenv("LIGHTNING_TODAY", DAYS[0])
    assert not bs.catch_up(c, date.fromisoformat(DAYS[0])).stale_bills
    patch.setenv("LIGHTNING_TODAY", DAYS[1])
    week = bs.catch_up(c, date.fromisoformat(DAYS[1]))
    assert week.stale_bills >= 1 and week.away


def test_states_follow_their_definitions(sample):
    c, _ = sample
    day = date.fromisoformat(DAYS[1])
    by_state = {r.state for r in bs.open_bills(c.planning, day, 60)}
    assert {bs.BillState.LATE, bs.BillState.LATE_STALE, bs.BillState.DUE_SOON, bs.BillState.BEFORE_PAYDAY} <= by_state
    for r in bs.open_bills(c.planning, day, 60):
        assert (r.state == bs.BillState.LATE_STALE) == bool(r.late_days > bs.STALE_DAYS or
                                                            (r.late_days and r.due_date < bs.last_income_date(c.planning, day)))
