"""NF-12M: property as an investment: Real estate class, gain from what you paid, its own page, instalments, rent and costs."""
from __future__ import annotations

import re
import shutil
from decimal import Decimal

from fastapi.testclient import TestClient

from lightning.ui.web import create_app

D = Decimal


def _text(page: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page)).replace("−", "-")


def _flat(c, opening="0", kind="flat", price="1800000"):
    """The audit's flat (r30 P1): valued at 2,500,000, bought for 1,800,000."""
    flat = c.account_flows.open_account("Flat", "OTHER_ASSET", "2025-01-01", opening)
    c.accounts.save_other_asset_value(c.accounts.get(flat.id), "2026-06-01", "2500000")
    c.accounts.save_other_asset_details(c.accounts.get(flat.id), kind, "2025-03-01", price, "")
    return c.accounts.get(flat.id)


def _with_a_stock(c):
    broker = c.account_flows.open_account("Broker", "BROKERAGE", "2025-01-01", "50000")
    asset = c.assets.create_investment("Comi", "STOCK", "COMI")
    c.investments.buy("2025-02-01", broker.id, asset.id, "100", "100")


# -- 12M1 ---------------------------------------------------------------------------------------------------------
def test_a_flat_is_real_estate_with_cost_value_and_gain_on_investments(c):
    _flat(c)
    _with_a_stock(c)
    page = _text(TestClient(create_app(c)).get("/investments").text)
    assert "Real estate 1,800,000 2,500,000 +700,000" in page
    assert "Flat 1,800,000 2,500,000 +700,000 +38.9%" in page
    assert "Other Investments" not in page


def test_the_gain_is_in_the_lead_not_valued_by_you(c):
    _flat(c)
    _with_a_stock(c)
    from lightning.investments import owned
    day = "2026-11-12"
    p, prior = c.investments.portfolio(day), c.investments.portfolio("2026-10-31")
    own = owned.owned_portfolio(c.reporting, c.money_from_others, {}, p, prior, day, "2026-10-31", D(0))
    lead = c.position.investment_breakdown(day, own.owned_rows, {}).lead
    assert lead.cost == D("1810000") and lead.unrealized == D("700000") and lead.valued_by_you == 0
    assert lead.value == lead.cost + lead.unrealized + lead.valued_by_you


def test_a_property_is_not_counted_as_sold_today_unless_you_set_a_factor(c):
    _flat(c)
    position = c.position.at()
    real_estate = next(cls for cls in position.classes if cls.code == "REAL_ESTATE")
    assert real_estate.value == D("2500000") and real_estate.after_sale == 0
    c.investments.set_liquidation_factor(real_estate.id, "80")
    again = next(cls for cls in c.position.class_values("2026-11-12")[0] if cls.code == "REAL_ESTATE")
    assert again.after_sale == D("2000000")


def test_a_car_and_a_flat_with_no_price_keep_their_place(c):
    car = c.account_flows.open_account("Car", "OTHER_ASSET", "2025-01-01", "0")
    c.accounts.save_other_asset_value(c.accounts.get(car.id), "2026-06-01", "500000")
    c.accounts.save_other_asset_details(c.accounts.get(car.id), "car", "2025-03-01", "600000", "")
    land = _flat(c, kind="land", price="")
    rows = {h.account.id: h for h in c.reporting.holdings("2026-11-12")[0]}
    assert rows[car.id].asset_class_code == "OTHER" and rows[car.id].cost is None
    assert rows[land.id].asset_class_code == "REAL_ESTATE" and rows[land.id].cost is None


def test_net_worth_is_unchanged_by_the_class(c):
    flat = _flat(c)
    worth = c.reporting.net_worth("2026-11-12")
    assert worth.total == D("2500000")
    assert [g.code for g in worth.by_class] == ["REAL_ESTATE"]
    assert flat.id


def test_an_older_profile_upgrades_and_takes_the_real_estate_class(monkeypatch, tmp_path):
    from lightning.database import migrator
    from lightning.database.connection import Database

    old = tmp_path / "migrations_78"
    old.mkdir()
    for path in migrator.MIGRATIONS_DIR.glob("*.sql"):
        if int(path.name[:4]) <= 78:
            shutil.copy(path, old / path.name)
    bundled = migrator.MIGRATIONS_DIR
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", old)
    db = Database(tmp_path / "old.db")
    migrator.migrate(db)
    before = db.scalar("SELECT COUNT(*) FROM asset_classes")
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", bundled)
    migrator.migrate(db)
    assert db.scalar("SELECT name FROM asset_classes WHERE code='REAL_ESTATE'") == "Real estate"
    assert db.scalar("SELECT COUNT(*) FROM asset_classes") == before + 1
    migrator.migrate(db)
    assert db.scalar("SELECT COUNT(*) FROM asset_classes") == before + 1
    db.close()
