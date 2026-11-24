"""NF-7AU: an investment marked to count with cash joins Free cash at its value, and nothing else moves."""
from __future__ import annotations

from decimal import Decimal

from lightning.planning.emergency_context import emergency_liquidity_context

DAY = "2026-10-15"


def _fund(c):
    bank = c.account_flows.open_account("Bank", "BANK", "2026-09-01", "50000")
    broker = c.account_flows.open_account("Broker", "BROKERAGE", "2026-09-01", "20000")
    fund = c.assets.create_investment("Fixed income fund", "FUND.FIXED_INCOME", "FIXF")
    c.investments.buy("2026-09-10", broker.id, fund.id, "100", "100")
    c.assets.set_price(fund.id, "2026-10-01", "120")
    return bank, broker, fund


def test_marking_a_fund_raises_free_cash_by_its_value_and_nothing_else(c):
    _, _, fund = _fund(c)
    c.investments.set_liquidation_factor(c.assets.get_class_by_code("FUND.FIXED_INCOME").id, "90")
    before = c.position.at(DAY, match_payments=False)
    assert c.assets.get_asset(fund.id).counts_as_cash is False
    assert before.counted_as_cash == 0

    c.assets.set_counts_as_cash(fund.id, True)
    after = c.position.at(DAY, match_payments=False)

    assert after.counted_as_cash == Decimal("12000")
    assert after.free_cash - before.free_cash == Decimal("12000")
    assert after.net_worth == before.net_worth
    assert after.what_you_own == before.what_you_own
    assert after.holdings_value == before.holdings_value
    assert after.cash_you_own == before.cash_you_own
    assert after.kept_apart == before.kept_apart
    # Counted at full value in Free cash, so never again at its sale factor.
    assert after.holdings_after_sale_beyond_cash == 0
    assert after.if_you_sold_today == after.free_cash + after.kept_apart
    assert sum(after.sale_parts["classes"].values()) == after.sale_parts["holdings_after_sale"]
    # Listed once: Free cash holds it, the emergency list does not repeat it.
    context = emergency_liquidity_context(after)
    assert not context["within_days"] and not context["unknown"]


def test_the_ledger_check_still_agrees_and_unmarking_restores(c):
    _, _, fund = _fund(c)
    before = c.position.at(DAY, match_payments=False).free_cash
    c.assets.set_counts_as_cash(fund.id, True)
    check = c.integrity._free_cash_check(DAY)
    assert check.status == "PASS", check.detail
    c.assets.set_counts_as_cash(fund.id, False)
    assert c.position.at(DAY, match_payments=False).free_cash == before


def test_the_switch_on_the_investment_page(c):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app

    _, _, fund = _fund(c)
    client = TestClient(create_app(c))
    page = client.get(f"/investments/assets/{fund.id}/edit")
    assert page.status_code == 200 and 'name="counts_as_cash"' in page.text
    form = {"name": fund.name, "class_code": "FUND.FIXED_INCOME", "symbol": "FIXF", "active": "1",
            "cash_switch": "1", "counts_as_cash": "1"}
    assert client.post(f"/investments/assets/{fund.id}/edit", data=form).status_code in (200, 303)
    assert c.assets.get_asset(fund.id).counts_as_cash is True
    form.pop("counts_as_cash")
    client.post(f"/investments/assets/{fund.id}/edit", data=form)
    assert c.assets.get_asset(fund.id).counts_as_cash is False


def test_home_and_free_cash_explanation_include_the_same_adjustments(c, monkeypatch):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    from tests.screens import visible_text

    monkeypatch.setenv("LIGHTNING_TODAY", DAY)
    bank, _, fund = _fund(c)
    c.assets.set_counts_as_cash(fund.id, True)
    bill = c.planning.create(kind="BILL", name="Insurance", amount="1000", frequency="ONCE",
                             start_date=DAY, account_id=bank.id)
    reserve = c.reserves.create("Insurance money", "1000")
    c.reserves.allocate(reserve["id"], "800")
    c.reserves.set_planned_item(reserve["id"], bill)
    position = c.position.at(DAY)
    assert position.free_cash == 61000
    assert position.set_aside_or_due == 11000
    assert position.cash_you_own + sum(row.amount for row in position.free_cash_adjustments) == position.free_cash
    with TestClient(create_app(c)) as browser:
        home = visible_text(browser.get("/").text.split('id="cash-heading"', 1)[1].split('id="madeof-heading"', 1)[0])
        popup = visible_text(browser.get("/explain/free-cash").text)
    for text in (home, popup):
        assert "Counted as cash +12,000" in text
        assert "Bill cash already set aside +800" in text
        assert "61,000" in text
