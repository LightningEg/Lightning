"""Link the sections (NF-7T): what a transaction touched, a counterparty's page, what depends on an account,
and a tag's totals. Only stored links are read; nothing new is stored."""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_TODAY", "2026-10-02")
        patch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
        c = build(tmp_path_factory.mktemp("linked") / "t.db")
        load_mohab_2026(c)
        yield c, TestClient(create_app(c))
        c.db.close()


def _paid_plan_txn(c, kind):
    row = c.db.one("SELECT p.transaction_id FROM planned_payments p JOIN planned_items i ON i.id=p.planned_item_id "
                   "WHERE p.transaction_id IS NOT NULL AND i.kind=? ORDER BY p.due_date LIMIT 1", (kind,))
    return int(row["transaction_id"])


# ------------------------------------------------------------------ 7T1
def test_a_transaction_gathers_its_budget_line_bill_source_and_claim(sample):
    c, _ = sample
    loan_txn = _paid_plan_txn(c, "LOAN")
    touched = c.linked.transaction(loan_txn)
    assert [link["name"] for link in touched["settled"]] == ["Car loan"]
    assert touched["settled"][0]["href"] == "/plan/loans"
    assert touched["sources"] and touched["sources"][0]["file_name"].endswith(".csv")
    assert touched["budget"] and touched["budget"][0]["month"] == c.transactions.get(loan_txn).date[:7]

    claim = c.reimbursements.list_claims()[0]
    with_claim = c.linked.transaction(claim["expense_id"])
    assert [(row["id"], row["role"]) for row in with_claim["claims"]] == [(claim["id"], "expense")]
    for receipt in claim["receipts"]:
        assert [row["role"] for row in c.linked.transaction(receipt["receipt_id"])["claims"]] == ["receipt"]


def test_a_transaction_shows_the_rule_that_files_it_only_while_it_still_does(sample):
    c, _ = sample
    row = c.db.one("SELECT t.id, le.category_id FROM transactions t JOIN ledger_entries le ON le.transaction_id=t.id "
                   "WHERE t.counterparty='Talabat' AND t.status='POSTED' AND le.category_id IS NOT NULL LIMIT 1")
    assert c.linked.transaction(row["id"])["rule"] is None
    with c.db.transaction():
        rule_id = c.rules.save({"counterparty": "Talabat", "category_id": str(row["category_id"])})
    try:
        rule = c.linked.transaction(row["id"])["rule"]
        assert rule["id"] == rule_id and "Talabat" in rule["when"]
    finally:
        with c.db.transaction():
            c.rules.delete(rule_id)


def test_one_transaction_page_holds_the_review_and_old_activity_links_land_on_it(sample):
    c, client = sample
    claim = c.reimbursements.list_claims()[0]
    page = client.get(f"/transactions/{claim['expense_id']}")
    assert page.status_code == 200
    assert "What this touched" in page.text and 'href="/reimbursements"' in page.text
    assert 'id="activity-review"' in page.text  # the suggested links once on /activity/{id}
    moved = client.get(f"/activity/{claim['expense_id']}", follow_redirects=False)
    assert moved.status_code == 303 and moved.headers["location"] == f"/transactions/{claim['expense_id']}"
    assert 'href="/transactions/' in client.get("/activity").text
    assert client.get("/activity/999999", follow_redirects=False).headers["location"].startswith("/activity")


def test_a_reserve_link_is_shown_once_with_its_remove_button(sample):
    c, client = sample
    link = c.db.one("SELECT transaction_id, reserve_id FROM reserve_transaction_links LIMIT 1")
    page = client.get(f"/transactions/{link['transaction_id']}").text
    assert page.count(f'href="/reserves/{link["reserve_id"]}/payments"') == 1
    assert page.count('name="action" value="unlink"') == 1


@pytest.mark.parametrize("phone", [False, True], ids=["pc", "phone"])
def test_the_panel_renders_in_the_phone_frame_too(sample, phone):
    c, _ = sample
    app = create_app(c)
    if phone:
        inner = app

        async def app(scope, receive, send):
            if scope["type"] == "http":
                scope.setdefault("state", {})["phone"] = True
            await inner(scope, receive, send)
    page = TestClient(app).get(f"/transactions/{_paid_plan_txn(c, 'LOAN')}").text
    assert ('class="phone-row linked-row"' if phone else 'class="compact-row linked-row"') in page


