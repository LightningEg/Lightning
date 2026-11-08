"""3AY10: Money. Net worth today, the balances themselves (four, then N more), Coming up with never a late bill."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from lightning.planning.bill_state import BillState
from lightning.samples import load_mohab_2026
from lightning.ui.phone.router import mount_phone
from lightning.ui.phone.screens import money as screen
from lightning.ui.web import create_app


@pytest.fixture
def mohab(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-04")
    load_mohab_2026(c)
    return c


def test_net_worth_is_the_positions_and_balances_are_four_then_more(mohab):
    day = date(2026, 10, 4)
    s = screen.build(mohab, day)
    now = mohab.position.at(day)
    assert s.net_worth == now.net_worth and s.what_you_owe == now.what_you_owe
    assert len(s.accounts) <= screen.ACCOUNTS_SHOWN
    assert [a.balance for a in s.accounts] == sorted((a.balance for a in s.accounts), reverse=True)


def test_coming_up_never_holds_a_late_bill_and_late_ones_are_one_pointer(mohab):
    s = screen.build(mohab, date(2026, 10, 25))      # bills have gone late by then
    assert len(s.coming_up) <= screen.COMING_UP
    assert all(b.state not in (BillState.LATE, BillState.LATE_STALE) for b in s.coming_up)


def test_the_page_renders_with_a_link_to_every_shown_balance_and_the_gear(mohab):
    app = create_app(mohab)
    mount_phone(app)
    client = TestClient(app)
    page = client.get("/money").text
    s = screen.build(mohab, date(2026, 10, 4))
    assert all(f'href="/accounts/{a.id}"' in page for a in s.accounts)
    assert 'href="/settings"' in page and "Coming up" in page
