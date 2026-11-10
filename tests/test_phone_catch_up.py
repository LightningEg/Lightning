"""3AY6 catch-up (guideline C13, owner decision D3): after days away the long-overdue bills are one question on one
screen, never a wall of red rows; then bank messages, a statement, and Later. It counts the same bills as Home."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.samples import load_mohab_2026
from lightning.ui.phone.router import mount_phone
from lightning.ui.phone.screens import catch_up, home
from lightning.ui.web import create_app


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
        patch.setenv("LIGHTNING_TODAY", "2026-10-11")
        c = build(tmp_path_factory.mktemp("catchup") / "t.db")
        load_mohab_2026(c)
        yield c, patch
        c.db.close()


def _page(c):
    app = create_app(c)
    mount_phone(app)

    async def phone_app(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)
    return TestClient(phone_app)


def test_the_screen_asks_about_exactly_the_bills_home_calls_long_overdue(sample):
    c, _ = sample
    day = date(2026, 10, 11)
    screen = catch_up.build(c, day)
    assert screen.away and screen.bills
    assert len(screen.bills) == home.build(c, day).catch_up.stale_bills      # one bill count (F1)
    assert [b.payment.due_date for b in screen.bills] == sorted(b.payment.due_date for b in screen.bills)


def test_home_leads_to_it_and_each_bill_opens_its_pay_sheet_and_comes_back(sample):
    c, _ = sample
    phone = _page(c)
    opened = phone.get("/home").text
    assert 'href="/catch-up"' in opened                                       # bills fill To do, yet Catch up is one of the three
    assert home.build(c, date(2026, 10, 11)).todo[-1].kind == "catch_up" and len(home.build(c, date(2026, 10, 11)).todo) == 3
    page = phone.get("/catch-up")
    assert page.status_code == 200 and "Did you pay these?" in page.text
    first = catch_up.build(c, date(2026, 10, 11)).bills[0].payment
    assert f'href="/plan/items/{first.item.id}/pay?due={first.due_date}&amp;back=%2Fcatch-up"' in page.text
    assert "is-late" not in page.text and "Late ·" not in page.text          # a question, not red rows (D3)
    assert 'href="/sms"' in page.text and 'href="/import"' in page.text and ">Later<" in page.text


def test_a_profile_that_is_up_to_date_says_so(sample):
    c, patch = sample
    patch.setenv("LIGHTNING_TODAY", "2026-10-04")
    try:
        assert not catch_up.build(c, date(2026, 10, 4)).away
        page = _page(c).get("/catch-up").text
        assert "You are caught up." in page and "Did you pay these?" not in page
    finally:
        patch.setenv("LIGHTNING_TODAY", "2026-10-11")
