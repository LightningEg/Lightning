"""Target allocation by risk level (NF-12AM, owner 2026-11-14): Low, Medium and High risk instead of asset
classes. Each holding starts in its class's level and can be moved; old class targets add up into their level."""
from __future__ import annotations

import shutil
from decimal import Decimal as D

from fastapi.testclient import TestClient

from lightning.assets.risk import HIGH, LOW, MEDIUM, default_risk, risk_of
from lightning.ui.web import create_app


def test_each_class_starts_in_the_owners_level():
    assert default_risk("STOCK") == HIGH
    assert default_risk("GOLD") == default_risk("FUND.EQUITY") == default_risk("FUND.GOLD") == MEDIUM
    assert default_risk("FUND.FIXED_INCOME") == default_risk("FUND.MONEY_MARKET") == default_risk("FUND.CLOUD") == LOW
    assert default_risk("DEPOSIT.CD") == default_risk("GAMEYA") == LOW
    assert default_risk("SILVER") == default_risk("REAL_ESTATE") == default_risk("OTHER") == MEDIUM
    assert default_risk("FUND.SOMETHING_NEW") == default_risk(None) == MEDIUM
    # A class name an older device saved counts as that class's level; a level is kept as it is.
    assert risk_of("STOCK", "Money Market Fund", {"Money Market Fund": "FUND.MONEY_MARKET"}) == LOW
    assert risk_of("STOCK", LOW) == LOW and risk_of("STOCK", None) == HIGH


def test_a_money_market_fund_counts_toward_low_risk_and_a_stock_can_be_moved(c, setup):
    accounts, _ = setup
    thndr = accounts["thndr"].id
    c.transactions.record_transfer("2026-09-02", accounts["cib"].id, thndr, "30000")
    stock = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI")
    money = c.assets.create_investment("Azimut Money Market", "FUND.MONEY_MARKET", "AZ MM")
    c.investments.buy("2026-09-10", thndr, stock.id, "100", "60")
    c.investments.buy("2026-09-10", thndr, money.id, "100", "40")
    c.investments.set_target_weight(LOW, D("50"))
    client = TestClient(create_app(c), base_url="http://127.0.0.1")

    from lightning.ui.routes.investments import target_plan
    rows = {r["name"]: r for r in target_plan(c)["rows"]}
    assert [r for r in rows] == [LOW, MEDIUM, HIGH]
    # 6,000 in the stock, 4,000 in the money market fund and 5,000 in the CD account (low risk, by its account).
    assert rows[LOW]["current"] == 60 and rows[HIGH]["current"] == 40 and rows[LOW]["difference"] == -10
    assert [m["name"] for m in rows[LOW]["holdings"]] == ["CIB CD", "Azimut Money Market"]
    assert rows[LOW]["holdings"][0]["asset_id"] is None  # cash in a deposit has no holding page to move it on

    # Move the stock to low risk on its own page: it now counts toward the low-risk target.
    moved = client.post(f"/investments/asset-plan/{stock.id}", data={"allocation_bucket": LOW, "investment_horizon": ""})
    assert moved.status_code == 200
    assert c.assets.investment_preferences(stock.id)[0] == LOW
    rows = {r["name"]: r for r in target_plan(c)["rows"]}
    assert rows[LOW]["current"] == 100 and rows[HIGH]["current"] == 0
    holding = client.get(f"/investments/holding/{stock.id}").text
    assert "Risk level" in holding and f'value="{LOW}" selected' in holding

    # Back to its class's level: nothing is kept, so it follows its class again.
    client.post(f"/investments/asset-plan/{stock.id}", data={"allocation_bucket": HIGH, "investment_horizon": ""})
    assert c.db.scalar("SELECT allocation_bucket FROM financial_assets WHERE id=?", (stock.id,)) is None
    bad = client.post(f"/investments/asset-plan/{stock.id}", data={"allocation_bucket": "Stocks", "investment_horizon": ""})
    assert "Choose Low risk, Medium risk or High risk." in bad.text and c.assets.investment_preferences(stock.id)[0] == HIGH


def test_an_older_profile_adds_its_class_targets_up_into_levels(monkeypatch, tmp_path):
    from lightning.database import migrator
    from lightning.database.connection import Database
    from lightning.database.seed import seed

    old = tmp_path / "migrations_82"
    old.mkdir()
    for path in migrator.MIGRATIONS_DIR.glob("*.sql"):
        if int(path.name[:4]) <= 82:
            shutil.copy(path, old / path.name)
    bundled = migrator.MIGRATIONS_DIR
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", old)
    db = Database(tmp_path / "old.db")
    migrator.migrate(db)
    seed(db)
    cls = {row["code"]: row["id"] for row in db.all("SELECT id,code FROM asset_classes")}
    for name, code, weight in (("Stocks", "STOCK", 40), ("Fixed Income Fund", "FUND.FIXED_INCOME", 30),
                               ("Money Market Fund", "FUND.MONEY_MARKET", 10), ("Gold", "GOLD", 20)):
        db.execute("INSERT INTO investment_targets(bucket,target_weight,updated_at,asset_class_id) VALUES(?,?,?,?)",
                   (name, weight, "2026-10-01", cls[code]))
    from lightning.assets.service import AssetService
    assets = AssetService(db)
    stock = assets.create_investment("Alpha", "STOCK", "ALPH")
    fund = assets.create_investment("Beta Money", "FUND.MONEY_MARKET", "BETA")
    gold = assets.create_investment("Gold 21K", "GOLD", karat="21")
    db.execute("UPDATE financial_assets SET allocation_bucket='Fixed Income Fund' WHERE id=?", (stock.id,))
    db.execute("UPDATE financial_assets SET allocation_bucket='Fixed Income Fund' WHERE id=?", (fund.id,))
    db.execute("UPDATE financial_assets SET allocation_bucket='Gold' WHERE id=?", (gold.id,))

    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", bundled)
    migrator.migrate(db)
    targets = {row["bucket"]: row["target_weight"] for row in db.all("SELECT bucket,target_weight FROM investment_targets")}
    assert targets == {HIGH: 40, LOW: 40, MEDIUM: 20}
    buckets = {row["id"]: row["allocation_bucket"] for row in db.all("SELECT id,allocation_bucket FROM financial_assets")}
    assert buckets[stock.id] == LOW  # moved to a fixed income class before: it stays in low risk
    assert buckets[fund.id] is None and buckets[gold.id] is None  # already its class's level
    migrator.migrate(db)  # a second run changes nothing
    assert {row["bucket"] for row in db.all("SELECT bucket FROM investment_targets")} == {HIGH, LOW, MEDIUM}
    db.close()
