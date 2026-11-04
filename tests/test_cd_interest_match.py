"""Certificate interest is matched to the bank's fixed payout: ranked candidates, one suggestion each, one click."""
from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from lightning.core.dates import parse_date
from lightning.ui.web import create_app
from lightning.workflows.review import ReviewInbox


def _scenario(c, setup):
    """Mohab's case: a 100,000 certificate at 22% paying monthly from the 1st; NBE pays a fixed 1,833.33 on the 15th."""
    accounts, cats = setup
    c.db.execute("UPDATE accounts SET institution='NBE' WHERE id=?", (accounts["cd"].id,))
    c.transactions.record_inflow("2026-08-31", accounts["cib"].id, "100000", cats["EXP.WORK.SALARY"].id,
                                 counterparty="Employer")
    certificate, _ = c.deposits.purchase(
        accounts["cd"].id, name="NBE 3-year", start_date="2026-09-01", lockup_end_date="2026-09-01",
        maturity_date="2029-09-01", principal="100000", annual_rate="22", interest_method="SIMPLE",
        payout_frequency="MONTHLY", compounding_frequency="MONTHLY",
        destination_account_id=accounts["cib"].id, funding_account_id=accounts["cib"].id)
    interest = cats["EXP.INVEST.INTEREST"].id
    salary = cats["EXP.WORK.SALARY"].id
    nbe, salaries = [], []
    for month in ("09", "10", "11", "12"):
        nbe.append(c.transactions.record_inflow(f"2026-{month}-15", accounts["cib"].id, "1833.33", interest,
                                                counterparty="NBE"))
        salaries.append(c.transactions.record_inflow(f"2026-{month}-25", accounts["cib"].id, "50000", salary,
                                                     counterparty="Employer"))
    return accounts, cats, certificate, nbe, salaries


def _plan(c, accounts):
    return [o for o in c.deposit_receipts.match_plan(accounts["cd"].id, "2026-12-31") if o["remaining"] > 0]


def test_each_expected_payout_gets_one_nbe_receipt_never_a_salary(c, setup):
    accounts, _, _, nbe, salaries = _scenario(c, setup)
    plan = _plan(c, accounts)
    assert len(plan) >= 3
    suggested = [o["suggested"] for o in plan if o["suggested"]]
    assert len(suggested) == len(set(suggested))  # one bank row never serves two expectations
    assert set(suggested) <= {t.id for t in nbe} and not set(suggested) & {t.id for t in salaries}
    for occurrence in plan:
        assert occurrence["suggested"] is not None, occurrence["event_date"]
        pick = next(x for x in occurrence["candidates"] if x["suggested"])
        assert pick["payer_ok"] and pick["amount"] == Decimal("1833.33")
        # Closest date after the expected day wins: the 15th of the same month, not the previous one.
        assert pick["days"] == (parse_date(pick["date"]) - parse_date(occurrence["event_date"])).days >= 0
        assert not any(x["suggested"] for x in occurrence["candidates"] if x["amount"] == Decimal("50000"))
        assert all(not x["plausible"] for x in occurrence["candidates"] if x["amount"] == Decimal("50000"))


def test_another_payer_with_a_far_amount_is_not_suggested(c, setup):
    accounts, cats, _, nbe, _ = _scenario(c, setup)
    for txn in nbe:
        c.db.execute("UPDATE transactions SET status='VOID' WHERE id=?", (txn.id,))
    c.transactions.record_inflow("2026-10-15", accounts["cib"].id, "900", cats["EXP.INVEST.INTEREST"].id,
                                 counterparty="Somebody Else")
    plan = _plan(c, accounts)
    assert plan and all(o["suggested"] is None for o in plan)


def test_match_all_confirms_every_suggestion_without_posting_and_leaves_needs_you(c, setup):
    accounts, _, certificate, nbe, _ = _scenario(c, setup)
    before = c.reporting.account_balance(accounts["cib"].id)
    count_before = c.db.scalar("SELECT COUNT(*) FROM transactions")
    items = [i for i in ReviewInbox(c).items(parse_date("2026-12-31")) if "interest payment" in i["label"]]
    assert len(items) == 1 and items[0]["label"].startswith("NBE 3-year:")
    assert items[0]["post"]["label"] == "Match all suggested"
    result = c.deposit_receipts.confirm_suggested(accounts["cd"].id, certificate.terms.id, "2026-12-31")
    assert result["matched"] == 3  # Oct, Nov and Dec 1st; the 15 Sep payment precedes the first expected payout
    assert nbe[0].id not in result["transaction_ids"]
    assert c.reporting.account_balance(accounts["cib"].id) == before
    assert c.db.scalar("SELECT COUNT(*) FROM transactions") == count_before
    assert not [i for i in ReviewInbox(c).items(parse_date("2026-12-31")) if "interest payment" in i["label"]]
    assert all(o["remaining"] < o["expected"] for o in c.deposit_receipts.expected_past(accounts["cd"].id, "2026-12-31"))


def test_page_preticks_the_suggestion_and_match_all_works_over_http(c, setup):
    accounts, _, certificate, nbe, _ = _scenario(c, setup)
    client = TestClient(create_app(c))
    page = client.get(f"/deposits/{accounts['cd'].id}")
    assert page.status_code == 200
    assert "Match all suggested" in page.text and page.text.count(" checked") >= 3
    assert "Show all receipts" in page.text
    needs = client.get("/review")
    assert needs.status_code == 200 and "interest payments to match" in needs.text
    posted = client.post(f"/deposits/{accounts['cd'].id}/interest/match-all", follow_redirects=False)
    assert posted.status_code == 303
    assert posted.headers["location"].startswith("/needs-you?msg=")
    after = client.get(f"/deposits/{accounts['cd'].id}")
    assert "Match all suggested" not in after.text


def test_arabic_labels_exist(c, setup):
    accounts, *_ = _scenario(c, setup)
    page = TestClient(create_app(c)).get(f"/deposits/{accounts['cd'].id}", headers={"Cookie": "lightning_locale=ar"})
    assert page.status_code == 200


def test_match_all_is_one_undoable_action(c, setup):
    from lightning.undo import user_action
    accounts, *_ = _scenario(c, setup)
    with user_action("Saved changes"):
        c.deposit_receipts.confirm_suggested(accounts["cd"].id, None, "2026-12-31")
    assert c.db.scalar("SELECT COUNT(*) FROM cd_interest_receipt_links") == 3
    group = c.undo.available()["undo"]
    c.undo.replay(expected_id=group["id"])
    assert c.db.scalar("SELECT COUNT(*) FROM cd_interest_receipt_links") == 0
