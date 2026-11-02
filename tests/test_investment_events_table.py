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
