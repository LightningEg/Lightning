from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def _purchase(c, accounts, **overrides):
    values = {
        "name": "CIB 1-year certificate",
        "start_date": "2026-09-01",
        "lockup_end_date": "2027-03-01",
        "maturity_date": "2027-09-01",
        "principal": "5000",
        "annual_rate": "12.5",
        "interest_method": "SIMPLE",
        "payout_frequency": "MONTHLY",
        "compounding_frequency": "MONTHLY",
        "destination_account_id": accounts["cib"].id,
        "funding_account_id": accounts["cib"].id,
    }
    values.update(overrides)
    return c.deposits.purchase(accounts["cd"].id, **values)


def _form(accounts, **overrides):
    values = {
        "name": "CIB new certificate",
        "start_date": "2026-09-20",
        "lockup_end_date": "2027-03-20",
        "maturity_date": "2027-09-20",
        "term_years": "",
        "principal": "1000",
        "annual_rate": "12.5",
        "interest_method": "SIMPLE",
        "payout_frequency": "MONTHLY",
        "compounding_frequency": "MONTHLY",
        "destination_account_id": str(accounts["cib"].id),
        "funding_account_id": str(accounts["cib"].id),
    }
    return values | overrides


def test_cd_portfolio_shows_certificates_and_records_purchase(c, setup):
    accounts, _ = setup
    cd = accounts["cd"]
    _purchase(c, accounts)
    client = TestClient(create_app(c), follow_redirects=False)

    listing = client.get("/accounts")
    assert f'href="/deposits/{cd.id}"' in listing.text
    page = client.get(f"/deposits/{cd.id}")
    assert page.status_code == 200
    assert "CIB 1-year certificate" in page.text
    assert "12.5% · Simple" in page.text
    assert "Earliest withdrawal" in page.text and "Maturity" in page.text
    assert "Interest is estimated for cash forecasting only and is never posted automatically" in page.text

    before = c.transactions.count_for_account(cd.id)
    response = client.post(f"/deposits/{cd.id}/purchase", data=_form(accounts))
    assert response.status_code == 303
    assert c.transactions.count_for_account(cd.id) == before + 1
    assert len(c.deposits.list_certificates(cd.id)) == 2


def test_prices_page_uses_purchase_value_for_certificate_and_does_not_ask_for_a_quote(c, setup):
    accounts, _ = setup
    certificate, _ = _purchase(c, accounts)
    client = TestClient(create_app(c), follow_redirects=False)

    page = client.get("/investments/prices").text
    assert "CIB 1-year certificate" in page
    assert "Set at purchase" in page
    assert f'name="p_{certificate.terms.asset_id}"' not in page
    assert f'name="value_{certificate.terms.asset_id}"' not in page
    assert c.reevaluations._price(certificate.terms.asset_id, "2026-12-31") == (Decimal("5000"), "COST")


def test_generic_certificate_value_is_refused_without_inventing_a_month_end_gain(c, setup):
    accounts, _ = setup
    certificate, _ = _purchase(c, accounts)
    client = TestClient(create_app(c), follow_redirects=False)
    cash_before = c.reporting.account_balance(accounts["cd"].id)

    response = client.post("/investments/prices", data={
        "date": "2026-09-30", f"value_{certificate.terms.asset_id}": "6000",
    })

    assert response.status_code == 303
    assert "principal" in response.headers["location"]
    assert c.assets.price_history(certificate.terms.asset_id) == []
    assert not any(row["return_base_e6"] for row in c.reevaluations.history()
                   if row["asset_id"] == certificate.terms.asset_id)
    holding = next(p for p in c.investments.portfolio("2026-09-30").open
                   if p.asset_id == certificate.terms.asset_id)
    assert holding.value == holding.cost_basis == Decimal("5000") and holding.unrealized == 0
    assert c.reporting.account_balance(accounts["cd"].id) == cash_before


def test_cd_purchase_validates_compound_schedule_and_dates(c, setup):
    accounts, _ = setup
    client = TestClient(create_app(c), follow_redirects=False)

    response = client.post(f"/deposits/{accounts['cd'].id}/purchase",
                           data=_form(accounts, interest_method="COMPOUND", payout_frequency="MONTHLY"))
    assert response.status_code == 400
    assert "Compound interest is paid at maturity only." in response.text
    assert c.deposits.list_certificates(accounts["cd"].id) == []

    response = client.post(f"/deposits/{accounts['cd'].id}/purchase",
                           data=_form(accounts, lockup_end_date="2027-10-01"))
    assert response.status_code == 400
    assert "between the purchase and maturity dates" in response.text


def test_certificate_status_and_early_redemption_form_follow_dates_and_sale_factor(c, setup, monkeypatch):
    accounts, _ = setup
    cd_class = c.assets.get_class_by_code("DEPOSIT.CD")
    c.investments.set_liquidation_factor(cd_class.id, "65")
    certificate, _ = _purchase(c, accounts)
    client = TestClient(create_app(c), follow_redirects=False)

    page = client.get(f"/deposits/{accounts['cd'].id}")
    assert "Locked" in page.text
    assert "currently 65%" in page.text
    assert "/certificates/" in page.text

    from lightning.ui.routes import deposits
    monkeypatch.setattr(deposits, "today", lambda: date(2027, 4, 1))
    page = client.get(f"/deposits/{accounts['cd'].id}")
    assert "Can redeem" in page.text
    assert "Record actual redemption" in page.text

    monkeypatch.setattr(deposits, "today", lambda: date(2027, 9, 1))
    page = client.get(f"/deposits/{accounts['cd'].id}")
    assert "Matured · awaiting redemption" in page.text
