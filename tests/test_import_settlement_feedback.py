"""Import feedback describes committed bill links and survives a failed settlement retry."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app


def _import(c, setup, kind="BILL"):
    accounts, cats = setup
    account, category = accounts["cib"], cats["EXP.PERSONAL.FOOD"]
    bill = c.planning.create(kind=kind, name="Landlord", amount="400", frequency="ONCE",
                             start_date="2026-09-22", account_id=account.id, category_id=category.id)
    batch, _ = c.bank_imports.stage(account.id, "bills.csv", b"Date,Counterparty,Amount\n2026-09-22,Landlord,-400\n")
    row = c.bank_imports.preview(batch)[1][0]["_import_row_id"]
    payload = {f"amount_{row}": "-400", f"date_{row}": "2026-09-22",
               f"category_{row}": str(category.id), f"counterparty_{row}": "Landlord"}
    return account, category, bill, batch, payload


@pytest.mark.parametrize("phone,locale", [(False, "en"), (True, "en"), (False, "ar"), (True, "ar")])
def test_import_names_only_its_bills_and_undo_restores_the_batch(c, setup, phone, locale):
    account, category, bill, batch, payload = _import(c, setup)
    # An unrelated receipt may also be matched by this write; it is absent from the import message.
    c.planning.create(kind="BILL", name="Unrelated bill", amount="25", frequency="ONCE",
                      start_date="2026-09-20", account_id=account.id, category_id=category.id)
    c.transactions.record_outflow("2026-09-20", account.id, "25", category.id)
    c.settings.set("locale", locale)
    app = create_app(c)
    @app.middleware("http")
    async def surface(request, call_next):
        request.state.phone = phone
        return await call_next(request)
    @app.get("/test-undo-id")
    async def undo_id():
        return c.undo.available()["undo"]["id"]
    with TestClient(app) as client:
        response = client.post(f"/accounts/{account.id}/import/{batch}/confirm", data=payload)
        assert response.status_code == 200
        assert ("Settled bills: Landlord." if locale == "en" else "الفواتير اللي اتسددت: Landlord.") in response.text
        assert "Unrelated bill" not in response.text
        assert c.planning.linked_transaction_ids()
        assert c.reporting.account_balance(account.id) == Decimal("49575")
        group_id = client.get("/test-undo-id").json()
        assert client.post("/history/undo", data={"group_id": group_id}, follow_redirects=False).status_code == 303
    assert c.reporting.account_balance(account.id) == Decimal("49975")
    assert c.bank_imports.preview(batch)[0]["status"] == "REVIEW"
    assert not c.db.scalar("SELECT 1 FROM planned_payments WHERE planned_item_id=?", (bill,))


@pytest.mark.parametrize("storage_error", [False, True])
def test_settlement_failure_rolls_back_import_then_retry_posts_once(c, setup, monkeypatch, storage_error):
    account, _, bill, batch, payload = _import(c, setup)
    original = c.planning.match_payments
    calls = []
    def fail(day):
        calls.append(original(day))
        if storage_error:
            raise OSError("Injected disk failure")
        raise ValidationError("Injected settlement failure")
    monkeypatch.setattr(c.planning, "match_payments", fail)
    client = TestClient(create_app(c), raise_server_exceptions=False)
    response = client.post(f"/accounts/{account.id}/import/{batch}/confirm", data=payload)
    assert response.status_code == (500 if storage_error else 400)
    assert calls == [1]
    assert "Import complete" not in response.text
    assert c.reporting.account_balance(account.id) == Decimal("50000")
    assert c.bank_imports.preview(batch)[0]["status"] == "REVIEW"
    assert not c.db.scalar("SELECT 1 FROM planned_payments WHERE planned_item_id=?", (bill,))
    monkeypatch.setattr(c.planning, "match_payments", original)
    response = client.post(f"/accounts/{account.id}/import/{batch}/confirm", data=payload)
    assert response.status_code == 200 and "Settled bills: Landlord." in response.text
    assert c.reporting.account_balance(account.id) == Decimal("49600")
    assert client.post(f"/accounts/{account.id}/import/{batch}/confirm", data=payload).status_code == 400
    assert c.reporting.account_balance(account.id) == Decimal("49600")


@pytest.mark.parametrize("kind", ["BILL", "SUBSCRIPTION"])
def test_existing_statement_link_reports_bill_without_posting_cash_again(c, setup, kind):
    account, category, _, batch, payload = _import(c, setup, kind)
    txn = c.transactions.record_outflow("2026-09-22", account.id, "400", category.id, counterparty="Landlord")
    row = c.bank_imports.preview(batch)[1][0]["_import_row_id"]
    payload[f"match_{row}"] = f"link:{txn.id}"
    response = TestClient(create_app(c)).post(f"/accounts/{account.id}/import/{batch}/confirm", data=payload)
    assert response.status_code == 200
    assert "0 posted, 1 linked" in response.text and "Settled bills: Landlord." in response.text
    assert c.reporting.account_balance(account.id) == Decimal("49600")


def test_ambiguous_bill_is_not_claimed_as_settled(c, setup):
    account, category, _, batch, payload = _import(c, setup)
    c.planning.create(kind="BILL", name="Another possible bill", amount="400", frequency="ONCE",
                      start_date="2026-09-22", account_id=account.id, category_id=category.id)
    response = TestClient(create_app(c)).post(f"/accounts/{account.id}/import/{batch}/confirm", data=payload)
    assert response.status_code == 200 and "Import complete: 1 posted" in response.text
    assert "Settled bills:" not in response.text
    assert not c.planning.linked_transaction_ids()
