"""7N: Due before payday is one total, in the profile currency and still owed, on the card, the stat and Safe to spend."""

from __future__ import annotations

import re
from datetime import date
from html import unescape

from fastapi.testclient import TestClient

from lightning.core.figures import label
from lightning.samples import load_mohab_2026
from lightning.ui import visuals
from lightning.ui.web import create_app
from tests.test_phone_cash_planning import _phone


def _cards(html: str) -> list[str]:
    row = html.split('class="kpi-row', 1)[1].split("</section>", 1)[0]
    return [unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", card)))
            for card in re.split(r'<article class="kpi-card[^"]*">', row)[1:]]


def test_a_dollar_bill_and_a_part_paid_instalment_give_one_due_before_payday(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-02")
    load_mohab_2026(c)
    names = {account.name: account.id for account in c.accounts.list()}
    category = lambda text: str(c.categories.find_by_text(text).id)  # noqa: E731
    # A 20 USD subscription paid from the dollar account (the audit's case: 18,480 on the card, 19,492 in Safe to spend).
    c.planning.create(kind="SUBSCRIPTION", name="Cloud storage", amount="20", frequency="MONTHLY", interval_count="1",
                      start_date="2026-10-15", account_id=str(names["Dollar savings"]),
                      category_id=category("Personal › Entertainment"))
    # An instalment due before payday, half paid early: 1,000 of 2,000 is still owed.
    loan = c.planning.create(kind="LOAN", name="Phone instalments", amount="2,000", frequency="MONTHLY",
                             interval_count="1", start_date="2026-10-20", payment_count="6", principal="12,000",
                             account_id=str(names["CIB Payroll"]),
                             category_id=category("System categories › Loan payments"))
    c.planning.record_payment(loan, "2026-10-20", "2026-10-02", "1000", names["CIB Payroll"])

    day = date(2026, 10, 2)
    f = c.forecaster.forecast(day)
    before = {p.item.name: p for p in f.payments_before_income}
    assert {"Cloud storage", "Phone instalments"} <= set(before)
    assert before["Phone instalments"].still_owed == 1000
    total = -dict(f.safe_to_spend_parts)[label("payments_before_next_income")]
    assert f.payments_before_income_total == total
    assert total == c.planning.still_owed_in_base(f.payments_before_income, day)
    assert total > sum(p.still_owed for p in f.payments_before_income)  # 20 USD is worth more than 20 EGP

    assert visuals.cash_plan(c, f, day)["before_total"] == total  # the stat and the chart
    with TestClient(create_app(c)) as browser:
        cards = _cards(browser.get("/plan").text)
        desktop = browser.get("/payday").text
    with _phone(c) as phone:
        mobile = phone.get("/payday").text
    converted = c.planning.amount_in_base(before["Cloud storage"], before["Cloud storage"].still_owed, day)
    for page in (desktop, mobile):
        cloud = page.split("Cloud storage", 1)[1].split("</b>", 1)[0]
        assert f"{converted:,.0f} EGP" in cloud
    due = next(card for card in cards if label("payments_before_next_income") in card)
    assert f"{total:,.0f}" in due


def test_home_bills_due_show_the_outstanding_amount_in_profile_currency(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-02")
    load_mohab_2026(c)
    names = {a.name: a.id for a in c.accounts.list()}
    today = date(2026, 10, 2)
    cloud = c.planning.create(kind="BILL", name="Dollar hosting", amount="20", frequency="ONCE",
                              start_date=today.isoformat(), account_id=names["Dollar savings"])
    loan = c.planning.create(kind="LOAN", name="Phone instalment", amount="1000", frequency="MONTHLY",
                             start_date=today.isoformat(), payment_count="2", account_id=names["CIB Payroll"])
    c.planning.record_payment(loan, today.isoformat(), today.isoformat(), "250", names["CIB Payroll"])
    payments = {p.item.id: p for p in c.position.at(today).owe.bills_due_items}
    converted = c.planning.amount_in_base(payments[cloud], payments[cloud].still_owed, today)
    assert converted > 20 and payments[loan].still_owed == 750
    with TestClient(create_app(c)) as browser:
        card = browser.get("/").text.split('id="cash-heading"', 1)[1].split('id="madeof-heading"', 1)[0]
    for name, expected in (("Dollar hosting", converted), ("Phone instalment", 750)):
        row = card.split(name, 1)[1].split("</a>", 1)[0]
        assert f"<b>{expected:,.0f}</b>" in row
