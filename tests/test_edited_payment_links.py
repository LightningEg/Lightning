"""BT-7U (owner decision 2026-11-02): editing the transaction that paid a bill or income keeps the link while it still
fits the item's window and tolerance, refreshes the paid amount, and otherwise opens the payment again and says so."""
from decimal import Decimal as D
from urllib.parse import unquote_plus

import pytest
from fastapi.testclient import TestClient

from lightning.planning.domain import PaymentStatus
from lightning.ui.web import create_app


@pytest.fixture
def paid_bill(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-12-31")
    bank = setup[0]["cib"]
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    item = c.planning.create(kind="BILL", name="Internet", amount="500", frequency="MONTHLY",
                             start_date="2026-02-05", category_id=str(food.id))
    c.planning.record_payment(item, "2026-02-05", "2026-02-05", "500", bank.id)
    txn = c.db.scalar("SELECT id FROM transactions WHERE type='OUT' AND status='POSTED'")
    return TestClient(create_app(c), base_url="http://127.0.0.1"), bank, item, txn


def _edit(c, client, bank, txn, **changes):
    row = dict(date="2026-02-05", amount="-500", category="Food & Groceries", counterparty="", notes="",
               revision=c.transactions.revision(txn)) | changes
    reply = client.post(f"/accounts/{bank.id}/register/{txn}", data=row, follow_redirects=False)
    assert reply.status_code == 303
    return unquote_plus(reply.headers["location"])


def _february(c, item):
    return next(p for p in c.planning.payments(c.planning.get(item), "2026-02-28") if p.due_date == "2026-02-05")


def test_a_small_change_keeps_the_bill_paid_at_the_new_amount(c, paid_bill):
    client, bank, item, txn = paid_bill
    message = _edit(c, client, bank, txn, amount="-520")
    paid = _february(c, item)
    assert paid.status == PaymentStatus.PAID and paid.paid_amount == D("520") and "no longer fits" not in message


def test_a_change_that_no_longer_fits_opens_the_payment_again_and_says_so(c, paid_bill):
    client, bank, item, txn = paid_bill
    message = _edit(c, client, bank, txn, amount="-5000", date="2026-12-05")
    assert "no longer fits Internet" in message and "open again" in message
    assert _february(c, item).status != PaymentStatus.PAID
