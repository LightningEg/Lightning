"""BV-7AY: comparable monthly totals and a complete category-less bill payment."""
import re
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from lightning.planning.calendar import month_calendar
from lightning.ui.web import create_app
from tests.test_upcoming_calendar import _household
from test_journal_finance import devices  # noqa: F401


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-11")


def test_equal_months_include_gameya_and_exclude_its_payout(c):
    bank, _ = _household(c)
    circle = c.account_flows.open_account("Office", "GAMEYA", "2026-09-01", "0")
    c.gameya.save_terms(circle.id, organiser="Um Ali", members=10, installment="2000", first_date="2026-09-05",
                        my_turn=3, funding_account_id=bank.id, payout_account_id=bank.id)
    cal = month_calendar(c.planning, c.gameya, "2026-11", date(2026, 11, 11))
    assert cal.month_total == cal.last_month_total == Decimal("17150")
    text = TestClient(create_app(c)).get("/plan/upcoming").text
    assert "The same as October" in text


def test_recurring_sentence_uses_bills_share_without_the_loan(c):
    _household(c)
    text = TestClient(create_app(c)).get("/plan/recurring").text
    assert "Your bills take 12,650 a month, 28% of your income." in text


def test_category_less_bill_can_be_paid_from_catch_up_and_failure_rolls_back(c):
    bank = c.account_flows.open_account("Wallet", "CASH", "2026-09-01", "1000")
    item = c.planning.create(kind="BILL", name="Old bill", amount="100", frequency="ONCE",
                             start_date="2026-11-01", account_id=bank.id)
    category = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    client = TestClient(create_app(c))
    step = client.get("/plan/catch-up").text
    pay_url = re.search(r'class="btn primary" href="([^"]+)"', step).group(1).replace("&amp;", "&")
    query = parse_qs(urlsplit(pay_url).query)
    assert 'name="category_id"' in client.get(pay_url).text
    data = {"due": query["due"][0], "back": query["back"][0], "outcome": "record",
            "date_paid": "2026-11-11", "amount": "-1", "account_id": str(bank.id), "category_id": str(category)}
    failed = client.post(f"/plan/items/{item}/pay", data=data)
    assert failed.text.count("Enter the amount paid.") == 1
    assert c.planning.get(item).category_id is None
    data["amount"] = "100"
    result = client.post(f"/plan/items/{item}/pay", data=data)
    assert "catch-up-summary" in result.text and "Marked paid" in result.text
    assert c.planning.get(item).category_id == category
    payment = c.planning.payments(c.planning.get(item), "2026-11-11")[0]
    assert not payment.outstanding and payment.transaction_id
    assert c.reporting.account_balance(bank.id, date(2026, 11, 11)) == Decimal("900")
    assert 'name="category_id"' not in client.get(pay_url).text


def test_category_less_bill_payment_on_a_journal_home(devices):
    from lightning.sync.journal.proxy import JournalServices
    from tests.test_journal_screens import Screen

    home, _ = devices
    services = JournalServices(home)
    bank = next(a for a in home.c.accounts.list() if a.name == "Bank")
    item = services.planning.create(kind="BILL", name="Old bill", amount="100", frequency="ONCE",
                                    start_date="2026-11-01", account_id=bank.id, interval_count=1,
                                    notes="", weekend_move="none")
    category = home.c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    response = Screen(home).post(f"/plan/items/{item}/pay", data={
        "due": "2026-11-01", "back": "/plan/catch-up", "outcome": "record", "date_paid": "2026-11-11",
        "amount": "100", "account_id": str(bank.id), "category_id": str(category)})
    assert response.status_code == 303
    assert home.c.planning.get(item).category_id == category
    assert not home.c.planning.payments(home.c.planning.get(item), "2026-11-11")[0].outstanding
