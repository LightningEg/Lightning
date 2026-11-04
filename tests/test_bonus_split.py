"""NF-5E: bonus shares, a split and a reverse split change the units and never the cost; no purchase appears."""
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.investments.report import build_investment_report
from lightning.ui.web import create_app


@pytest.fixture
def share(c, setup):
    accounts, _ = setup
    comi = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI")
    c.transactions.record_transfer("2026-01-02", accounts["cib"].id, accounts["thndr"].id, "30000")
    broker = accounts["thndr"].id
    c.investments.buy("2026-02-01", broker, comi.id, "100", "10")  # 1,000 in total
    return c, broker, comi


def position(c, broker, comi, day="2026-12-31"):
    return next(p for p in c.investments.portfolio(day, broker).positions if p.asset_id == comi.id)


def test_a_one_for_four_bonus_keeps_the_cost_and_lowers_the_average(share):
    c, broker, comi = share
    c.investments.bonus_or_split("2026-03-01", broker, comi.id, "125")
    p = position(c, broker, comi)
    assert (p.quantity, p.cost_basis, p.average_cost) == (D("125"), D("1000"), D("8"))
    assert p.invested == D("1000") and p.realized == D(0)  # no purchase appeared


def test_a_reverse_split_takes_units_away_and_keeps_the_cost(share):
    c, broker, comi = share
    c.investments.bonus_or_split("2026-03-01", broker, comi.id, "25")
    p = position(c, broker, comi)
    assert (p.quantity, p.cost_basis, p.average_cost) == (D("25"), D("1000"), D("40"))


@pytest.mark.parametrize("method", ["average", "fifo"])
def test_a_sale_after_the_split_gives_the_right_gain(share, method):
    c, broker, comi = share
    c.accounts.set_cost_method(broker, method)
    c.investments.bonus_or_split("2026-03-01", broker, comi.id, "125")
    c.investments.sell("2026-04-01", broker, comi.id, "25", "12")  # 25 units cost 8 each = 200; proceeds 300
    p = position(c, broker, comi)
    assert (p.quantity, p.cost_basis, p.realized) == (D("100"), D("800"), D("100"))
    report = build_investment_report(c.db, c.accounts, c.assets, c.reporting, "2026-04-01", "2026-04-30")
    assert report["realized"] == D("100")


def test_fifo_spreads_the_new_units_over_every_open_purchase(share):
    c, broker, comi = share
    c.accounts.set_cost_method(broker, "fifo")
    c.investments.buy("2026-02-15", broker, comi.id, "100", "20")  # 2,000
    c.investments.bonus_or_split("2026-03-01", broker, comi.id, "250")  # 1-for-4 on 200 units, then +0
    p = position(c, broker, comi)
    assert [(lot.quantity, lot.cost) for lot in p.lots] == [(D("125"), D("1000")), (D("125"), D("2000"))]


def test_the_split_moves_no_money_for_xirr_or_the_report(share):
    c, broker, comi = share
    before = position(c, broker, comi, "2026-03-01")
    c.investments.bonus_or_split("2026-03-01", broker, comi.id, "125")
    c.assets.set_price(comi.id, "2026-12-30", "8")
    after = position(c, broker, comi)
    assert after.value == D("1000") and before.value == D("1000")
    assert after.xirr is None or abs(after.xirr) < D("0.0001")  # same money in, same value: no return from the split
    report = build_investment_report(c.db, c.accounts, c.assets, c.reporting, "2026-03-01", "2026-03-31")
    assert report["new_money"] == D(0) and report["realized"] == D(0)


def test_it_needs_units_held_and_a_different_number(share):
    c, broker, comi = share
    with pytest.raises(ValidationError):
        c.investments.bonus_or_split("2026-03-01", broker, comi.id, "100")  # no change
    with pytest.raises(ValidationError):
        c.investments.bonus_or_split("2026-01-15", broker, comi.id, "125")  # nothing held yet that day
    with pytest.raises(ValidationError):
        c.investments.bonus_or_split("2026-03-01", broker, comi.id, "0")


def test_the_split_edits_and_voids_like_any_event(share):
    c, broker, comi = share
    txn = c.investments.bonus_or_split("2026-03-01", broker, comi.id, "125")
    assert c.investments.values_of(txn.id)["kind"] == "bonus_or_split"
    c.investments.update(txn.id, date="2026-03-01", account_id=broker, asset_id=comi.id, quantity="150", notes="")
    assert position(c, broker, comi).quantity == D("150")
    c.transactions.void(txn.id)
    assert position(c, broker, comi).quantity == D("100")


def test_the_holding_chart_does_not_fall_off_a_cliff(share):
    from datetime import date
    from lightning.investments.journey import holding_history
    c, broker, comi = share
    c.assets.set_price(comi.id, "2026-02-28", "10")
    c.investments.bonus_or_split("2026-03-10", broker, comi.id, "125")
    c.assets.set_price(comi.id, "2026-03-31", "8")
    history = holding_history(c.reporting, c.investments, broker, comi.id, date(2026, 3, 31), months=2)
    assert history["price"] == [D("8"), D("8")]  # February's 10 is shown as 8: the same worth per new unit
    assert any(step["kind"] == "Bonus or split" for step in history["trades"])


def test_the_form_records_it_and_the_journal_carries_it(share):
    c, broker, comi = share
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    page = client.get(f"/investments/new?kind=bonus_or_split&account={broker}")
    assert "Units you hold after it" in page.text
    client.post("/investments/new?kind=bonus_or_split", data={
        "date": "2026-03-01", "account_id": str(broker), "asset_id": str(comi.id), "quantity": "125", "notes": ""})
    assert position(c, broker, comi).quantity == D("125")
