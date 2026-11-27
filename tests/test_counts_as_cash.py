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


def test_partial_owned_fund_in_two_accounts_and_after_a_sale(c):
    _, broker, fund = _fund(c)
    other = c.account_flows.open_account("Other broker", "BROKERAGE", "2026-09-01", "1000")
    c.investments.move_units("2026-10-02", broker.id, other.id, fund.id, "20")
    owner = c.counterparties.create("Relative")
    salary = c.categories.get_by_code("EXP.WORK.SALARY").id
    c.transactions.record_inflow("2026-10-03", broker.id, "1200", salary, owner_id=owner)
    c.investments.buy("2026-10-03", broker.id, fund.id, "10", "120", owner_id=owner)
    c.investments.set_liquidation_factor(fund.asset_class_id, "90")
    before = c.position.at(DAY)
    c.assets.set_holding_cash_percent(broker.id, fund.id, DAY, "٢٥")
    c.assets.set_holding_cash_percent(other.id, fund.id, DAY, "0")
    c.assets.set_counts_as_cash(fund.id, True)
    after = c.position.at(DAY)
    assert after.counted_as_cash == 2400  # 25% of 80 owned units at 120
    assert after.free_cash == before.free_cash + 2400
    assert after.cash_you_own == before.cash_you_own and after.net_worth == before.net_worth
    assert after.holdings_after_sale_beyond_cash == 8640
    assert emergency_liquidity_context(after)["unknown"][0]["value"] == 9600
    c.assets.set_holding_cash_percent(other.id, fund.id, "2026-10-16", None)
    assert c.position.at(DAY).counted_as_cash == 2400
    assert c.position.at("2026-10-16").counted_as_cash == 4800
    c.investments.sell("2026-10-17", broker.id, fund.id, "40", "120")
    assert c.position.at("2026-10-17").counted_as_cash == 3600


def test_percentage_preview_and_invalid_edits(c, monkeypatch):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    monkeypatch.setenv("LIGHTNING_TODAY", DAY)
    _, broker, fund = _fund(c)
    client = TestClient(create_app(c))
    path = f"/investments/holding/{fund.id}/cash/{broker.id}"
    custom = {"mode": "custom", "percent": "٢٥٫٥"}
    assert "3,060" in client.get(path + "/preview", params=custom).text
    assert c.position.at(DAY).counted_as_cash == 0
    for invalid in ("", "100.01", "-1", "0.001", "NaN"):
        fields = {"mode": "custom", "percent": invalid}
        assert client.get(path + "/preview", params=fields).status_code == 400
        client.post(path, data=fields, follow_redirects=False)
    assert c.assets.holding_cash_rules(DAY) == {}
    client.post(path, data=custom, follow_redirects=False)
    assert c.position.at(DAY).counted_as_cash == 3060
    assert c.position.at("2026-10-14").counted_as_cash == 0
    assert "requires redemption" in client.get("/explain/free-cash").text


def test_upgrading_preserves_existing_investment_defaults(tmp_path, monkeypatch):
    import shutil
    from lightning.assets.service import AssetService
    from lightning.database import migrator
    from lightning.database.connection import Database
    from lightning.database.seed import seed

    old = tmp_path / "migrations"
    old.mkdir()
    for migration in migrator.MIGRATIONS_DIR.glob("*.sql"):
        if int(migration.name[:4]) <= 93:
            shutil.copy(migration, old)
    db = Database(":memory:")
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", old)
    migrator.migrate(db)
    seed(db)
    assets = AssetService(db)
    fund = assets.create_investment("Money market", "FUND.MONEY_MARKET", "MMKT")
    db.execute("UPDATE financial_assets SET counts_as_cash=1 WHERE id=?", (fund.id,))
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", migrator._BUNDLED_MIGRATIONS_DIR)
    assert migrator.migrate(db)[0] == "0094_holding_cash_shares (APPLIED)"
    assert assets.get_asset(fund.id).counts_as_cash
    assert assets.holding_cash_rules(DAY) == {}
    assert migrator.migrate(db) == []


