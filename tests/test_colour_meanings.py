"""IV-3Q4: colour by meaning (A03) and no card in a card (A16) on Loans, Cash planning and Currencies."""
import re

from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def test_loan_paid_is_held_and_owed_is_money_out(c, setup):
    loan = c.planning.create(kind="LOAN", name="Car loan", amount="2500", frequency="MONTHLY", start_date="2026-09-05",
                             payment_count="4", account_id=str(setup[0]["cib"].id))
    c.planning.create(kind="LOAN", name="Phone", amount="900", frequency="MONTHLY", start_date="2026-10-01",
                      payment_count="6", account_id=str(setup[0]["cib"].id))
    c.planning.record_payment(loan, "2026-09-05", "2026-09-05", "2500", setup[0]["cib"].id)
    with TestClient(create_app(c)) as client:
        loans = client.get("/plan/loans").text
        plan = client.get("/plan").text
    assert 'class="seg-hold"' in loans and 'class="seg-out"' in loans  # paid Azure, left soft rose
    assert 'class="seg-in"' not in loans
    assert 'chart-meter-track is-paid' in loans
    by_loan = plan[plan.index("By loan"):]
    assert "tone-spend" in by_loan.split("</section>")[0]


def test_currency_figures_are_not_cards_inside_a_card(c, setup):
    c.currencies.register("USD")
    c.account_flows.open_account("USD bank", "BANK", "2026-09-01", "0", currency="USD")
    with TestClient(create_app(c)) as client:
        page = client.get("/accounts/currencies").text
    for section in re.findall(r'<section class="card data-panel fx-currency".*?</section>', page, re.S):
        assert "metric-card" not in section and "fx-figure" in section
