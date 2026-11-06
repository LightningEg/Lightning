"""IT-1R: investment_breakdown, its price/FX split and its balance-only holdings, tested directly (no screen)."""
from decimal import Decimal
from types import SimpleNamespace

from lightning.planning.investment_figures import _native_cost, _owned_split, investment_breakdown

D = Decimal


def holding(name, cls, account_id, asset_id, quantity, price=D("10")):
    def owned_result(units, yours, capital):
        gain = None if yours is None else yours - capital
        return {"gain": gain, "invested": capital}
    return SimpleNamespace(asset_name=name, asset_class=cls, account_id=account_id, asset_id=asset_id,
                           quantity=D(quantity), price=price, xirr=None, display_return=None, owned_result=owned_result)


def row(h, yours, horizon, capital, unrealized, units):
    return (h, yours, "bucket", horizon, D(capital), unrealized, D(units))


def balance(account, account_id, asset_id, value):
    return SimpleNamespace(account=account, account_id=account_id, asset_id=asset_id, value=D(value))


def position(holdings_value, *classes):
    return SimpleNamespace(holdings_value=D(holdings_value),
                           classes=[SimpleNamespace(name=n, items=items) for n, items in classes])


def test_a_balance_only_asset_lands_in_unassigned_and_the_horizons_add_up_to_holdings_value():
    fund = holding("Equity fund", "Funds › Equity", 1, 10, "10")
    flat = balance("Share of a flat", 2, 20, "500")
    pos = position("1500", ("Real estate", [flat]), ("Equity", []))
    result = investment_breakdown([row(fund, D("1000"), "Long", "800", D("200"), "10")], pos, {}, "EGP")
    assert result.horizons == {"Long": D("1000"), "Unassigned": D("500")}
    assert sum(result.horizons.values()) == pos.holdings_value == result.total
    assert [name for name, _ in result.balances] == ["Real estate"]
    flat_row = next(r for g in result.groups for r in g["rows"] if r.get("balance"))
    assert flat_row["gain"] == 0 and flat_row["weight"] == D("500") / D("1500") * 100


def test_a_balance_that_is_also_traded_or_empty_is_not_listed_twice():
    fund = holding("Equity fund", "Funds › Equity", 1, 10, "10")
    traded = balance("Broker", 1, 10, "1000")       # the same account and asset as the traded holding
    empty = balance("Old deposit", 3, 30, "0")      # no value: nothing to list
    pos = position("1000", ("Equity", [traded, empty]))
    result = investment_breakdown([row(fund, D("1000"), "Long", "800", D("200"), "10")], pos, {}, "EGP")
    assert result.balances == []
    assert "Unassigned" not in result.horizons


def test_groups_sum_weights_and_sort_by_value():
    big = holding("Big fund", "Funds › Equity", 1, 10, "10")
    small = holding("Small fund", "Funds › Equity", 1, 11, "5")
    bonds = holding("Bond fund", "Funds › Bonds", 1, 12, "4")
    rows = [row(small, D("200"), "Long", "150", D("50"), "5"), row(big, D("600"), "Long", "500", D("100"), "10"),
            row(bonds, D("200"), "Short", "190", D("10"), "4")]
    result = investment_breakdown(rows, position("1000"), {}, "EGP")
    assert [g["name"] for g in result.groups] == ["Equity", "Bonds"]
    equity = result.groups[0]
    assert (equity["value"], equity["cost"], equity["gain"]) == (D("800"), D("650"), D("150"))
    assert equity["weight"] == D("80") and equity["gain_pct"] == D("150") / D("650") * 100
    assert [r["h"].asset_name for r in equity["rows"]] == ["Big fund", "Small fund"]


def test_a_foreign_holdings_price_part_and_fx_part_add_up_to_its_gain():
    etf = holding("US index ETF", "Funds › Equity", 5, 50, "10", price=D("60"))
    report = {"holdings": [{"account_id": 5, "asset_id": 50, "price_part": D("5200"), "fx_part": D("1000"),
                            "currency": "USD", "cost_native": D("500")}]}
    result = investment_breakdown([row(etf, D("31200"), "Long", "25000", D("6200"), "10")], position("31200"),
                                  report, "EGP")
    shown = result.groups[0]["rows"][0]
    assert shown["price_part"] + shown["fx_part"] == D("6200")
    assert shown["currency"] == "USD" and shown["average_cost_native"] == D("50")


def test_part_of_a_holding_gets_its_share_and_fx_takes_the_rounding():
    assert _owned_split((D("5200"), D("1000")), D("5"), D("10"), D("3100")) == {
        "price_part": D("2600.00"), "fx_part": D("500.00")}
    third = _owned_split((D("100"), D("0")), D("1"), D("3"), D("33.34"))
    assert third["price_part"] == D("33.33") and third["price_part"] + third["fx_part"] == D("33.34")


def test_no_quantity_or_no_gain_or_no_split_returns_no_split():
    split = (D("5200"), D("1000"))
    assert _owned_split(split, D("5"), D("0"), D("3100")) == {}
    assert _owned_split(split, D("5"), D("10"), None) == {}
    assert _owned_split(None, D("5"), D("10"), D("3100")) == {}
    assert _native_cost(("USD", D("500")), D("0")) == {"currency": None, "average_cost_native": None}
    assert _native_cost(None, D("10")) == {"currency": None, "average_cost_native": None}


def test_a_base_currency_holding_has_no_native_cost_and_an_empty_position_has_no_weights():
    egp = holding("Local fund", "Funds › Equity", 1, 10, "10")
    report = {"holdings": [{"account_id": 1, "asset_id": 10, "currency": "EGP", "cost_native": D("800")}]}
    result = investment_breakdown([row(egp, D("1000"), "Long", "800", D("200"), "10")], position("0"), report, "EGP")
    shown = result.groups[0]["rows"][0]
    assert shown["currency"] is None and shown["weight"] == 0 and result.groups[0]["weight"] == 0
