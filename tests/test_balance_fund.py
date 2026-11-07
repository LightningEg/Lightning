"""IT-2AJ: a fund with no share price (balance grows by interest) is held as 1 unit = 1 pound and never repriced."""
from decimal import Decimal

from fastapi.testclient import TestClient

from lightning.ui.web import create_app

D = Decimal


def _fund(c, accounts):
    fund = c.assets.create_investment("THNDR Fixed Cloud", "FUND.BALANCE", "CLOUD")
    c.transactions.record_transfer("2026-01-02", accounts["cib"].id, accounts["thndr"].id, "20000")
    return fund


def test_balance_fund_is_an_investment_kind_worth_one_pound_a_unit(c, setup):
    accounts, _ = setup
    assert "FUND.BALANCE" in [k.code for k in c.assets.investment_classes()]
    fund = _fund(c, accounts)
    assert fund.code == "BAL:CLOUD" and fund.quantity_decimals == 2


def test_a_later_buy_never_reprices_an_earlier_holding(c, setup):
    """The owner's workbook: Dad's 43,900 and then your own 19,010 bought at different 'prices'."""
    accounts, _ = setup
    fund = _fund(c, accounts)
    dad = c.counterparties.create("Dad")
    thndr = accounts["thndr"].id
    c.money_from_others.record("2026-01-04", "Dad", thndr, D("4390"))
    c.investments.buy_total("2026-01-05", thndr, fund.id, "4390", "4390", owner_id=dad)
    c.investments.buy_total("2026-01-06", thndr, fund.id, "1000", "1010")
    assert c.reporting.money_from_others_total("2026-01-06") == D("4390")


def test_interest_posted_as_units_grows_the_balance_and_the_gain(c, setup):
    accounts, _ = setup
    fund = _fund(c, accounts)
    thndr = accounts["thndr"].id
    c.investments.buy_total("2026-01-05", thndr, fund.id, "1000", "1000")
    c.investments.bonus_or_split("2026-02-05", thndr, fund.id, "1012.55")
    position = next(p for p in c.investments.portfolio("2026-02-05").positions if p.asset_id == fund.id)
    assert position.value == D("1012.55") and position.price == D("1") and position.cost_basis == D("1000")
    page = TestClient(create_app(c)).get("/investments/assets/new").text
    assert '<option value="FUND.BALANCE"' in page
