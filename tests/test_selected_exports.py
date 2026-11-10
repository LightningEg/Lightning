"""Selected exports contain precisely the requested records and safe CSV text."""

import csv
import asyncio
from io import StringIO
from urllib.parse import urlencode

import pytest
from starlette.requests import Request

from lightning.core.errors import ValidationError
from lightning.ui.routes import exports
from lightning.ui.web import create_app


def _rows(response):
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    return list(csv.DictReader(StringIO(response.body.decode("utf-8-sig"))))


def _post(c, path, data):
    body = urlencode(data).encode()
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request({"type": "http", "method": "POST", "path": path,
                       "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
                       "app": create_app(c)}, receive)
    handler = {"transactions": exports.transactions, "categories": exports.categories,
               "reevaluations": exports.reevaluations}[path.rsplit("/", 1)[-1]]
    return asyncio.run(handler(request))


def test_transaction_export_is_selected_and_keeps_ledger_detail(c):
    account = c.account_flows.open_account("CIB Current", "BANK", "2026-09-01", "5000")
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    first = c.transactions.record_outflow("2026-09-25", account.id, "1234.56",
                                          food.id, description="=SUM(1,2)")
    second = c.transactions.record_outflow("2026-09-26", account.id, "2", food.id)
    rows = _rows(_post(c, "/exports/transactions", {"txn_ids": str(first.id)}))
    assert {row["transaction_id"] for row in rows} == {str(first.id)}
    assert second.ref not in {row["reference"] for row in rows}
    assert any(row["amount"] == "-1234.56" for row in rows)
    assert any(row["description"] == "'=SUM(1,2)" for row in rows)
    with pytest.raises(ValidationError):
        _post(c, "/exports/transactions", {})


def test_category_export_keeps_parent_and_flags(c):
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    rows = _rows(_post(c, "/exports/categories", {"category_ids": str(food.id)}))
    assert len(rows) == 1
    assert rows[0]["category_id"] == str(food.id)
    assert rows[0]["parent"] == "Personal"
    assert rows[0]["direction"] == "OUT"
    assert rows[0]["active"] == "yes"


def test_reevaluation_export_is_selected_and_linked(c):
    account = c.account_flows.open_account("Broker", "BROKERAGE", "2026-09-01", "1000")
    first = c.assets.create_investment("First fund", "FUND.EQUITY", "F1")
    second = c.assets.create_investment("Second fund", "FUND.EQUITY", "F2")
    c.investments.add_holding(account.id, first.id, "1", "100", "2026-09-01")
    c.investments.add_holding(account.id, second.id, "1", "100", "2026-09-01")
    c.assets.set_price(first.id, "2026-09-30", "120")
    c.assets.set_price(second.id, "2026-09-30", "130")
    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")
    history = c.reevaluations.history()
    assert len(history) == 2
    rows = _rows(_post(c, "/exports/reevaluations", {"entry_ids": str(history[0]["id"])}))
    assert len(rows) == 1
    assert rows[0]["entry_id"] == str(history[0]["id"])
    assert rows[0]["journal_reference"] == history[0]["ref"]
    assert rows[0]["asset"] == history[0]["asset_name"]
    with pytest.raises(ValidationError):
        _post(c, "/exports/reevaluations", {"entry_ids": "999999"})