def test_floor_price_changes_redemption_and_broker_cash(c, monkeypatch):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    monkeypatch.setenv("LIGHTNING_TODAY", DAY)
    _, broker, fund = _fund(c)
    browser = TestClient(create_app(c))
    path = f"/investments/holding/{fund.id}/cash/{broker.id}"
    from datetime import date
    day = date.fromisoformat(DAY)
    baseline = c.position.at(DAY)
    funding_before = c.funding.preview(day)["cash"]
    forecast_before = c.forecaster.forecast(day)
    fields = {"mode": "floor", "protected": "٩٠٠٠"}
    assert "3,000" in browser.get(path + "/preview", params=fields).text
    assert c.position.at(DAY).free_cash == baseline.free_cash
    browser.post(path, data=fields, follow_redirects=False)
    after = c.position.at(DAY)
    assert after.free_cash == baseline.free_cash + 3000
    assert after.net_worth == baseline.net_worth
    assert c.funding.preview(day)["cash"] == funding_before + 3000
    forecast_after = c.forecaster.forecast(day)
    assert forecast_after.free_cash == after.free_cash
    assert forecast_after.safe_to_spend == forecast_before.safe_to_spend + 3000
    assert emergency_liquidity_context(after)["unknown"][0]["value"] == 9000
    assert c.position.at("2026-10-14").counted_as_cash == 0
    assert browser.get(path + "/preview", params={"mode": "floor", "protected": "-1"}).status_code == 400
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-18")
    c.assets.set_price(fund.id, "2026-10-16", "80")
    assert c.position.at("2026-10-16").counted_as_cash == 0
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-16")
    detail = browser.get("/explain/free-cash").text
    assert "Holdings contributing zero" in detail and "9,000" in detail
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-18")
    c.assets.set_price(fund.id, "2026-10-17", "140")
    assert c.position.at("2026-10-17").counted_as_cash == 5000
    c.investments.sell("2026-10-17", broker.id, fund.id, "50", "140")
    sold = c.position.at("2026-10-17")
    assert sold.counted_as_cash == 0
    assert sold.free_cash == baseline.free_cash
    browser.post(f"/accounts/{broker.id}/spendable", data={"spendable": "yes"}, follow_redirects=False)
    assert c.position.at("2026-10-17").free_cash == sold.free_cash + sold.brokerage_cash
    c.assets.set_holding_cash_percent(broker.id, fund.id, "2026-10-18", "25")
    assert c.position.at("2026-10-18").counted_as_cash == 1750


def test_inherited_defaults_preserve_history_and_respect_overrides(c):
    _, broker, fund = _fund(c)
    c.assets.set_dated_cash_default(fund.id, DAY, True)
    assert c.position.at("2026-10-14").counted_as_cash == 0
    c.assets.set_holding_cash_floor(broker.id, fund.id, "2026-10-16", 2000)
    c.assets.set_dated_cash_default(fund.id, "2026-10-17", False)
    c.assets.set_holding_cash_percent(broker.id, fund.id, "2026-10-18", None)
    assert c.position.at(DAY).counted_as_cash == 12000
    assert c.position.at("2026-10-17").counted_as_cash == 10000
    assert c.position.at("2026-10-18").counted_as_cash == 0


def test_cash_preferences_survive_workbook_export(c, tmp_path):
    from lightning.bootstrap import build
    from lightning.workflows.data_export import export_all
    from lightning.workflows.workbook_import import confirm_import

    _, broker, fund = _fund(c)
    c.assets.set_dated_cash_default(fund.id, DAY, True)
    c.assets.set_holding_cash_floor(broker.id, fund.id, "2026-10-16", "8500.25")
    data, _, _ = export_all(c, "xlsx")
    restored = build(tmp_path / "restored.db")
    try:
        confirm_import(restored, data)
        assert restored.position.at("2026-10-14").counted_as_cash == 0
        assert restored.position.at(DAY).counted_as_cash == 12000
        assert restored.position.at("2026-10-16").counted_as_cash == Decimal("3499.75")
    finally:
        restored.db.close()


def test_floor_requires_a_positive_owned_valuation_and_an_unlocked_holding():
    from lightning.planning.position import OwnedHolding

    item = OwnedHolding(1, "Broker", 2, "Fund", "FUND.FIXED_INCOME", Decimal(10), None, "units",
                        protected_amount=Decimal("0.25"))
    for value in (None, Decimal("-1"), Decimal("0"), Decimal("0.25")):
        item.value = value
        assert item.cash_value == 0
    item.value = Decimal("10.75")
    assert item.cash_value == Decimal("10.50")
    item._locked_until = "2027-01-01"
    assert item.cash_value == 0
