"""NF-3AZ8: a maturing certificate shows its expected date as a forecast; allocation choices appear only after the
redemption is recorded, from the cash that actually arrived."""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from lightning.ui.web import create_app
from test_deposit_ui import _purchase
from tests.screens import said


def test_expected_maturity_is_a_forecast_and_choices_wait_for_the_receipt(c, setup, monkeypatch):
    accounts, _ = setup
    certificate, _ = _purchase(c, accounts, payout_frequency="AT_MATURITY")
    cd = accounts["cd"]
    from lightning.ui.routes import deposits
    monkeypatch.setattr(deposits, "today", lambda: date(2027, 9, 1))
    monkeypatch.setenv("LIGHTNING_TODAY", "2027-09-01")
    client = TestClient(create_app(c), follow_redirects=False)
    page = client.get(f"/deposits/{cd.id}")
    assert said("Expected 2027-09-01: about") in page.text and "not cash received" in page.text
    assert "What next for the money" not in page.text and "allocation-choices" not in page.text   # a forecast is not cash
    outlook = c.deposits.maturity_outlook(c.deposits.list_certificates(cd.id)[0])
    assert outlook["received"] is None and outlook["expected"] > 5000

    cert_id = c.deposits.list_certificates(cd.id)[0].terms.id
    done = client.post(f"/deposits/{cd.id}/certificates/{cert_id}/redeem",
                       data={"date": "2027-09-01", "proceeds": "5625", "destination_account_id": str(accounts["cib"].id)})
    assert done.status_code == 303
    page = client.get(f"/deposits/{cd.id}")
    assert "What next for the money from CIB 1-year certificate?" in page.text
    assert said("5,625 EGP reached your account on 2027-09-01") in page.text
    for choice in ("Buy another certificate", "Top up the emergency fund", "Fund your payday plan", "Keep it as cash"):
        assert choice in page.text
    assert "Expected 2027-09-01" not in page.text                                    # redeemed: no forecast any more
    assert client.get(f"/deposits/{cd.id}?principal=5625.00").text.count('value="5625.00"') >= 1