# ------------------------------------------------------------------ 7T2
def test_a_counterparty_page_gathers_money_by_month_plans_claims_and_money_held(sample):
    c, _ = sample
    employer = c.linked.counterparty(1)
    assert employer["side"] == "money_in" and len(employer["months"]) == 12
    assert employer["total"] == sum(row["money_in"] for row in employer["months"])
    assert {plan["name"] for plan in employer["plans"]} == {"ACME Egypt", "Year-end bonus"}
    assert [claim["payer_id"] for claim in employer["claims"]] == [1]
    mom = c.linked.counterparty(13)
    assert mom["side"] == "money_out" and mom["held"][0]["amount"] == Decimal("6900.00")
    uber = c.linked.counterparty(14)
    spent = c.reporting.spending_by_counterparty("2025-11-01", "2026-10-02")
    assert uber["money_out"] == dict(spent)["Uber"]  # the same rule as Expense analysis


def test_a_counterparty_page_lists_the_rules_that_look_at_its_names(sample):
    c, _ = sample
    rules = c.linked.counterparty(20)["rules"]  # the sample's Vodafone rule
    assert rules and "Vodafone" in rules[0]["when"]


def test_the_counterparty_page_opens_from_the_list_and_the_transaction(sample):
    c, client = sample
    assert 'href="/counterparties/14"' in client.get("/counterparties").text
    page = client.get("/counterparties/14")
    assert page.status_code == 200 and "Money out to them" in page.text
    txn = c.db.scalar("SELECT id FROM transactions WHERE counterparty_id=14 AND status='POSTED' LIMIT 1")
    assert 'href="/counterparties/14"' in client.get(f"/transactions/{txn}").text
    assert client.get("/counterparties/999999", follow_redirects=False).headers["location"].startswith("/counterparties")


# ------------------------------------------------------------------ 7T3
def test_an_account_lists_what_depends_on_it_and_deactivating_warns_first(sample):
    c, client = sample
    payroll = c.linked.account(1)
    assert {"Landlord", "Car loan", "ACME Egypt"} <= {plan["name"] for plan in payroll["plans"]}
    assert [plan["amount"] for plan in payroll["plans"]] == sorted((p["amount"] for p in payroll["plans"]), reverse=True)
    assert [circle["name"] for circle in payroll["circles"]] == ["Office gam'eya"]
    assert payroll["certificates"] and payroll["count"] >= 10
    assert c.linked.account(2)["count"] == 0
    page = client.get("/accounts/3").text
    assert 'id="account-depends"' in page and "Vodafone" in page
    assert "still use this account" in page  # the Deactivate button asks first
    assert 'id="account-depends"' not in client.get("/accounts/2").text  # nothing depends: the section is left out


def test_the_first_day_an_account_goes_below_zero_comes_from_the_dated_forecast(sample):
    c, _ = sample
    with c.db.transaction():
        item_id = c.planning.create(kind="BILL", name="Big bill", amount="900000", frequency="ONCE",
                                    start_date="2026-10-20", account_id=3)
    try:
        shortfall = c.linked.account(3)["shortfall"]
        assert shortfall is not None and shortfall.date == "2026-10-20" and shortfall.balance < 0
    finally:
        with c.db.transaction():
            c.planning.remove(item_id)


# ------------------------------------------------------------------ 7T4
def test_a_tag_has_one_total_across_categories_and_accounts(sample):
    c, client = sample
    page = c.linked.tag("#Eid")
    ids = c.transactions.tag_transaction_ids("eid")
    assert page["count"] == len(ids) and (page["money_in"], page["money_out"]) == c.reporting.money_in_out(ids)
    assert sum(row["money_out"] for row in page["categories"]) == page["money_out"]
    assert sum(row["money_out"] for row in page["accounts"]) == page["money_out"]
    assert page["reserves"] == []
    html = client.get("/tags/eid").text
    assert "Its transactions" in html and 'href="/transactions?tag=eid"' in html
    assert 'href="/tags/eid"' in client.get("/transactions?tag=eid").text  # reachable where the tag is shown
    assert 'href="/tags/eid"' in client.get(f"/transactions/{min(ids)}").text


def test_a_reserve_named_like_the_tag_is_compared_with_it(sample):
    c, client = sample
    with c.db.transaction():
        reserve = c.reserves.create("Eid", "10000")
    try:
        page = c.linked.tag("eid")
        assert [r["name"] for r in page["reserves"]] == ["Eid"]
        assert page["reserves"][0]["left_after"] == Decimal("10000") - page["money_out"]
        assert "of the 10,000 target for Eid" in client.get("/tags/eid").text
    finally:
        with c.db.transaction():
            c.reserves.delete(reserve["id"])


def test_four_names_then_other():
    from lightning.workflows.linked import _four_then_other
    rows = {i: {"name": str(i), "money_out": Decimal(i)} for i in range(1, 8)}
    shown = _four_then_other(rows)
    assert [row["name"] for row in shown] == ["7", "6", "5", "4", "Other"] and shown[-1]["money_out"] == Decimal(6)
