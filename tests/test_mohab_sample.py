"""Mohab's 2026 sample shows every part of Lightning: what ``--sample`` and the welcome page load.

The year test (test_mohab_year.py) does these things through the screens; this file checks the loaded sample
holds one of each, so a screenshot, a demo or a bug hunt on the sample never meets an empty page. When a
feature is added to Lightning, add its sample data (lightning/samples/__init__.py ``_features``) and a line here.
"""
from __future__ import annotations

from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.samples import SAMPLE_TODAY, load_mohab_2026
from lightning.ui.web import create_app

PAGES = ("/", "/budget", "/plan", "/plan/reserves", "/financial-health", "/investments", "/investments/targets",
         "/investments/planner", "/accounts", "/transactions", "/money-from-others", "/zakat", "/reimbursements",
         "/review", "/rules", "/counterparties", "/categories", "/checks", "/settings", "/birdview", "/exports/all")


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_TODAY", SAMPLE_TODAY.isoformat())
        c = build(tmp_path_factory.mktemp("sample") / "s.db")
        load_mohab_2026(c)
        yield c, TestClient(create_app(c))
        c.db.close()


def names(c):
    return {a.name: a for a in c.accounts.list()}


def test_every_kind_of_account_is_there(sample):
    c, _ = sample
    kinds = {a.account_type.value for a in c.accounts.list()}
    assert kinds >= {"BANK", "CASH", "BROKERAGE", "DEPOSIT", "PHYSICAL_ASSET", "OTHER_ASSET", "GAMEYA"}
    assert {a.currency for a in c.accounts.list()} >= {"EGP", "USD"}


def test_goals_big_and_small_two_still_being_saved_for_and_one_paid(sample):
    c, _ = sample
    active = {r["name"] for r in c.reserves.list_active()}
    assert {"Emergency Fund", "Car insurance", "New laptop"} <= active
    assert [r["name"] for r in c.reserves.list_completed()] == ["Sahel trip"]


def test_a_phone_on_the_rule_is_shopping_and_the_bill_is_not(sample):
    c, _ = sample
    assert len(c.rules.list()) == 1
    rows = {abs(D(r["quantity_e6"])) / 1_000_000: r["category"] for r in c.db.all(
        """SELECT le.quantity_e6, cat.name category FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id
           JOIN counterparties cp ON cp.id=t.counterparty_id LEFT JOIN categories cat ON cat.id=le.category_id
           WHERE cp.name='Vodafone' AND le.account_id IS NOT NULL AND t.status='POSTED'""")}
    assert rows[D(12000)] == "Shopping" and rows[D(350)] == "Utilities & Bills"


def test_a_laptop_is_owed_like_a_loan_next_to_the_car(sample):
    c, _ = sample
    loans = {p.name for p in c.planning.items() if p.kind.value == "LOAN"}
    assert loans == {"Car loan", "Laptop instalments"}
    assert c.db.scalar("SELECT COUNT(*) FROM loan_extra_payments") == 1   # 3,000 put against it early


def test_the_gameya_took_its_pot_and_nothing_is_late(sample):
    c, _ = sample
    circle = names(c)["Office gam'eya"]
    progress = c.gameya.progress(circle.id, SAMPLE_TODAY)
    assert (progress.paid, progress.payouts) == (3, 1) and progress.owes_you is False


def test_a_reimbursed_work_expense_is_a_closed_claim(sample):
    c, _ = sample
    (claim,) = c.reimbursements.list_claims()
    assert claim["expected"] == D(1200) and len(claim["receipts"]) == 1


def test_zakat_is_on_with_a_day_and_a_payment(sample):
    c, _ = sample
    assert c.zakat.enabled() and c.zakat.settings().zakat_day == "2026-12-01"
    assert c.zakat.paid_between(SAMPLE_TODAY.replace(month=9, day=1), SAMPLE_TODAY) == D(1000)


def test_mom_holds_money_and_paid_for_groceries(sample):
    c, _ = sample
    assert any(p["name"] == "Mom" for p in c.counterparties.list_people())
    assert c.money_from_others.by_owner(SAMPLE_TODAY.isoformat())


def test_dollars_were_bought_with_pounds_and_a_flat_is_valued(sample):
    c, _ = sample
    assert names(c)["Dollar savings"].currency == "USD" and "Family flat (my share)" in names(c)
    assert c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='CNV' AND status='POSTED'") == 1


def test_investing_has_targets_a_monthly_goal_and_a_saved_report(sample):
    c, _ = sample
    assert set(c.investments.target_weights()) == {"Stocks", "Money Market Fund", "Gold"}
    assert c.settings.get("investment_monthly_goal") == "3000"
    assert [v["name"] for v in c.saved_views.list()] == ["Eid"]


def test_a_statement_is_waiting_for_decisions(sample):
    c, _ = sample
    (batch,) = c.bank_imports.waiting_all()
    assert batch["file_name"] == "vodafone-october.csv" and batch["waiting"] == 3


def test_eid_is_tagged(sample):
    c, _ = sample
    assert c.db.scalar("SELECT COUNT(*) FROM transactions WHERE notes LIKE '%#eid%'") == 4


def test_the_data_checks_pass(sample):
    c, _ = sample
    assert [x.name for x in c.integrity.checks(SAMPLE_TODAY) if x.status != "PASS"] == []


@pytest.mark.parametrize("page", PAGES)
def test_every_page_opens_on_the_sample(sample, page):
    _, client = sample
    assert client.get(page, follow_redirects=True).status_code == 200
