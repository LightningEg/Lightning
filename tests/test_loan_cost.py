"""IV-3H7: a loan may carry an optional yearly rate (flat or reducing); the Loans tab then shows the total interest
and the cost of the loan. Payments stay spending and nothing in the ledger changes; a loan without a rate reads as
before."""
from __future__ import annotations

from decimal import Decimal as D

import shutil

import pytest
from fastapi.testclient import TestClient

from lightning.database import migrator
from lightning.database.connection import Database

from lightning.core.errors import ValidationError
from lightning.planning.loan_cost import loan_cost
from lightning.ui.web import create_app


def test_a_flat_loan_charges_interest_on_the_amount_borrowed_for_the_whole_term():
    cost = loan_cost(D("60000"), D("10"), "FLAT", 24, None)
    assert cost.interest == D("12000.00") and cost.cost == D("72000.00") and cost.instalment == D("3000.00")
    # Without the amount borrowed it is worked back from the monthly payment.
    assert loan_cost(None, D("10"), "FLAT", 24, D("3000")).principal == D("60000.00")


def test_a_reducing_loan_matches_an_amortisation_table_worked_month_by_month():
    principal, rate, months = D("100000"), D("18"), 12
    cost = loan_cost(principal, rate, "REDUCING", months, None)
    i = rate / 1200
    payment = cost.instalment
    balance, interest_paid = principal, D(0)
    for month in range(1, months + 1):  # the bank's table: interest on what is still owed, the rest repays it
        interest = (balance * i).quantize(D("0.01"))
        repaid = payment - interest if month < months else balance
        interest_paid += interest
        balance -= repaid
    assert payment == D("9168.00")
    assert balance == 0 and cost.interest == interest_paid
    assert cost.interest == D("10015.99") and cost.cost == D("110015.99")
    # The same loan worked back from its payment gives back the amount borrowed.
    assert abs(loan_cost(None, rate, "REDUCING", months, payment).principal - principal) <= D("0.05")


def test_no_cost_without_a_term_or_an_amount():
    assert loan_cost(None, D("10"), "FLAT", 24, None) is None
    assert loan_cost(D("1000"), D("10"), "FLAT", 0, None) is None


def _loan(c, **extra):
    return c.planning.create(kind="LOAN", name="Car loan", amount="3000", frequency="MONTHLY",
                             start_date="2026-01-15", payment_count=24, principal="60000", **extra)


def _phone(app):
    async def phone_app(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)
    return phone_app


def test_the_loan_card_shows_interest_and_cost_only_when_a_rate_is_set(c):
    plain = _loan(c)
    pc, phone = TestClient(create_app(c)), TestClient(_phone(create_app(c)))
    for client in (pc, phone):
        page = client.get("/plan/loans").text
        assert "Car loan" in page and "Total interest" not in page and "Cost of this loan" not in page
    assert c.planning.loan_cost(c.planning.get(plain)) is None

    spent_before = c.reporting.cash_flow("2026-01-01", "2026-12-31").outflows
    item = c.planning.get(plain)
    c.planning.update(plain, kind="LOAN", name=item.name, amount="3000", frequency="MONTHLY", start_date=item.start_date,
                      payment_count=24, principal="60000", interest_rate="10", rate_kind="FLAT")
    assert c.planning.loan_cost(c.planning.get(plain)).interest == D("12000.00")
    for client in (pc, phone):
        page = client.get("/plan/loans").text
        assert "Total interest" in page and "12,000" in page and "Cost of this loan" in page and "72,000" in page
    assert c.reporting.cash_flow("2026-01-01", "2026-12-31").outflows == spent_before  # nothing posted

    # An edit that does not send the rate keeps it; an empty rate clears it.
    c.planning.update(plain, kind="LOAN", name="Car loan", amount="3000", frequency="MONTHLY",
                      start_date=item.start_date, payment_count=24, principal="60000")
    assert c.planning.get(plain).interest_rate == D("10") and c.planning.get(plain).rate_kind == "FLAT"
    c.planning.update(plain, kind="LOAN", name="Car loan", amount="3000", frequency="MONTHLY",
                      start_date=item.start_date, payment_count=24, principal="60000", interest_rate="", rate_kind="")
    assert c.planning.get(plain).interest_rate is None and c.planning.loan_cost(c.planning.get(plain)) is None


