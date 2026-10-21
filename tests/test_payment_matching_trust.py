"""7K: a bill paid from another account links by hand, last month's payment is not offered for this month,
and salary that arrived early is not counted a second time."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from starlette.testclient import TestClient

from lightning.planning.domain import PaymentStatus
from lightning.ui.web import create_app
from lightning.workflows.activity import ActivityReview
from lightning.workflows.review import ReviewInbox

D = Decimal


@pytest.fixture
def client(c):
    return TestClient(create_app(c), base_url="http://127.0.0.1")


def _party(c, name):
    c.counterparties.resolve(name)  # exists once a transaction used it
    return c.counterparties.resolve(name)["id"]


def _payment(c, item_id, due, as_of):
    item = c.planning.get(item_id)
    return next(p for p in c.planning.payments(item, due, as_of) if p.due_date == due)


# ---------------------------------------------------------------- 1. another account
def _vodafone(c, setup):
    accounts, cats = setup
    utilities = c.categories.get_by_code("EXP.PERSONAL.UTILITIES").id
    c.transactions.record_outflow("2026-09-09", accounts["wallet"].id, "350", utilities, counterparty="Vodafone")
    item_id = c.planning.create(kind="SUBSCRIPTION", name="Vodafone", amount="350", frequency="MONTHLY",
                                start_date="2026-09-09", account_id=accounts["wallet"].id, category_id=utilities,
                                counterparty_id=_party(c, "Vodafone"))
    # Paid from CIB, not the wallet the plan names.
    paid = c.transactions.record_outflow("2026-10-12", accounts["cib"].id, "350", utilities, counterparty="Vodafone")
    return item_id, paid


def test_a_bill_paid_from_another_account_links_by_hand_but_never_automatically(c, setup, client):
    item_id, paid = _vodafone(c, setup)
    day = date(2026, 10, 20)
    assert c.planning.match_payments(day) == 1  # September, from the wallet it names
    payment = _payment(c, item_id, "2026-10-09", day)
    assert payment.status == PaymentStatus.DUE
    assert c.planning.candidates(payment, day) == []                # automatic matching stays strict to the account
    assert c.planning.match_payments(day) == 0
    assert [r["id"] for r in c.planning.candidates(payment, day, any_account=True)] == [paid.id]
    # The pay popup offers it, and so does the transaction's own page.
    popup = client.get(f"/plan/items/{item_id}/pay?due=2026-10-09&back=%2Fplan").text
    assert paid.ref in popup
    choices = ActivityReview(c)._planned_choices(c.transactions.get(paid.id))
    assert [(x["item_id"], x["due_date"]) for x in choices] == [(item_id, "2026-10-09")]
    c.planning.mark_paid(item_id, "2026-10-09", paid.id)
    assert _payment(c, item_id, "2026-10-09", day).status == PaymentStatus.PAID
    assert c.planning.what_you_owe(day).bills_due == 0


def test_a_payment_in_another_currency_is_still_not_offered(c, setup):
    accounts, cats = setup
    item_id, _ = _vodafone(c, setup)
    from tests.test_workflow_matching import _usd_account
    usd = _usd_account(c)
    utilities = c.categories.get_by_code("EXP.PERSONAL.UTILITIES").id
    dollars = c.transactions.record_outflow("2026-10-12", usd.id, "350", utilities, counterparty="Vodafone")
    payment = _payment(c, item_id, "2026-10-09", date(2026, 10, 20))
    assert dollars.id not in [r["id"] for r in c.planning.candidates(payment, date(2026, 10, 20), any_account=True)]


# ---------------------------------------------------------------- 2. last month's payment
def _landlord(c, setup, *, start):
    accounts, cats = setup
    housing = cats["EXP.PERSONAL.HOUSING"].id if "EXP.PERSONAL.HOUSING" in cats else \
        c.categories.get_by_code("EXP.PERSONAL.HOUSING").id
    september = c.transactions.record_outflow("2026-09-03", accounts["cib"].id, "12000", housing, counterparty="Landlord")
    item_id = c.planning.create(kind="BILL", name="Landlord", amount="12000", frequency="MONTHLY", start_date=start,
                                account_id=accounts["cib"].id, category_id=housing,
                                counterparty_id=_party(c, "Landlord"))
    return item_id, september, housing


def test_last_months_payment_is_not_offered_for_this_month(c, setup, client):
    item_id, september, _ = _landlord(c, setup, start="2026-10-03")  # newly tracked: its first payment is October's
    day = date(2026, 10, 4)
    october = _payment(c, item_id, "2026-10-03", day)
    assert c.planning.plausible_candidates(october, day) == []
    popup = client.get(f"/plan/items/{item_id}/pay?due=2026-10-03&back=%2Fplan").text
    assert september.ref not in popup and "Possible" not in popup
    assert client.get("/plan/recurring").status_code == 200


def test_a_payment_already_linked_to_another_month_is_not_offered(c, setup):
    item_id, september, _ = _landlord(c, setup, start="2026-09-03")
    day = date(2026, 10, 12)
    c.planning.match_payments(day)
    assert _payment(c, item_id, "2026-09-03", day).transaction_id == september.id
    october = _payment(c, item_id, "2026-10-03", day)
    assert c.planning.plausible_candidates(october, day) == []


def test_a_late_payment_nearer_this_month_and_an_early_salary_are_still_offered(c, setup):
    accounts, cats = setup
    item_id, _, housing = _landlord(c, setup, start="2026-10-03")
    late = c.transactions.record_outflow("2026-10-20", accounts["cib"].id, "12000", housing, counterparty="Landlord")
    day = date(2026, 10, 25)
    assert [r["id"] for r in c.planning.plausible_candidates(_payment(c, item_id, "2026-10-03", day), day)] == [late.id]
    salary = cats["EXP.WORK.SALARY"].id
    early = c.transactions.record_inflow("2026-12-24", accounts["cib"].id, "30000", salary, counterparty="Employer")
    job = c.planning.create(kind="INCOME", name="Salary", amount="30000", frequency="MONTHLY", start_date="2027-01-01",
                            account_id=accounts["cib"].id, category_id=salary, counterparty_id=_party(c, "Employer"))
    january = _payment(c, job, "2027-01-01", date(2027, 1, 1))
    assert [r["id"] for r in c.planning.plausible_candidates(january, date(2027, 1, 1))] == [early.id]


def test_the_popup_no_longer_says_the_other_matches_fit_only_one_detail(c, setup, client):
    accounts, cats = setup
    item_id, _, housing = _landlord(c, setup, start="2026-10-03")
    c.transactions.record_outflow("2026-10-05", accounts["cib"].id, "9000", housing, counterparty="Landlord")
    popup = client.get(f"/plan/items/{item_id}/pay?due=2026-10-03&back=%2Fplan").text
    assert "Other possible matches" in popup
    assert "only one of its category or counterparty" not in popup


# ---------------------------------------------------------------- 3. early salary
def _salary(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-20")
    accounts, cats = setup
    salary = cats["EXP.WORK.SALARY"].id
    for when in ("2026-09-01", "2026-10-01"):
        c.transactions.record_inflow(when, accounts["cib"].id, "45000", salary, counterparty="ACME Egypt")
    item_id = c.planning.create(kind="INCOME", name="ACME Egypt", amount="45000", frequency="MONTHLY",
                                start_date="2026-09-01", account_id=accounts["cib"].id, category_id=salary,
                                counterparty_id=_party(c, "ACME Egypt"))
    c.planning.match_payments(date(2026, 10, 20))
    return item_id, accounts["cib"].id, salary


def test_salary_paid_early_is_not_counted_again_in_the_forecast(c, setup, monkeypatch, client):
    item_id, cib, salary = _salary(c, setup, monkeypatch)
    day = date(2026, 10, 20)
    before = c.forecaster.forecast(day)
    assert c.planning.early_payments(day) == []
    november = before.months[1]
    assert (november.month, november.income) == ("2026-11", D("45000.00")) and before.next_income_date == "2026-11-01"

    paid = c.transactions.record_inflow("2026-10-19", cib, "45000", salary, counterparty="ACME Egypt")  # 12 days early
    [early] = c.planning.early_payments(day)
    assert (early["payment"].due_date, early["transaction"]["id"]) == ("2026-11-01", paid.id)
    after = c.forecaster.forecast(day)
    assert after.months[1].income == 0                       # November's pay is already in the account
    assert after.next_income_date == "2026-12-01"                 # so the next payday is December's
    # The money is in Free cash once; November's closing balance is what it was when the pay was still to come.
    assert after.months[1].closing == before.months[1].closing
    assert after.safe_to_spend < before.safe_to_spend + D("45000.00")  # the 45,000 now has to last until December's payday

    # Needs you offers the link, and one press settles November's payment.
    inbox = [i for i in ReviewInbox(c).items(day) if i["label"].startswith("ACME Egypt")]
    assert len(inbox) == 1 and inbox[0]["action"] == "Link" and inbox[0]["post"]["label"] == "Link this payment"
    fields = inbox[0]["post"]["fields"]
    assert fields["outcome"] == "link" and fields["due"] == "2026-11-01" and fields["transaction_id"] == str(paid.id)
    done = client.post(inbox[0]["post"]["href"], data=fields | {"back": "/review"}, follow_redirects=False)
    assert done.status_code == 303
    assert _payment(c, item_id, "2026-11-01", day).status == PaymentStatus.PAID
    assert c.planning.early_payments(day) == []
    assert c.forecaster.forecast(day).months[1].income == 0
    assert not [i for i in ReviewInbox(c).items(day) if i["label"].startswith("ACME Egypt")]


def test_a_payment_that_is_not_early_or_not_alone_is_still_expected(c, setup, monkeypatch):
    item_id, cib, salary = _salary(c, setup, monkeypatch)
    day = date(2026, 10, 20)
    c.transactions.record_inflow("2026-10-19", cib, "45000", salary, counterparty="ACME Egypt")
    c.transactions.record_inflow("2026-10-19", cib, "45000", salary, counterparty="ACME Egypt")  # two: ambiguous
    assert c.planning.early_payments(day) == []
    assert c.forecaster.forecast(day).months[1].income == D("45000.00")


def test_the_early_payment_entry_reads_in_arabic(c, setup, monkeypatch, client):
    import re
    item_id, cib, salary = _salary(c, setup, monkeypatch)
    c.transactions.record_inflow("2026-10-19", cib, "45000", salary, counterparty="ACME Egypt")
    assert client.post("/settings/locale", data={"locale": "ar"}, follow_redirects=False).status_code == 303
    page = client.get("/review").text
    assert "وصل بدري" in page and "اربطها" in page
    start = page.index("وصل بدري")
    text = re.sub(r"<[^>]+>", " ", page[start - 200:start + 600])
    assert "Link it" not in text and "arrived early" not in text
