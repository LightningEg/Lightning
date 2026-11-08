"""NF-3AZ6: Can I afford this? on the chosen account and date: plan fit and account balance side by side, named basis."""
from __future__ import annotations

from decimal import Decimal as D

from fastapi.testclient import TestClient

from lightning.planning.afford import account_check
from lightning.ui.web import create_app

SERIES = (("2026-11-01", ((1, D(5000)),)), ("2026-11-10", ((1, D(1000)),)), ("2026-11-25", ((1, D(9000)),)))


def test_balance_is_the_last_point_on_or_before_the_date():
    answer = account_check(SERIES, 1, "2026-11-05", D(2000), "CIB")
    assert answer.balance_on == D(5000) and answer.after == D(3000)
    assert answer.enough is False and answer.short_on == "2026-11-10"       # rent day takes it below zero later
    assert answer.lowest_after == D(-1000)


def test_a_later_date_after_payday_is_enough():
    answer = account_check(SERIES, 1, "2026-11-25", D(2000), "CIB")
    assert answer.balance_on == D(9000) and answer.enough and answer.short_on is None


def test_an_account_with_nothing_recorded_is_unknown_not_zero():
    assert account_check(SERIES, 2, "2026-11-05", D(10), "Wallet").balance_on is None


def test_the_page_names_the_account_the_date_and_the_basis(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-01")
    accounts, cats = setup
    cib = accounts["cib"]
    c.planning.create(kind="BILL", name="Rent", amount="3000", frequency="ONCE", start_date="2026-11-10",
                      account_id=cib.id, category_id=cats["EXP.PERSONAL.FOOD"].id)
    count = c.db.scalar("SELECT count(*) FROM transactions")
    page = TestClient(create_app(c)).get(f"/plan?afford=2000&afford_account={cib.id}&afford_date=2026-11-12")
    assert "Fits your plan" in page.text and cib.name in page.text and "2026-11-12" in page.text
    assert "Basis: posted cash plus bills" in page.text and "Nothing is recorded until you save it" in page.text
    assert f"/accounts/{cib.id}/transaction/new?" in page.text
    assert c.db.scalar("SELECT count(*) FROM transactions") == count        # asking records nothing
