"""NF-9C: kind, purchase and loan on an Other asset account, beside its dated values."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app

from test_journal_finance import devices  # noqa: F401
from test_journal_screens import screens  # noqa: F401

D = Decimal


def _car_and_loan(c):
    car = c.account_flows.open_account("Car", "OTHER_ASSET", "2025-01-01", "0")
    loan = c.planning.create(kind="LOAN", name="Car loan", amount="2500", frequency="MONTHLY",
                             start_date="2026-01-15", payment_count=10)
    c.accounts.save_other_asset_value(car, "2025-06-01", "600000")
    c.accounts.save_other_asset_value(car, "2026-06-01", "540000")
    return c.accounts.get(car.id), loan


def test_details_are_saved_replaced_and_checked(c):
    car, loan = _car_and_loan(c)
    assert c.accounts.other_asset_details(car.id) is None
    saved = c.accounts.save_other_asset_details(car, "car", "2025-06-01", "600000", str(loan))
    assert saved == {"kind": "car", "purchase_date": "2025-06-01", "purchase_price": D("600000"), "loan_item_id": loan}
    again = c.accounts.save_other_asset_details(car, "flat", "", "", "")
    assert again == {"kind": "flat", "purchase_date": None, "purchase_price": None, "loan_item_id": None}
    for kind, day, price, link in (("boat", "", "", ""), ("car", "2999-01-01", "", ""), ("car", "", "-5", ""),
                                   ("car", "", "", "999")):
        with pytest.raises(ValidationError):
            c.accounts.save_other_asset_details(car, kind, day, price, link)
    bank = c.account_flows.open_account("Bank", "BANK", "2025-01-01", "0")
    with pytest.raises(ValidationError):
        c.accounts.save_other_asset_details(c.accounts.get(bank.id), "car", "", "", "")


def test_a_non_loan_cannot_be_linked(c):
    car, _ = _car_and_loan(c)
    bill = c.planning.create(kind="BILL", name="Rent", amount="1000", frequency="MONTHLY", start_date="2026-01-01")
    with pytest.raises(ValidationError):
        c.accounts.save_other_asset_details(car, "car", "", "", str(bill))


def test_the_account_page_shows_the_change_since_purchase_the_history_and_the_loan(c):
    car, loan = _car_and_loan(c)
    client = TestClient(create_app(c))
    page = client.get(f"/accounts/{car.id}").text
    assert "Property or vehicle" in page and "Say what this is" in page
    response = client.post(f"/accounts/{car.id}/details", data={
        "kind": "car", "purchase_date": "2025-06-01", "purchase_price": "600000", "loan_item_id": str(loan)},
        follow_redirects=False)
    assert response.status_code == 303 and "Details%20saved" in response.headers["location"]
    page = client.get(f"/accounts/{car.id}").text
    assert "Bought for 600,000" in page and "Since you bought it" in page and "-60,000" in page.replace("−", "-")
    assert "Car loan" in page and "Left to pay" in page and "2025-06-01" in page and "2026-06-01" in page
    # 3AT: flat rows, whole pounds, no investment form or statement import on a car, a typed loan picker.
    assert "stat-tile" not in page and "Add investment transaction" not in page and "/import" not in page
    assert 'data-pick-target="asset-loan-pick"' in page and "<select name=\"loan_item_id\"" not in page
    assert 'href="#estimated-value"' in page
    refused = client.post(f"/accounts/{car.id}/details", data={"kind": "boat"}, follow_redirects=False)
    assert "msg=" in refused.headers["location"] and c.accounts.other_asset_details(car.id)["kind"] == "car"


def test_removing_the_loan_unlinks_the_car(c):
    car, loan = _car_and_loan(c)
    c.accounts.save_other_asset_details(car, "car", "", "", str(loan))
    c.db.execute("DELETE FROM planned_items WHERE id=?", (loan,))
    assert c.accounts.other_asset_details(car.id)["loan_item_id"] is None


def test_details_travel_as_a_portable_command(screens):
    from lightning.sync.journal.codec import unpack
    from lightning.sync.journal.proxy import JournalServices

    (hd, pc), (_, replica) = screens
    JournalServices(hd).account_flows.open_account("Flat", "OTHER_ASSET", "2026-01-01", "0")
    pc.sync_with(hd.home)
    flat = next(a for a in pc.c.accounts.list() if a.name == "Flat")
    response = replica.post(f"/accounts/{flat.id}/details", data={
        "kind": "flat", "purchase_date": "2026-02-01", "purchase_price": "900000", "loan_item_id": ""})
    assert response.status_code == 303 and "Saved+on+this+device" in response.headers["location"]
    assert unpack(pc.store.pending()[0])["body"]["kind"] == "command.accounts.other_asset_details.save"
    pc.sync_with(hd.home)
    home_flat = next(a for a in hd.c.accounts.list() if a.name == "Flat")
    for device, account in ((hd, home_flat), (pc, flat)):
        details = device.c.accounts.other_asset_details(account.id)
        assert details["kind"] == "flat" and details["purchase_price"] == D("900000")
    assert pc.store.fingerprint() == hd.store.fingerprint()
