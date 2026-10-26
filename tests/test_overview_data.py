"""Overview figures and drilldowns use the same ledger boundaries as their source views."""

from decimal import Decimal
from fastapi.testclient import TestClient
from starlette.responses import Response

from lightning.ui.web import create_app


def test_overview_cash_reserves_spending_and_investments_reconcile(c, setup, monkeypatch):
    from lightning.ui.routes import dashboard as dashboard_module

    accounts, cats = setup
    c.transactions.record_transfer("2026-12-05", accounts["cib"].id, accounts["thndr"].id, "1000")
    c.transactions.record_outflow("2026-12-10", accounts["cib"].id, "100", cats["EXP.PERSONAL.FOOD"].id)
    reserve = c.reserves.create("Travel", "1000")
    c.reserves.allocate(reserve["id"], "500")
    captured = {}

    def capture(_request, _template, **context):
        captured.update(context)
        return Response("ok")

    monkeypatch.setattr(dashboard_module, "render", capture)
    response = TestClient(create_app(c)).get("/?period=custom&date_from=2026-12-01&date_to=2026-12-31")
    assert response.status_code == 200
    pos = captured["pos"]
    assert c.reporting.net_worth(pos.as_of).total == sum(
        (c.reporting.owned_account_value(account.id, pos.as_of) for account in c.accounts.list()), Decimal(0))
    assert pos.cash_you_own == sum((row["value"] for row in captured["cash_accounts"]), Decimal(0))
    assert pos.brokerage_cash == Decimal("1000")
    assert pos.reserves == sum((row["effective_allocated"] for row in pos.reserve_rows), Decimal(0))
    assert pos.kept_apart == pos.brokerage_cash  # brokerage cash is kept apart from spendable cash
    assert pos.free_cash == pos.cash_you_own - pos.kept_apart - Decimal("500")
    from datetime import date as _date
    from lightning.ui import visuals as _visuals  # "Where money in went" lives on Spending (owner, 2026-10-21)
    flow = _visuals.cash_flow_charts(c, _date(2026, 12, 1), _date(2026, 12, 31), False, _date(2026, 12, 31))["money_sankey"]
    assert "Food" in flow["targets"][0]["label"] and len(flow["targets"]) == 1 and flow["targets"][0]["value"] == Decimal("100")
    assert "category_id=" in flow["targets"][0]["href"]
    assert [s["label"] for s in flow["sources"]] == ["From what you had"] and flow["total"] == Decimal("100")
    columns = captured["flow_columns"]["columns"]  # money in, less money out by kind, ends at net flow
    assert [(col["label"], col["value"]) for col in columns] == [
        ("Money in", Decimal("0")), ("Personal", Decimal("-100")), ("Net flow", Decimal("-100"))]
    assert captured["investment_report"]["brokerage_cash"] == Decimal("1000")
    assert captured["investment_report"]["new_money"] == Decimal("1000")
    assert captured["investment_report"]["period_result"] == Decimal("0")


def test_overview_keeps_every_current_attention_item(c, setup, monkeypatch):
    from lightning.ui.routes import dashboard as dashboard_module

    normal_net_worth = c.reporting.net_worth

    def with_missing_valuations(day):
        result = normal_net_worth(day)
        if str(day) == "2026-12-31":
            result.unvalued = [f"Holding {number}" for number in range(5)]
        return result

    monkeypatch.setattr(c.reporting, "net_worth", with_missing_valuations)
    captured = {}

    def capture(_request, _template, **context):
        captured.update(context)
        return Response("ok")

    monkeypatch.setattr(dashboard_module, "render", capture)
    assert TestClient(create_app(c)).get("/?month=2026-12").status_code == 200
    assert len([item for item in captured["attention"] if item["label"] == "Missing valuation"]) == 5


def test_reserve_historical_breakdown_matches_total_and_rejects_unknown_past(c, setup):
    reserve = c.reserves.create("Travel", "1000")
    c.reserves.allocate(reserve["id"], "500")
    assert c.reserves.breakdown_at("2026-09-30") is None
    rows = c.reserves.breakdown_at("2026-12-31")
    assert rows == [{"id": reserve["id"], "name": "Travel", "kind": "PROJECT", "effective_allocated": Decimal("500")}]
    assert c.reserves.allocation_at("2026-12-31") == sum((row["effective_allocated"] for row in rows), Decimal(0))


def test_where_money_in_went_splits_kept_into_invested_and_the_rest(c, setup, monkeypatch):
    """Feedback ticket 82: Kept shows the part moved into investments in blue."""
    from lightning.ui.routes import dashboard as dashboard_module

    accounts, cats = setup
    c.transactions.record_inflow("2026-12-01", accounts["cib"].id, "10000", cats["EXP.WORK.SALARY"].id)
    c.transactions.record_outflow("2026-12-10", accounts["cib"].id, "4000", cats["EXP.PERSONAL.FOOD"].id)
    c.transactions.record_transfer("2026-12-15", accounts["cib"].id, accounts["thndr"].id, "2500")
    captured = {}

    def capture(_request, _template, **context):
        captured.update(context)
        return Response("ok")

    monkeypatch.setattr(dashboard_module, "render", capture)
    TestClient(create_app(c)).get("/?period=custom&date_from=2026-12-01&date_to=2026-12-31")
    from datetime import date as _date
    from lightning.ui import visuals as _visuals  # on Spending since 2026-10-21
    sankey = _visuals.cash_flow_charts(c, _date(2026, 12, 1), _date(2026, 12, 31), False, _date(2026, 12, 31))["money_sankey"]
    targets = {t["label"]: (t["value"], t["tone"]) for t in sankey["targets"]}
    assert targets["Invested"] == (Decimal("2500"), "hold")
    assert targets["Kept"] == (Decimal("3500"), "in")
    assert sum(v for v, _ in targets.values()) == Decimal("10000")
