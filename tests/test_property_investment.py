"""NF-12M: property as an investment: Real estate class, gain from what you paid, its own page, instalments, rent and costs."""
from __future__ import annotations

import re
import shutil
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError

from lightning.ui.web import create_app

from test_journal_finance import devices  # noqa: F401
from test_journal_screens import screens  # noqa: F401
from tests.screens import said

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
    # Real estate (0079) and Cloud (0082) are the two classes added after migration 78.
    assert db.scalar("SELECT COUNT(*) FROM asset_classes") == before + 2
    migrator.migrate(db)
    assert db.scalar("SELECT COUNT(*) FROM asset_classes") == before + 2
    db.close()


# -- 12M3 ---------------------------------------------------------------------------------------------------------
def _off_plan(c):
    """A flat bought off plan: 3,000,000, 600,000 paid down; 24 monthly instalments of 100,000 from the bank."""
    bank = c.account_flows.open_account("Bank", "BANK", "2025-01-01", "1000000")
    flat = c.account_flows.open_account("New flat", "OTHER_ASSET", "2026-01-01", "600000")
    c.accounts.save_other_asset_details(c.accounts.get(flat.id), "flat", "2026-01-01", "3000000", "")
    item = c.property.save_contract(flat.id, "100000", "MONTHLY", "2026-02-01", "24", bank.id)
    return bank, c.accounts.get(flat.id), item


def test_an_instalment_is_a_transfer_that_raises_what_you_paid(c):
    bank, flat, item = _off_plan(c)
    before = c.reporting.net_worth("2026-11-12").total
    holding = next(h for h in c.reporting.holdings("2026-11-12")[0] if h.account.id == flat.id)
    assert holding.asset_class_code == "REAL_ESTATE" and holding.cost == D("600000") and holding.value == D("600000")
    c.property.pay_instalment(flat.id, "2026-02-01", "2026-02-01", "", "")
    holding = next(h for h in c.reporting.holdings("2026-11-12")[0] if h.account.id == flat.id)
    assert holding.cost == D("700000") and holding.value == D("700000")
    assert c.reporting.net_worth("2026-11-12").total == before  # a transfer: net worth never moves
    progress = c.property.contract(flat.id, D("700000"))
    assert progress["left"] == D("2300000") and progress["done"] == 1 and progress["count"] == 24
    with pytest.raises(ValidationError):
        c.property.pay_instalment(flat.id, "2026-02-01", "2026-02-02", "", "")  # paid already


def test_the_unpaid_part_is_not_a_debt_but_coming_instalments_are_in_the_forecast(c):
    bank, flat, item = _off_plan(c)
    owe = c.planning.what_you_owe(date(2026, 1, 15))
    assert owe.total == 0  # nothing is due yet: the 2,400,000 still to pay is no debt
    upcoming = [p for p in c.planning.all_payments("2026-04-30", date(2026, 1, 15)) if p.item.id == item]
    assert [p.due_date for p in upcoming] == ["2026-02-01", "2026-03-01", "2026-04-01"]
    assert all(p.amount == D("100000") for p in upcoming)


def test_an_instalment_cannot_be_paid_as_spending_from_cash_planning(c):
    bank, flat, item = _off_plan(c)
    with pytest.raises(ValidationError, match="property's page"):
        c.planning.record_payment(item, "2026-02-01", "2026-02-01", "100000", bank.id)


def test_a_contract_needs_a_property_and_its_price(c):
    bank = c.account_flows.open_account("Bank", "BANK", "2025-01-01", "1000")
    car = c.account_flows.open_account("Car", "OTHER_ASSET", "2025-01-01", "0")
    c.accounts.save_other_asset_details(c.accounts.get(car.id), "car", "", "", "")
    with pytest.raises(ValidationError):
        c.property.save_contract(car.id, "100", "MONTHLY", "2026-02-01", "3", bank.id)
    flat = c.account_flows.open_account("Flat", "OTHER_ASSET", "2025-01-01", "0")
    c.accounts.save_other_asset_details(c.accounts.get(flat.id), "flat", "", "", "")
    with pytest.raises(ValidationError, match="contract price"):
        c.property.save_contract(flat.id, "100", "MONTHLY", "2026-02-01", "3", bank.id)


# -- 12M4 ---------------------------------------------------------------------------------------------------------
def test_rent_and_costs_belong_to_the_property_and_give_its_yield_and_return(c):
    from lightning.accounts.property import property_return
    bank = c.account_flows.open_account("Bank", "BANK", "2025-01-01", "100000")
    flat = _flat(c)
    for month in range(1, 11):
        c.property.record_flow(flat.id, "rent", f"2026-{month:02d}-05", "10000", bank.id)
    c.property.record_flow(flat.id, "cost", "2026-06-10", "20000", bank.id, "Maintenance")
    year = c.property.flows(flat.id, "2025-11-13", "2026-11-12")
    assert year["rent"] == D("100000") and year["costs"] == D("20000") and year["net"] == D("80000")
    figures = property_return(D("2500000"), D("1800000"), year, year)
    assert figures["yield_pct"] == D("3.2") and figures["total"] == D("780000")
    assert round(figures["total_pct"], 1) == D("43.3")
    # Rent is investment income, the cost an investment-family outflow: neither is household spending.
    rent = c.categories.get_by_code("EXP.INVEST.RENT")
    assert rent.income_class.value == "INVESTMENT"
    assert c.reporting.account_balance(bank.id, "2026-11-12") == D("180000")


