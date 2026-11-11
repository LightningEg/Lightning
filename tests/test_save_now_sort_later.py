"""NF-7AN: at the till the person knows only the amount. Money out or in saves without a category as To sort
(filed Unaccounted), Home's To do counts it with its total, and sorting it later moves it into its category."""
from __future__ import annotations

from decimal import Decimal as D

from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def test_an_amount_alone_saves_as_to_sort_and_is_counted_until_sorted(c, setup):
    accounts, _ = setup
    cib = accounts["cib"].id
    before = c.reporting.account_balance(cib)
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    for amount in ("160", "250"):
        saved = client.post(f"/accounts/{cib}/transaction/new", data={
            "kind": "out", "date": "2026-10-03", "counterparty": "", "category_id": "", "amount": amount},
            follow_redirects=False)
        assert saved.status_code == 303, saved.text[-400:]
    assert c.reporting.account_balance(cib) == before - D("410")   # the cash left: Safe to spend already counts it
    from lightning.workflows.review import ReviewInbox
    items = [i for i in ReviewInbox(c)._uncategorized() if "no category" in i["label"]]
    assert items and items[0]["label"].startswith("2 payments") and items[0]["glance"]["amount"] == D("410")
    money_in = client.post(f"/accounts/{cib}/transaction/new", data={
        "kind": "in", "date": "2026-10-03", "counterparty": "", "category_id": "", "amount": "75"},
        follow_redirects=False)
    assert money_in.status_code == 303
    assert c.db.scalar("SELECT COUNT(*) FROM ledger_entries l JOIN categories k ON k.id=l.category_id "
                       "WHERE k.code='INC.UNACCOUNTED'") == 1
