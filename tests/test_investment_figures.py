"""Direct coverage of the owned investment table's allocation and foreign gains."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from lightning.investments.domain import Position as Holding
from lightning.planning.investment_figures import InvestmentBreakdown, investment_breakdown
from lightning.planning.position import ClassValue, OwnedHolding


def holding(quantity=D("10"), value=D("31200")):
    return Holding(account_id=1, account_label="Broker", asset_id=2, asset_code="ETF",
                   asset_name="Foreign fund", asset_class="Funds › Equity", exposure="Equity", unit="unit",
                   quantity=quantity, cost_basis=D("25000"), realized=D("0"), dividends=D("0"),
                   price=D("60"), price_date="2026-09-30", price_source="MANUAL", value=value,
                   owned_invested=D("25000"))


def test_balance_only_holdings_are_unassigned_and_all_horizons_reconcile(c):
    h = holding()
    traded = OwnedHolding(1, "Broker", 2, "Foreign fund", "FUND.EQUITY", D("10"), D("31200"), "unit")
    flat = OwnedHolding(3, "Flat", 4, "Flat", "PROPERTY", D("1"), D("100000"), "unit")
    empty = replace(flat, account_id=5, value=D("0"))
    position = replace(c.position.at("2026-09-30"), classes=(
        ClassValue(1, "FUND.EQUITY", "Equity", D("31200"), D("95"), [traded]),
        ClassValue(2, "PROPERTY", "Property", D("100000"), D("95"), [flat, empty]),
    ))
    result = investment_breakdown([(h, h.value, "Invest", "Long term", h.cost_basis, h.unrealized, h.quantity)],
                                  position, {}, "EGP")
    assert isinstance(result, InvestmentBreakdown)
    assert result.balances == [("Property", flat)]
    assert dict(result.horizons) == {"Long term": D("31200"), "Unassigned": D("100000")}
    assert sum(result.horizons.values()) == result.total == position.holdings_value == D("131200")
    assert sum(g["value"] for g in result.groups) == result.total
    assert next(g for g in result.groups if g["name"] == "Property")["rows"][0]["balance"] is True


@pytest.mark.parametrize("units", [D("10"), D("3.333333")])
def test_foreign_price_and_fx_parts_add_to_the_owned_gain(c, units):
    h = holding()
    share = units / h.quantity
    value, cost = h.value * share, h.cost_basis * share
    gain = value - cost
    report = {"holdings": [{"account_id": 1, "asset_id": 2, "price_part": D("5200"),
                            "fx_part": D("1000"), "currency": "USD", "cost_native": D("500")}]}
    result = investment_breakdown([(h, value, "Invest", "Long term", cost, gain, units)],
                                  c.position.at("2026-09-30"), report, "EGP")
    row = result.groups[0]["rows"][0]
    assert row["price_part"] == (D("5200") * share).quantize(D("0.01"))
    assert row["price_part"] + row["fx_part"] == row["gain"] == gain
    assert row["currency"] == "USD"
    assert row["average_cost_native"] == D("50")


@pytest.mark.parametrize("quantity,gain", [(D("0"), D("6200")), (D("10"), None)])
def test_missing_quantity_or_gain_has_no_foreign_split(c, quantity, gain):
    h = holding(quantity=quantity)
    report = {"holdings": [{"account_id": 1, "asset_id": 2, "price_part": D("5200"),
                            "fx_part": D("1000"), "currency": "USD", "cost_native": D("500")}]}
    result = investment_breakdown([(h, h.value, "Invest", "Long term", h.cost_basis, gain, quantity)],
                                  c.position.at("2026-09-30"), report, "EGP")
    row = result.groups[0]["rows"][0]
    assert "price_part" not in row and "fx_part" not in row
    if not quantity:
        assert row["average_cost_native"] is None