def test_the_loan_form_saves_the_rate_and_bad_rates_are_refused(c):
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    loan = _loan(c)
    form = client.get(f"/plan/items/{loan}/edit").text
    assert 'name="interest_rate"' in form and 'name="rate_kind"' in form
    fields = dict(kind="LOAN", name="Car loan", amount="3000", frequency="MONTHLY", interval_count="1",
                  start_date="2026-01-15", payment_count="24", principal="60000", weekend_move="none",
                  match_window_days="7", match_tolerance_pct="1", back="/plan/loans")
    saved = client.post(f"/plan/items/{loan}/edit", data=fields | dict(interest_rate="10", rate_kind="FLAT"),
                        follow_redirects=False)
    assert saved.status_code == 303 and c.planning.get(loan).interest_rate == D("10")
    refused = client.post("/plan/items", data=fields | dict(name="Second", interest_rate="200", rate_kind="FLAT"))
    assert refused.status_code == 400 and not [i for i in c.planning.items() if i.name == "Second"]  # nothing half-saved
    client.post(f"/plan/items/{loan}/edit", data=fields | dict(interest_rate="", rate_kind="FLAT"))
    assert c.planning.get(loan).interest_rate is None
    with pytest.raises(ValidationError, match="flat or reducing"):
        _loan(c, interest_rate="12")
    with pytest.raises(ValidationError, match="up to 100%"):
        _loan(c, interest_rate="150", rate_kind="FLAT")
    bill = c.planning.create(kind="BILL", name="Rent", amount="5000", frequency="MONTHLY", start_date="2026-01-01",
                             interest_rate="10", rate_kind="FLAT")
    assert c.planning.get(bill).interest_rate is None  # only a loan carries a rate
    reducing = _loan(c, interest_rate="18.5", rate_kind="reducing")
    assert c.planning.get(reducing).rate_kind == "REDUCING" and c.planning.get(reducing).interest_rate == D("18.5")


def test_migration_0093_keeps_every_loan_as_it_was_with_no_rate(monkeypatch, tmp_path):
    before = tmp_path / "migrations"
    before.mkdir()
    for path in sorted(migrator._BUNDLED_MIGRATIONS_DIR.glob("*.sql")):
        if int(path.name[:4]) <= 92:
            shutil.copy(path, before / path.name)
    db = Database(":memory:")
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", before)
    migrator.migrate(db)
    db.execute("INSERT INTO planned_items(kind,name,amount_e6,frequency,interval_count,start_date,payment_count,principal_e6,"
               "created_at,updated_at) VALUES ('LOAN','Car loan',3000000000,'MONTHLY',1,'2026-01-15',24,60000000000,'x','x')")
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", migrator._BUNDLED_MIGRATIONS_DIR)
    assert migrator.migrate(db) == ["0093_loan_rate (APPLIED)"]
    row = db.one("SELECT amount_e6,principal_e6,payment_count,interest_rate_e6,rate_kind FROM planned_items")
    assert tuple(row) == (3000000000, 60000000000, 24, None, None)
    assert migrator.migrate(db) == []  # a second run does nothing
    with pytest.raises(Exception):
        db.execute("UPDATE planned_items SET rate_kind='SIMPLE'")


def test_the_loan_cost_rows_read_in_arabic(c):
    _loan(c, interest_rate="10", rate_kind="FLAT")
    client = TestClient(create_app(c))
    client.post("/settings/locale", data={"locale": "ar"}, follow_redirects=False)
    page = client.get("/plan/loans").text
    assert "إجمالي الفوايد" in page and "تكلفة القرض ده" in page and "ثابتة" in page
    assert "Total interest" not in page and "Cost of this loan" not in page and " flat" not in page
