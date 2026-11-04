"""Real ledger histories expose return uncertainty without changing money or plain returns."""
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.ui.web import create_app


@pytest.fixture
def ambiguous_holding(c, request):
    sale, purchase = getattr(request, "param", ("230", "232.16"))
    broker = c.account_flows.open_account("Return audit", "BROKERAGE", "2024-01-01", "1000")
    stock = c.assets.create_investment("Return audit stock", "STOCK", "AUDIT")
    c.investments.buy_total("2024-01-01", broker.id, stock.id, "1", "100")
    c.investments.sell_total("2024-12-31", broker.id, stock.id, "1", sale)
    c.investments.buy_total("2025-12-31", broker.id, stock.id, "1", purchase)
    c.assets.set_price(stock.id, "2025-12-31", "100")
    return broker, stock


def test_real_repurchase_history_is_ambiguous_and_reads_preserve_ledger(c, ambiguous_holding):
    broker, stock = ambiguous_holding
    before = [tuple(r) for r in c.db.execute("SELECT * FROM ledger_entries ORDER BY id").fetchall()]
    p = c.investments.portfolio("2025-12-31", broker.id)
    h = next(h for h in p.positions if h.asset_id == stock.id)
    assert (h.quantity, h.cost_basis, h.value, h.realized, h.unrealized) == (
        D(1), D("232.16"), D(100), D(130), D("-132.16"))
    for result in (p, h):
        assert result.xirr is None
        assert result.display_return.status == "ambiguous"
        assert result.display_return.reason == "multiple_roots"
        assert result.display_return.percent is None
    assert c.reporting.account_balance(broker.id, "2025-12-31") == D("897.84")
    assert before == [tuple(r) for r in c.db.execute("SELECT * FROM ledger_entries ORDER BY id").fetchall()]


@pytest.mark.parametrize("ambiguous_holding", [("230", "232.16"), ("50", "200")], indirect=True)
@pytest.mark.parametrize("phone", [False, True])
@pytest.mark.parametrize("locale", ["en", "ar"])
def test_ambiguity_is_explained_on_portfolio_and_holding(c, ambiguous_holding, phone, locale):
    broker, stock = ambiguous_holding
    client = TestClient(create_app(c))
    client.post("/settings/locale", data={"locale": locale}, follow_redirects=False)
    headers = {"user-agent": "Mozilla/5.0 (iPhone)"} if phone else {}
    expected = ("More than one annualized return fits these cash flows." if locale == "en"
                else "فيه أكتر من عائد سنوي ينطبق على التدفقات النقدية دي.")
    if c.investments.portfolio("2025-12-31", broker.id).display_return.status == "unavailable":
        expected = ("These cash flows have no annualized return." if locale == "en"
                    else "التدفقات النقدية دي ملهاش عائد سنوي قابل للحساب.")
    for url in ("/investments?period=custom&date_from=2024-01-01&date_to=2025-12-31",
                f"/investments/holding/{stock.id}?account={broker.id}&date=2025-12-31"):
        response = client.get(url, headers=headers)
        assert response.status_code == 200
        assert expected in response.text, (url, c.investments.portfolio("2025-12-31").display_return)
