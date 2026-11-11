"""NF-7AR: the Upcoming tab puts the month's payments on a calendar, with what is left to pay leading."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.planning.calendar import month_calendar
from lightning.ui.web import create_app

D = Decimal
TODAY = date(2026, 11, 11)


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", TODAY.isoformat())


def _household(c, opening="50000"):
    bank = c.account_flows.open_account("CIB Current", "BANK", "2026-09-01", opening, institution="CIB")
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    ids = {
        "rent": c.planning.create(kind="BILL", name="Rent", amount="12000", frequency="MONTHLY",
                                  start_date="2026-09-03", account_id=bank.id, category_id=food),
        "internet": c.planning.create(kind="BILL", name="Internet", amount="650", frequency="MONTHLY",
                                      start_date="2026-09-20", account_id=bank.id),
        "loan": c.planning.create(kind="LOAN", name="Car loan", amount="2500", frequency="MONTHLY",
                                  start_date="2026-08-05", payment_count=24, account_id=bank.id),
        "salary": c.planning.create(kind="INCOME", name="Salary", amount="45000", frequency="MONTHLY",
                                    start_date="2026-09-01", account_id=bank.id),
    }
    c.planning.record_payment(ids["rent"], "2026-11-03", "2026-11-03", "12000", bank.id)
    return bank, ids


def test_the_month_lists_each_payment_with_its_state_and_the_totals(c):
    _, ids = _household(c)
    cal = month_calendar(c.planning, c.gameya, "2026-11", TODAY)
    rows = {(e.name, e.date): e for e in cal.entries}
    assert rows[("Rent", "2026-11-03")].state == "paid"
    loan = rows[("Car loan", "2026-11-05")]
    assert (loan.state, loan.group, loan.number, loan.of, loan.left) == ("late", "instalments", 4, 24, D("2500"))
    assert rows[("Internet", "2026-11-20")].state == "upcoming"
    assert rows[("Salary", "2026-11-01")].incoming and rows[("Salary", "2026-11-01")].group == "income"
    # Left to pay counts the late loan and the coming bill; Already paid is the rent; income is never a payment.
    assert (cal.left_to_pay, cal.already_paid, cal.month_total) == (D("3150"), D("12000"), D("15150"))
    assert cal.last_month_total == D("15150")       # October: rent, internet, loan
    assert cal.money_in == D("45000") and cal.paydays == ("2026-11-01",)
    assert cal.groups == ("bills", "instalments", "income")
    assert all(e.date[:7] == "2026-11" for e in cal.entries)


def test_a_gameya_circle_shows_its_instalment_and_payout(c):
    bank, _ = _household(c)
    circle = c.account_flows.open_account("Office", "GAMEYA", "2026-09-01", "0")
    c.gameya.save_terms(circle.id, organiser="Um Ali", members=10, installment="2000", first_date="2026-09-05",
                        my_turn=3, funding_account_id=bank.id, payout_account_id=bank.id)
    cal = month_calendar(c.planning, c.gameya, "2026-11", TODAY)
    circle_rows = [e for e in cal.entries if e.group == "gameya"]
    assert {(e.incoming, e.amount, e.number, e.of) for e in circle_rows} == {
        (False, D("2000"), 3, 10), (True, D("20000"), 3, 10)}
    assert cal.left_to_pay == D("5150")             # the instalment joins what is left to pay; the payout does not
    assert "gameya" in cal.groups


def test_the_first_short_day_is_marked_when_it_falls_in_the_month(c):
    bank = c.account_flows.open_account("Wallet", "CASH", "2026-09-01", "1000")
    c.planning.create(kind="BILL", name="Course", amount="5000", frequency="ONCE", start_date="2026-11-20",
                      account_id=bank.id)
    cal = month_calendar(c.planning, c.gameya, "2026-11", TODAY, c.forecaster)
    assert cal.short_on == "2026-11-20" and cal.short_by == D("4000")
    assert month_calendar(c.planning, c.gameya, "2026-10", TODAY, c.forecaster).short_on is None


def test_an_empty_month_has_no_entries_and_nothing_to_pay(c):
    cal = month_calendar(c.planning, c.gameya, "2026-11", TODAY, c.forecaster)
    assert cal.entries == () and cal.left_to_pay == 0 and cal.groups == ()


def test_the_page_leads_with_left_to_pay_and_a_day_opens_its_pay_sheet(c):
    _, ids = _household(c)
    client = TestClient(create_app(c))
    page = client.get("/plan/upcoming")
    assert page.status_code == 200
    text = page.text
    assert "Left to pay in November" in text and "3,150" in text
    assert "12,000 paid" in text and "of 15,150 due in November" in text
    assert 'href="/plan/upcoming"' in text                     # its tab in Cash planning
    # The day list opens on the late loan, the first day that still asks for money, and links to its pay sheet.
    assert f"/plan/items/{ids['loan']}/pay?due=2026-11-05&amp;back=/plan/upcoming%3Fmonth%3D2026-11%26day%3D2026-11-05" in text
    assert text.count('role="gridcell"') == 30
    assert "is-payday" in text and "Payday" in text
    day_list = lambda q: client.get("/plan/upcoming?month=2026-11&" + q).text.split('id="upcoming-day"')[1]
    assert "Car loan" in day_list("day=2026-11-05&show=instalments")
    assert "Rent" in day_list("day=2026-11-03") and "Rent" not in day_list("day=2026-11-03&show=instalments")


def test_month_steps_and_a_bad_month_falls_back_to_this_month(c):
    _household(c)
    client = TestClient(create_app(c))
    december = client.get("/plan/upcoming?month=2026-12").text
    assert "?month=2026-11" in december and "?month=2027-01" in december and "This month" in december
    assert client.get("/plan/upcoming?month=nonsense").status_code == 200


def test_an_empty_profile_gets_a_first_step(c):
    text = TestClient(create_app(c)).get("/plan/upcoming").text
    assert "Nothing is planned for this month" in text and "Left to pay in" not in text


def _phone_client(c):
    app = create_app(c)

    async def phone(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)
    return TestClient(phone)


def test_the_phone_shows_two_weeks_from_today_and_opens_on_the_late_loan(c):
    _, ids = _household(c)
    text = _phone_client(c).get("/plan/upcoming?month=2027-03&show=bills").text   # month and chips do not apply
    assert "Left to pay in November" in text and "3,150" in text
    assert text.count('class="phone-strip-day') == 14 and 'href="/plan/upcoming?day=2026-11-24"' in text
    assert 'href="/plan/upcoming?day=2026-11-25"' not in text
    assert f'/plan/items/{ids["loan"]}/pay?due=2026-11-05' in text and "upcoming-chips" not in text
    assert "Internet" in _phone_client(c).get("/plan/upcoming?day=2026-11-20").text.split('id="upcoming-day"')[1]


def test_the_phone_strip_reaches_into_next_month(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-25")
    _household(c)
    text = _phone_client(c).get("/plan/upcoming").text
    assert 'href="/plan/upcoming?day=2026-12-08"' in text
    assert "Rent" in _phone_client(c).get("/plan/upcoming?day=2026-12-03").text.split('id="upcoming-day"')[1]


def test_a_window_of_days_crosses_the_month_end(c):
    from lightning.planning.calendar import payment_window
    _household(c)
    week = payment_window(c.planning, c.gameya, date(2026, 11, 28), 7)
    assert [d.date for d in week.days][0] == "2026-11-28" and week.days[-1].date == "2026-12-04"
    assert [e.name for d in week.days for e in d.entries] == ["Salary", "Rent"]
    assert (week.left_to_pay, week.to_pay) == (D("12000"), 1) and week.days[3].payday


def test_the_overview_shows_the_next_seven_days_and_a_quiet_week_names_the_next_bill(c, monkeypatch):
    _household(c)
    client = TestClient(create_app(c))
    quiet = client.get("/").text                                    # 11 to 17 Nov: nothing; the loan is late, not ahead
    assert "Next 7 days" in quiet and 'class="week-day' not in quiet
    assert "Next: Internet, 650 on 20 Nov." in quiet
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-18")
    week = client.get("/").text
    assert week.count('class="week-day') == 7
    assert "650 to pay, of 3,150 left this month" in week and 'href="/plan/upcoming?month=2026-11&amp;day=2026-11-20"' in week


def test_the_overview_has_no_week_without_a_plan(c):
    c.account_flows.open_account("Wallet", "CASH", "2026-09-01", "1000")
    assert "Next 7 days" not in TestClient(create_app(c)).get("/").text


def test_money_coming_up_carries_the_two_weeks(c):
    from lightning.ui.phone.screens.money import build
    _household(c)
    strip = build(c, TODAY).strip
    assert len(strip) == 14 and strip[0]["today"] and strip[9]["date"] == "2026-11-20" and strip[9]["entries"]
