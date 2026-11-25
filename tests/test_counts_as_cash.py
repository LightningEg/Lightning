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
    assert c.assets.holding_cash_percentages(DAY) == {}
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
    assets.set_counts_as_cash(fund.id, True)
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", migrator._BUNDLED_MIGRATIONS_DIR)
    assert migrator.migrate(db)[0] == "0094_holding_cash_shares (APPLIED)"
    assert assets.get_asset(fund.id).counts_as_cash
    assert assets.holding_cash_percentages(DAY) == {}
    assert migrator.migrate(db) == []
