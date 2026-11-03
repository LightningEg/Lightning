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