def test_an_older_profile_takes_the_property_tables_and_categories(monkeypatch, tmp_path):
    from lightning.database import migrator
    from lightning.database.connection import Database
    from lightning.database.seed import seed

    old = tmp_path / "migrations_79"
    old.mkdir()
    for path in migrator.MIGRATIONS_DIR.glob("*.sql"):
        if int(path.name[:4]) <= 79:
            shutil.copy(path, old / path.name)
    bundled = migrator.MIGRATIONS_DIR
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", old)
    db = Database(tmp_path / "old.db")
    migrator.migrate(db)
    seed(db)
    db.execute("DELETE FROM categories WHERE code IN ('EXP.INVEST.RENT','EXP.INVEST.PROPERTY')")  # an older seed
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", bundled)
    migrator.migrate(db)
    assert db.scalar("SELECT movement FROM categories WHERE code='EXP.INVEST.RENT'") == "INFLOW"
    assert db.scalar("SELECT family FROM categories WHERE code='EXP.INVEST.PROPERTY'") == "INVESTMENT"
    assert db.scalar("SELECT COUNT(*) FROM property_contracts") == 0
    migrator.migrate(db)
    db.close()


def test_an_instalment_stays_editable_and_plain_transfers_still_cannot_reach_a_property(c):
    bank, flat, item = _off_plan(c)
    txn = c.property.pay_instalment(flat.id, "2026-02-01", "2026-02-01", "", "")
    c.transactions.update_transfer(txn, "2026-02-02", bank.id, flat.id, "90000")
    holding = next(h for h in c.reporting.holdings("2026-11-12")[0] if h.account.id == flat.id)
    assert holding.cost == D("690000")
    other = _flat(c)
    with pytest.raises(ValidationError):
        c.transactions.record_transfer("2026-02-01", bank.id, other.id, "100")


# -- 12M2 and the forms ---------------------------------------------------------------------------------------------
def test_the_property_page_leads_with_its_answer_not_a_register(c):
    flat = _flat(c)
    page = TestClient(create_app(c)).get(f"/accounts/{flat.id}").text
    text = _text(page)
    assert text.index("Value now") < text.index("Estimated value") < text.index("Money in and out")
    assert "+700,000 EGP · +38.9%" in text and "Record rent or a cost" in text and "Paying by instalments" in text
    assert "Find and replace" not in text and "Save this view" not in text and "/import" not in page


def test_the_page_forms_pay_an_instalment_and_record_rent(c):
    bank, flat, item = _off_plan(c)
    client = TestClient(create_app(c))
    page = _text(client.get(f"/accounts/{flat.id}").text)
    assert "Paid so far 600,000 of 3,000,000 EGP" in page and "Left to pay the developer 0 of 24 instalments paid" in page
    assert f"Next instalment {said('2026-02-01')}" in page
    done = client.post(f"/accounts/{flat.id}/instalment", data={"due_date": "2026-02-01", "date": "2026-02-01"},
                       follow_redirects=False)
    assert done.status_code == 303 and "Instalment%20paid" in done.headers["location"]
    rent = client.post(f"/accounts/{flat.id}/property-flow", data={
        "kind": "rent", "date": "2026-03-05", "amount": "8000", "cash_account_id": str(bank.id)}, follow_redirects=False)
    assert "Rent%20saved" in rent.headers["location"]
    page = _text(client.get(f"/accounts/{flat.id}").text)
    assert "Paid so far 700,000 of 3,000,000 EGP" in page and "1 of 24 instalments paid" in page
    assert "Rent less costs, last 12 months" in page and "Total return" in page
    refused = client.post(f"/accounts/{flat.id}/contract", data={"instalment": "100", "frequency": "WEEKLY",
                          "first_date": "2026-02-01", "payment_count": "3", "funding_account_id": str(bank.id)},
                          follow_redirects=False)
    assert "msg=" in refused.headers["location"]


def test_property_actions_travel_as_portable_commands(screens):
    from lightning.sync.journal.codec import unpack
    from lightning.sync.journal.proxy import JournalServices

    (hd, pc), (_, replica) = screens
    home = JournalServices(hd)
    home.account_flows.open_account("Builder bank", "BANK", "2026-01-01", "500000")
    flat = home.account_flows.open_account("Off-plan flat", "OTHER_ASSET", "2026-01-01", "600000")
    home.accounts.save_other_asset_details(hd.c.accounts.get(flat.id), "flat", "2026-01-01", "3000000", "")
    pc.sync_with(hd.home)
    flat_pc = next(a for a in pc.c.accounts.list() if a.name == "Off-plan flat")
    bank_pc = next(a for a in pc.c.accounts.list() if a.name == "Builder bank")
    response = replica.post(f"/accounts/{flat_pc.id}/contract", data={
        "instalment": "100000", "frequency": "MONTHLY", "first_date": "2026-02-01", "payment_count": "24",
        "funding_account_id": str(bank_pc.id)})
    assert response.status_code == 303 and "Saved+on+this+device" in response.headers["location"]
    assert unpack(pc.store.pending()[0])["body"]["kind"] == "command.property.save_contract"
    pc.sync_with(hd.home)
    flat_home = next(a for a in hd.c.accounts.list() if a.name == "Off-plan flat")
    assert hd.c.property.contract_item(flat_home.id) is not None
    assert pc.store.fingerprint() == hd.store.fingerprint()
