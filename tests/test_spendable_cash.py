"""Cash kept apart (audit 2026-10-15): brokerage and foreign-currency cash leave Free cash and Safe to spend by
default, stay in what you own and If you sold today, and the person can change it per account."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def _fund_thndr(c, accounts):
    c.transactions.record_transfer("2026-09-05", accounts["cib"].id, accounts["thndr"].id, "3000")


def test_brokerage_cash_is_kept_apart_by_default(c, setup):
    accounts, _ = setup
    _fund_thndr(c, accounts)
    p = c.position.at(date(2026, 9, 30))
    assert p.brokerage_cash == Decimal("3000") and p.kept_apart == Decimal("3000")
    assert p.cash_you_own == p.spendable_cash + p.kept_apart
    assert p.free_cash == p.cash_you_own - Decimal("3000") - p.reserves - p.bills_due
    assert p.if_you_sold_today == p.free_cash + p.kept_apart + p.holdings_after_sale
    assert c.reporting.owned_spendable_cash("2026-09-30") == p.spendable_cash
    assert c.reporting.owned_cash_kept_apart_by_account("2026-09-30") == [
        {"id": accounts["thndr"].id, "label": "THNDR", "currency": "EGP", "value": Decimal("3000")}]


def test_the_person_can_count_a_brokerage_or_set_a_bank_apart(c, setup):
    accounts, _ = setup
    _fund_thndr(c, accounts)
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    reply = client.post(f"/accounts/{accounts['thndr'].id}/spendable", data={"spendable": "yes"},
                        follow_redirects=False)
    assert reply.status_code == 303
    assert c.accounts.get(accounts["thndr"].id).spendable is True
    p = c.position.at(date(2026, 9, 30))
    assert p.kept_apart == 0 and p.free_cash == p.cash_you_own - p.reserves - p.bills_due

    client.post(f"/accounts/{accounts['wallet'].id}/spendable", data={"spendable": "no"})
    assert c.position.at(date(2026, 9, 30)).kept_apart == Decimal("1200")
    # Choosing the default again stores no override.
    client.post(f"/accounts/{accounts['wallet'].id}/spendable", data={"spendable": "yes"})
    assert c.accounts.get(accounts["wallet"].id).spendable is None


def test_overview_names_what_is_kept_apart_and_the_check_still_adds_up(c, setup):
    accounts, _ = setup
    _fund_thndr(c, accounts)
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    page = client.get("/").text
    assert "Kept apart" in page and "−3,000" in page
    account_page = client.get(f"/accounts/{accounts['thndr'].id}").text
    assert "Count its cash as spendable" in account_page
    checks = client.get("/checks").text
    assert "Free cash matches the ledger" in checks
