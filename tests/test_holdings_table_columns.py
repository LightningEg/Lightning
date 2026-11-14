"""Holdings table: average cost and price now per holding, in the profile currency (owner, 2026-11-14)."""
from decimal import Decimal as D

from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def test_table_shows_average_cost_and_price_now(c, setup):
    accounts, _ = setup
    comi = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI")
    c.transactions.record_transfer("2025-01-02", accounts["cib"].id, accounts["thndr"].id, "30000")
    account = accounts["thndr"].id
    c.investments.buy_total("2025-01-10", account, comi.id, "10", "1000")
    c.investments.buy_total("2025-07-10", account, comi.id, "10", "1200")
    c.assets.set_price(comi.id, "2026-01-10", "150")
    html = TestClient(create_app(c)).get("/investments?end=2026-01-10").text
    table = html.split('id="holdings-table"')[1].split("</table>")[0]
    head = table.split("</thead>")[0]
    assert "Avg cost" in head and "Price now" in head and "XIRR" not in head
    assert D("2200") / 20 == D("110") and ">110<" in table and ">150<" in table
