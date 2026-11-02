"""The events table (NF-5A1): buy, sell and dividend each have one row; one builder and one validator read it."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from lightning.core.errors import ValidationError
from lightning.core.ledger import Effect
from lightning.core.refs import DocType
from lightning.investments import events
from lightning.investments.events import EVENTS, EventValues, Sign, lines_for, validate

D = Decimal
ASSET = SimpleNamespace(id=7, code="COMI", unit="share", quantity_decimals=0)
ACCOUNT = SimpleNamespace(id=3)
CASH = {events.DIVIDEND_CATEGORY: 11, events.TAX_CATEGORY: 12}


def values(**kw):
    base = dict(asset=ASSET, account=ACCOUNT, cash_asset_id=1, category_ids=CASH)
    return EventValues(**{**base, **kw})


def test_table_rows_describe_each_event():
    assert EVENTS["buy"].doc_type == DocType.BUY and EVENTS["buy"].units == Sign.IN and EVENTS["buy"].fees == "cost"
    assert EVENTS["sell"].units == Sign.OUT and EVENTS["sell"].cash == Sign.IN and EVENTS["sell"].fees == "proceeds"
    assert EVENTS["dividend"].units == Sign.NONE and EVENTS["dividend"].income_category == events.DIVIDEND_CATEGORY


def test_buy_lines_add_fee_to_cost():
    cash, units = lines_for("buy", values(quantity="10", price="50", fees="5"))
    assert (cash.quantity, units.quantity, units.amount) == (D("-505"), D("10"), D("505"))
    assert cash.effect == units.effect == Effect.INTERNAL


def test_sell_lines_take_fee_from_proceeds():
    units, cash = lines_for("sell", values(quantity="10", price="50", fees="5"))
    assert (units.quantity, units.amount, cash.quantity) == (D("-10"), D("-495"), D("495"))


def test_dividend_lines_post_gross_and_tax():
    income, tax = lines_for("dividend", values(amount="200", tax="20"))
    assert (income.quantity, income.category_id) == (D("200"), 11)
    assert (tax.quantity, tax.category_id) == (D("-20"), 12)


@pytest.mark.parametrize("event,kw,field", [
    ("buy", dict(quantity="0", price="5"), "quantity"),
    ("buy", dict(quantity="1", price="0"), "price"),
    ("buy", dict(quantity="1", price="5", fees="-1"), "fees"),
    ("sell", dict(quantity="1", price="5", fees="9"), "fees"),
    ("dividend", dict(amount="0"), "amount"),
    ("dividend", dict(amount="10", tax="10"), "tax"),
])
def test_validator_refuses_bad_numbers(event, kw, field):
    with pytest.raises(ValidationError) as error:
        validate(event, values(**kw))
    assert error.value.field == field


def test_unknown_event_is_refused():
    with pytest.raises(ValidationError):
        lines_for("split", values())


def test_service_wrappers_go_through_the_one_record_path(c, setup):
    """buy, sell and dividend are wrappers: record(event, ...) posts the same documents (NF-5A2)."""
    accounts, _ = setup
    thndr = accounts["thndr"]
    c.transactions.record_transfer("2026-09-02", accounts["cib"].id, thndr.id, "30000")
    comi = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI")
    bought = c.investments.record("buy", "2026-09-03", thndr.id, comi.id, quantity="10", price="50", fees="5")
    assert bought.type == DocType.BUY and sorted(ln.quantity for ln in bought.lines) == [D("-505"), D("10")]
    sold = c.investments.record("sell", "2026-09-04", thndr.id, comi.id, quantity="2", price="60")
    assert sold.type == DocType.SEL
    paid = c.investments.record("dividend", "2026-09-05", thndr.id, comi.id, amount="100", tax="10")
    assert paid.type == DocType.DIV and sorted(ln.quantity for ln in paid.lines) == [D("-10"), D("100")]
    with pytest.raises(ValidationError) as error:
        c.investments.record("nonsense", "2026-09-05", thndr.id, comi.id)
    assert error.value.field == "event"
    assert not hasattr(c.investments, "_trade_lines") and not hasattr(c.investments, "_dividend_lines")


def test_form_fields_come_from_the_spec():
    buy, sell, div = (events.form_fields(k) for k in ("buy", "sell", "dividend"))
    assert (buy.units, buy.fees, buy.cash_account, buy.cash_from, buy.income) == (True, True, True, True, False)
    assert (sell.cash_from, sell.income) == (False, False)
    assert (div.units, div.fees, div.cash_account, div.income) == (False, False, False, True)


def test_entry_form_shows_only_what_the_spec_enables(c, monkeypatch):
    """The template reads the spec: a row without fees shows no fee field, with no template change (NF-5A3)."""
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from lightning.ui.web import create_app

    client = TestClient(create_app(c))
    buy = client.get("/investments/new?kind=buy").text
    assert 'name="fees"' in buy and 'name="cash_account_id"' in buy and 'name="amount"' not in buy
    dividend = client.get("/investments/new?kind=dividend").text
    assert 'name="amount"' in dividend and 'name="fees"' not in dividend and 'name="cash_account_id"' not in dividend
    monkeypatch.setitem(EVENTS, "buy", replace(EVENTS["buy"], fees="none"))
    bare = client.get("/investments/new?kind=buy").text
    assert 'name="fees"' not in bare and 'name="fees_included"' not in bare and 'name="cash_account_id"' in bare


# -- NF-5A4: reinvested dividend -----------------------------------------------------------------------------
def test_reinvested_dividend_lines_are_income_tax_then_units_for_the_net():
    income, tax, spend, units = lines_for("reinvested_dividend", values(amount="200", tax="20", quantity="4"))
    assert (income.quantity, income.effect, income.category_id) == (D("200"), Effect.INFLOW, 11)
    assert (tax.quantity, tax.effect, tax.category_id) == (D("-20"), Effect.OUTFLOW, 12)
    assert (spend.quantity, spend.effect) == (D("-180"), Effect.INTERNAL)
    assert (units.quantity, units.amount, units.unit_price, units.effect) == (D("4"), D("180"), D("45"), Effect.INTERNAL)
    assert EVENTS["reinvested_dividend"].doc_type == DocType.DIV


@pytest.mark.parametrize("kw,field", [
    (dict(amount="200", quantity="0"), "quantity"), (dict(amount="200"), "quantity"),
    (dict(amount="0", quantity="1"), "amount"), (dict(amount="10", tax="10", quantity="1"), "tax"),
    (dict(amount="0.01", quantity="100000000"), "quantity"),
])
def test_reinvested_dividend_refuses_bad_numbers(kw, field):
    with pytest.raises(ValidationError) as error:
        validate("reinvested_dividend", values(**kw))
    assert error.value.field == field


def _held(c, setup):
    accounts, _ = setup
    thndr = accounts["thndr"]
    c.transactions.record_transfer("2026-09-02", accounts["cib"].id, thndr.id, "30000")
    comi = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI")
    c.investments.buy("2026-09-03", thndr.id, comi.id, "100", "50")  # 5,000
    return thndr, comi


def test_reinvested_dividend_posts_one_document_and_every_screen_agrees(c, setup):
    from lightning.investments.report import investment_period
    thndr, comi = _held(c, setup)
    cash_before = c.reporting.account_balance(thndr.id, "2026-10-01")
    txn = c.investments.record("reinvested_dividend", "2026-10-01", thndr.id, comi.id, amount="200", tax="20",
                               quantity="4")
    assert txn.type == DocType.DIV and len(txn.lines) == 4
    assert c.reporting.account_balance(thndr.id, "2026-10-31") == cash_before  # net bought units; tax was income's
    position = next(p for p in c.investments.portfolio("2026-10-31", thndr.id).positions if p.asset_id == comi.id)
    assert (position.quantity, position.cost_basis, position.dividends, position.dividend_tax) == (
        D("104"), D("5180"), D("200"), D("20"))
    report = investment_period(c.db, c.accounts, c.assets, c.reporting, "2026-09-01", "2026-12-31")
    held = next(h for h in report["holdings"] if h["asset_id"] == comi.id)
    assert (held["units"], held["cost"], report["dividends"], report["tax"]) == (D("104"), D("5180"), D("200"), D("20"))
    assert report["unresolved_dividends"] == 0


def test_reinvested_dividend_sells_at_the_blended_cost_and_edits_in_place(c, setup):
    thndr, comi = _held(c, setup)
    txn = c.investments.record("reinvested_dividend", "2026-10-01", thndr.id, comi.id, amount="200", tax="0",
                               quantity="4")
    c.investments.update(txn.id, account_id=thndr.id, asset_id=comi.id, amount="300")  # units stay, cost follows
    assert c.investments.values_of(txn.id)["quantity"] == D("4")
    c.investments.sell("2026-10-02", thndr.id, comi.id, "104", "60")  # cost 5,300 -> proceeds 6,240
    position = next(p for p in c.investments.portfolio("2026-10-31", thndr.id).positions if p.asset_id == comi.id)
    assert (position.quantity, position.realized) == (D("0"), D("940"))
    stored = c.investments.values_of(txn.id)
    assert (stored["kind"], stored["amount"], stored["tax"], stored["quantity"]) == ("dividend", D("300"), D("0"), D("4"))
    with pytest.raises(ValidationError):
        c.investments.update(txn.id, account_id=thndr.id, asset_id=comi.id, amount="0")


def test_holding_journey_lists_a_reinvested_dividend_once(c, setup):
    from datetime import date

    from lightning.investments.journey import holding_history
    thndr, comi = _held(c, setup)
    c.investments.record("reinvested_dividend", "2026-10-01", thndr.id, comi.id, amount="200", quantity="4")
    trail = holding_history(c.reporting, c.investments, thndr.id, comi.id, date(2026, 10, 31))["trades"]
    row = [t for t in trail if t["kind"] == "Dividend reinvested"]
    assert len(row) == 1 and row[0]["units"] == D("4") and row[0]["held"] == D("104")
    assert [t["kind"] for t in trail].count("Dividend") == 1  # the income row, with no units
