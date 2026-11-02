"""Pins the certificate (CD) actions: redeeming, editing terms, interest attributed to certificates,
moving legacy cash, and the one-factor liquidation setting."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app


def _buy(c, accounts, *, name="CIB 1-year certificate", principal="5000", lockup="2026-11-01",
         maturity="2027-09-01", start="2026-09-01"):
    return c.deposits.purchase(
        accounts["cd"].id, name, start, lockup, maturity, principal, "12", "SIMPLE", "AT_MATURITY",
        "MONTHLY", accounts["cib"].id, accounts["cib"].id)


def _terms_form(accounts, **overrides):
    return {"name": "CIB 1-year certificate", "lockup_end_date": "2026-11-01",
            "maturity_date": "2027-09-01", "annual_rate": "12", "interest_method": "SIMPLE",
            "payout_frequency": "AT_MATURITY", "compounding_frequency": "MONTHLY",
            "destination_account_id": str(accounts["cib"].id), "term_years": ""} | overrides


def _cd_class(c, as_of):
    classes, _ = c.position.class_values(as_of)
    return next(cls for cls in classes if cls.code == "DEPOSIT.CD")


def test_redeeming_before_the_earliest_withdrawal_date_is_refused(c, setup):
    accounts, _ = setup
    certificate, _ = _buy(c, accounts)

    with pytest.raises(ValidationError, match="earliest withdrawal date has not arrived"):
        c.deposits.redeem(certificate.terms.id, "2026-10-31", "5100", accounts["cib"].id)
    response = TestClient(create_app(c), follow_redirects=False).post(
        f"/deposits/{accounts['cd'].id}/certificates/{certificate.terms.id}/redeem",
        data={"date": "2026-10-31", "proceeds": "5100", "destination_account_id": str(accounts["cib"].id)})

    assert response.status_code == 400
    assert "The bank&#39;s earliest withdrawal date has not arrived." in response.text
    assert c.deposits.certificate(certificate.terms.id).units == Decimal("1")


def test_redemption_moves_the_proceeds_to_the_bank_and_the_certificate_leaves_holdings(c, setup):
    accounts, _ = setup
    cd, cib = accounts["cd"], accounts["cib"]
    certificate, _ = _buy(c, accounts)
    assert c.reporting.account_balance(cib.id, "2026-12-31") == Decimal("45000")
    client = TestClient(create_app(c), follow_redirects=False)

    response = client.post(f"/deposits/{cd.id}/certificates/{certificate.terms.id}/redeem",
                           data={"date": "2026-12-01", "proceeds": "5250",
                                 "destination_account_id": str(cib.id)})

    assert response.status_code == 303
    assert response.headers["location"].startswith(
        f"/deposits/{cd.id}?msg=" + quote("Recorded actual CD redemption · "))
    assert c.reporting.account_balance(cib.id, "2026-12-31") == Decimal("50250")
    assert c.db.scalar("SELECT t.type FROM cd_redemptions r JOIN transactions t ON t.id=r.transaction_id "
                       "WHERE r.certificate_id=?", (certificate.terms.id,)) == "SEL"
    after = c.deposits.certificate(certificate.terms.id)
    assert after.redeemed is True and after.units == Decimal("0")
    holdings, _ = c.position.owned_holdings("2026-12-31")
    assert certificate.terms.asset_id not in {h.asset_id for h in holdings}
    before, _ = c.position.owned_holdings("2026-11-30")
    assert certificate.terms.asset_id in {h.asset_id for h in before}

    again = client.post(f"/deposits/{cd.id}/certificates/{certificate.terms.id}/redeem",
                        data={"date": "2026-12-02", "proceeds": "5250",
                              "destination_account_id": str(cib.id)})
    assert again.status_code == 400
    assert "This certificate is no longer available to redeem." in again.text
    assert c.reporting.account_balance(cib.id, "2026-12-31") == Decimal("50250")


def test_a_certificate_from_another_portfolio_cannot_be_redeemed_or_edited_here(c, setup):
    accounts, _ = setup
    certificate, _ = _buy(c, accounts)
    other = c.account_flows.open_account("NBE CD", "DEPOSIT", "2026-09-01", "0", institution="NBE")
    client = TestClient(create_app(c), follow_redirects=False)

    redeem = client.post(f"/deposits/{other.id}/certificates/{certificate.terms.id}/redeem",
                         data={"date": "2026-12-01", "proceeds": "5250",
                               "destination_account_id": str(accounts["cib"].id)})
    terms = client.post(f"/deposits/{other.id}/certificates/{certificate.terms.id}/terms",
                        data=_terms_form(accounts, name="Renamed"))

    assert redeem.status_code == terms.status_code == 400
    assert "Certificate not found in this portfolio." in redeem.text
    assert c.deposits.certificate(certificate.terms.id).redeemed is False
    assert c.deposits.certificate(certificate.terms.id).terms.name == "CIB 1-year certificate"


def test_new_certificate_terms_change_its_sale_factor_and_say_saved(c, setup):
    accounts, _ = setup
    c.investments.set_liquidation_factor(c.assets.get_class_by_code("DEPOSIT.CD").id, "65")
    certificate, _ = _buy(c, accounts)
    cd_id = accounts["cd"].id
    assert _cd_class(c, "2026-12-31").after_sale == Decimal("6500")

    response = TestClient(create_app(c), follow_redirects=False).post(
        f"/deposits/{cd_id}/certificates/{certificate.terms.id}/terms",
        data=_terms_form(accounts, lockup_end_date="2027-03-01"))

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/deposits/{cd_id}?msg=" + quote("Certificate terms saved. Interest remains forecast only."))
    assert c.deposits.certificate(certificate.terms.id).terms.lockup_end_date == "2027-03-01"
    assert _cd_class(c, "2026-12-31").after_sale == Decimal("3250")

    c.deposits.update_certificate(
        certificate.terms.id, name="CIB 1-year certificate", lockup_end_date="2026-12-01",
        maturity_date="2026-12-31", annual_rate="12", interest_method="SIMPLE",
        payout_frequency="AT_MATURITY", compounding_frequency="MONTHLY",
        destination_account_id=accounts["cib"].id)
    assert _cd_class(c, "2026-12-31").after_sale == Decimal("8250")


def test_bank_interest_is_split_across_the_certificates_held_that_day_by_cost(c, setup):
    accounts, cats = setup
    interest, cib = cats["EXP.INVEST.INTEREST"].id, accounts["cib"].id
    first, _ = _buy(c, accounts, principal="5000")
    c.transactions.record_inflow("2026-10-01", cib, "100", interest, counterparty="cib")
    second, _ = _buy(c, accounts, name="CIB 3-year certificate", principal="3000", start="2026-10-15")
    c.transactions.record_inflow("2026-11-01", cib, "100", interest, counterparty="CIB")
    c.transactions.record_inflow("2026-11-01", cib, "40", interest, counterparty="NBE")

    def rows(as_of):
        return [(r["date"], r["asset_id"], r["amount"]) for r in c.reporting.certificate_interest(as_of)]

    assert rows("2026-10-31") == [("2026-10-01", first.terms.asset_id, Decimal("100.00"))]
    assert rows("2026-11-01") == [
        ("2026-10-01", first.terms.asset_id, Decimal("100.00")),
        ("2026-11-01", first.terms.asset_id, Decimal("62.50")),
        ("2026-11-01", second.terms.asset_id, Decimal("37.50")),
    ]
    assert {r["account_id"] for r in c.reporting.certificate_interest("2026-11-01")} == {accounts["cd"].id}


def test_moving_legacy_cash_needs_the_portfolio_currency_and_then_moves_it(c, setup):
    accounts, _ = setup
    cd, cib = accounts["cd"], accounts["cib"]
    usd = c.account_flows.open_account("CIB USD", "BANK", "2026-09-01", "0", institution="CIB")
    c.db.execute("UPDATE accounts SET currency='USD' WHERE id=?", (usd.id,))
    client = TestClient(create_app(c), follow_redirects=False)

    refused = client.post(f"/deposits/{cd.id}/legacy-cash",
                          data={"date": "2026-12-01", "amount": "2000", "destination_account_id": str(usd.id)})
    assert refused.status_code == 400
    assert "Choose a destination in the CD portfolio&#39;s currency." in refused.text
    assert c.deposits.legacy_cash_balance(cd.id, date(2026, 12, 31)) == Decimal("5000")

    moved = client.post(f"/deposits/{cd.id}/legacy-cash",
                        data={"date": "2026-12-01", "amount": "2000", "destination_account_id": str(cib.id)})
    assert moved.status_code == 303
    assert moved.headers["location"].startswith(
        f"/deposits/{cd.id}?msg=" + quote("Moved legacy cash to a liquid account · "))
    assert c.deposits.legacy_cash_balance(cd.id, date(2026, 12, 31)) == Decimal("3000")
    assert c.reporting.account_balance(cib.id, "2026-12-31") == Decimal("52000")


def test_the_one_liquidation_factor_setting_refuses_101_and_applies_50_only_to_classes_with_holdings(c, setup):
    accounts, _ = setup
    _buy(c, accounts)
    held = {a.asset_class_id for a in c.assets.list_assets() if not a.is_cash}
    client = TestClient(create_app(c), follow_redirects=False)
    before = c.investments.own_liquidation_factors()

    refused = client.post("/birdview/settings", data={"factor": "101"})
    assert refused.status_code == 400
    assert refused.text == "Enter a liquidation factor from 0 to 100."
    assert c.investments.own_liquidation_factors() == before

    saved = client.post("/birdview/settings", data={"factor": "50"})
    assert saved.status_code == 204
    own = c.investments.own_liquidation_factors()
    assert c.assets.get_class_by_code("DEPOSIT.CD").id in held
    assert {class_id: own.get(class_id) for class_id in held} == {class_id: Decimal("50") for class_id in held}
    factors = c.investments.liquidation_factors()
    assert all(factors[class_id] == Decimal("50") for class_id in held)
    stock = c.assets.get_class_by_code("STOCK").id
    assert stock not in held and factors[stock] == Decimal("95")


def test_locked_certificate_has_a_separate_value_and_settings_use_the_same_sale_estimate(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-14")
    accounts, _ = setup
    _buy(c, accounts)
    position = c.position.at("2026-10-14")
    assert len(position.locked_holdings) == 1
    assert position.locked_holdings[0].value == Decimal("5000")
    assert position.locked_holdings[0].locked_until == "2026-11-01"
    assert _cd_class(c, "2026-10-14").after_sale == Decimal("4750")  # legacy 5,000 at 95%; locked certificate excluded
    client = TestClient(create_app(c))
    for path in ("/", "/investments", "/settings?section=assets-valuations"):
        page = client.get(path).text
        assert "not counted until 2026-11-01" in page and "5,000" in page
    assert not c.position.at("2026-11-01").locked_holdings


def test_a_certificate_holding_page_lists_its_interest_payouts(c, setup):
    """BV-5K: the interest the bank paid shows in Trades and payouts, after the purchase, with the units held then."""
    from datetime import date
    from lightning.ui import visuals
    accounts, cats = setup
    certificate, _ = _buy(c, accounts, principal="5000")
    interest, cib = cats["EXP.INVEST.INTEREST"].id, accounts["cib"].id
    c.transactions.record_inflow("2026-10-01", cib, "100", interest, counterparty="CIB")
    c.transactions.record_inflow("2026-11-01", cib, "100", interest, counterparty="CIB")
    cd_id, asset_id = accounts["cd"].id, certificate.terms.asset_id
    trades = visuals.holding_journey(c, cd_id, asset_id, date(2026, 12, 31))["trades"]
    paid = [t for t in trades if t["kind"] == "Interest paid"]
    assert [(t["date"], t["amount"]) for t in paid] == [("2026-11-01", Decimal("100.00")), ("2026-10-01", Decimal("100.00"))]
    assert all(t["held"] == trades[-1]["held"] > 0 for t in paid)
    page = TestClient(create_app(c)).get(f"/investments/holding/{asset_id}?account={cd_id}&date=2026-12-31")
    assert page.status_code == 200 and page.text.count("Interest paid") == 2
