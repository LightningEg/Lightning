"""IV-12J: a certificate reads as a certificate. Its own holding page (PC and phone) in the bank's words, a value that
grows as interest is earned when the bank pays at maturity, and dated rate changes for a variable certificate."""
from __future__ import annotations

import html
import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.core import certificate_schedule as schedule
from lightning.ui.web import create_app

STOCK_WORDS = re.compile(r"\b(price|units?|average cost|unrealized|buy more)\b", re.I)


def _client(c, phone=False, locale="en"):
    app = create_app(c)
    if phone:
        inner = app

        async def phone_app(scope, receive, send):
            if scope["type"] == "http":
                scope.setdefault("state", {})["phone"] = True
            await inner(scope, receive, send)
        app = phone_app
    client = TestClient(app, follow_redirects=False)
    if locale != "en":
        assert client.post("/settings/locale", data={"locale": locale}).status_code == 303
    return client


def _text(page: str) -> str:
    body = re.sub(r"(?s)<(script|style)\b.*?</\1>", " ", page)
    body = re.sub(r"(?s)<nav\b.*?</nav>", " ", body)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)))


def _monthly(c, accounts, **overrides):
    args = dict(name="CIB 3-year certificate", start_date="2026-09-01", lockup_end_date="2027-03-01",
                maturity_date="2029-09-01", principal="12000", annual_rate="20", interest_method="SIMPLE",
                payout_frequency="MONTHLY", compounding_frequency="MONTHLY",
                destination_account_id=accounts["cib"].id, funding_account_id=accounts["cib"].id)
    args.update(overrides)
    certificate, _ = c.deposits.purchase(accounts["cd"].id, **args)
    return certificate


def _compound(c, accounts):
    return _monthly(c, accounts, name="CIB compound certificate", principal="10000", annual_rate="24",
                    interest_method="COMPOUND", payout_frequency="AT_MATURITY", compounding_frequency="YEARLY",
                    lockup_end_date="2026-09-01", maturity_date="2028-09-01")


@pytest.mark.parametrize("phone", [False, True])
def test_the_certificate_page_speaks_of_rate_payouts_and_maturity_not_prices(c, setup, phone):
    accounts, cats = setup
    certificate = _monthly(c, accounts)
    # Three monthly payouts of 200 reached CIB from the bank: the October one is missing.
    for day in ("2026-11-01", "2026-12-01"):
        c.transactions.record_inflow(day, accounts["cib"].id, "200", cats["EXP.INVEST.INTEREST"].id,
                                     counterparty="CIB")

    page = _client(c, phone).get(f"/investments/holding/{certificate.terms.asset_id}")

    assert page.status_code == 200, page.text[:400]
    text = _text(page.text)
    for words in ("20% a year", "Interest paid monthly", 
                  "Its terms expected 600 by now", "Next payment", "1 Jan 2027", "in 1 day",
                  "Locked until 1 Mar 2027, in 60 days", "1 Sep 2029", "36 interest payments"):
        assert words in text, words
    assert re.search(r"Interest received\D*400\b", text)
    assert not STOCK_WORDS.search(text), STOCK_WORDS.search(text)
    assert "/investments/new?kind=buy" not in page.text
    assert f"/deposits/{accounts['cd'].id}" in page.text


def test_the_holding_figures_come_from_the_deposit_service(c, setup):
    accounts, _ = setup
    certificate = _monthly(c, accounts)
    factor = Decimal("90")

    info = c.deposits.holding(certificate, date(2027, 6, 15), Decimal("1800"), factor)

    assert info["expected"] == Decimal("1800")                    # 9 monthly payouts of 12,000 x 20% / 12
    assert info["next_date"] == "2027-07-01" and info["next_amount"] == Decimal("200")
    assert info["unlock_days"] is None and info["maturity_days"] == (date(2029, 9, 1) - date(2027, 6, 15)).days
    assert info["value"] == Decimal("12000")                      # it pays as it goes, so it stays at principal
    assert info["cash_in"] == Decimal("10800.00")                 # unlocked: 90% sale factor
    assert info["interest_payments"] == 36
    locked = c.deposits.holding(certificate, date(2026, 12, 31), Decimal("0"), factor)
    assert locked["cash_in"] is None and locked["unlock_days"] == 60


def test_the_certificates_page_leads_with_the_list_and_opens_the_buy_form_from_a_button(c, setup):
    accounts, _ = setup
    certificate = _monthly(c, accounts)
    holding = f'href="/investments/holding/{certificate.terms.asset_id}?account={accounts["cd"].id}"'

    pc = _client(c).get(f"/deposits/{accounts['cd'].id}").text
    assert pc.index("<table") < pc.index('id="buy-certificate"') and holding in pc
    assert re.search(r'<details class="card" id="buy-certificate"[^>]*>\s*<summary', pc)
    assert 'id="buy-certificate" style="margin-top:16px" open' not in pc   # it opens from its button
    head = _text(pc[pc.index("<thead"):pc.index("</thead>")]).split()
    assert head == ["Certificate", "Interest", "rate", "Next", "payment", "Maturity", "Status"]
    assert "1 Jan 2027" in _text(pc[pc.index("<tbody"):pc.index("</tbody>")])

    phone = _client(c, phone=True).get(f"/deposits/{accounts['cd'].id}").text
    rows = phone[phone.index('id="certificate-'):phone.index('id="buy-certificate"')]
    assert "<table" not in rows and holding in rows   # rows, never a table cut at the phone's edge
    assert all(words in _text(rows) for words in ("CIB 3-year certificate", "20%", "Next payment", "1 Jan 2027",
                                                    "Maturity", "1 Sep 2029", "Locked"))


def _short_compound(c, accounts):
    """10,000 at 24% compounded monthly for three months: 200, then 204, then 208.08 of interest."""
    return _monthly(c, accounts, name="CIB 3-month compound", principal="10000", annual_rate="24",
                    interest_method="COMPOUND", payout_frequency="AT_MATURITY", compounding_frequency="MONTHLY",
                    lockup_end_date="2026-09-01", maturity_date="2026-12-01")


def _value(c, asset_id, day):
    return next(h.value for h in c.investments.portfolio(day).open if h.asset_id == asset_id)


def test_a_certificate_paid_at_maturity_gains_value_as_it_earns(c, setup):
    accounts, _ = setup
    certificate = _short_compound(c, accounts)
    asset = certificate.terms.asset_id

    values = [_value(c, asset, day) for day in ("2026-09-01", "2026-10-01", "2026-10-16", "2026-11-01", "2026-12-01")]

    assert values == [Decimal("10000"), Decimal("10200"), Decimal("10298.71"), Decimal("10404"), Decimal("10612.08")]
    assert _value(c, asset, "2026-12-31") == Decimal("10612.08")      # matured, not yet redeemed: no more growth
    worth = [c.reporting.net_worth(day).total for day in ("2026-09-01", "2026-10-01", "2026-11-01")]
    assert worth[1] - worth[0] == Decimal("200") and worth[2] - worth[1] == Decimal("204")
    info = c.deposits.holding(certificate, date(2026, 10, 16), Decimal("0"), Decimal("95"))
    assert info["value"] == values[2] and info["earned"] == Decimal("298.71")   # 204 over 15 of 31 days
    page = _text(_client(c).get(f"/investments/holding/{asset}").text)
    assert "Worth today" in page and "estimate" in page and "10,612" in page


def test_the_redemption_settles_the_estimate_and_the_period_report_reconciles(c, setup):
    from lightning.investments.report import investment_period
    accounts, _ = setup
    certificate = _short_compound(c, accounts)
    c.deposits.redeem(certificate.terms.id, "2026-12-01", "10612.08", accounts["cib"].id)

    report = investment_period(c.db, c.accounts, c.assets, c.reporting, "2026-10-01", "2026-12-31")
    worth_change = c.reporting.net_worth("2026-12-31").total - c.reporting.net_worth("2026-09-30").total

    assert report["realized"] == Decimal("612.08")                   # the bank paid what the terms said
    # The estimate held the day before the period (29 of September's 30 days of 200) is settled by the redemption.
    assert report["unrealized_change"] == Decimal("-193.33")
    assert report["result"] == Decimal("418.75") == worth_change     # interest earned in the period, nothing more
    assert all(h.asset_id != certificate.terms.asset_id for h in c.investments.portfolio("2026-12-31").open)


def test_a_certificate_that_pays_as_it_goes_stays_at_its_principal(c, setup):
    accounts, _ = setup
    certificate = _monthly(c, accounts)
    assert _value(c, certificate.terms.asset_id, "2026-12-15") == Decimal("12000")


def test_simple_interest_paid_at_maturity_accrues_evenly_to_the_maturity_amount(c, setup):
    accounts, _ = setup
    certificate = _monthly(c, accounts, payout_frequency="AT_MATURITY", principal="36500", annual_rate="10",
                           lockup_end_date="2026-09-01", maturity_date="2027-09-01")
    terms = certificate.terms
    total = sum(amount for _, amount, kind in schedule.events(terms) if kind == "INTEREST")
    assert total == Decimal("3650")
    assert schedule.accrued(terms, date(2027, 9, 1)) == total
    assert schedule.accrued(terms, date(2026, 9, 11)) == Decimal("100.00")   # 10 of 365 days


def test_growing_foreign_certificate_uses_the_dated_exchange_rate(c):
    from lightning.fx import save_rate
    from lightning.database.currencies import CurrencyRegistry

    CurrencyRegistry(c.db).register('USD')
    save_rate(c.db, '2026-09-01', 'USD', 'EGP', Decimal('50'), 'MANUAL')
    save_rate(c.db, '2026-10-01', 'USD', 'EGP', Decimal('51'), 'MANUAL')
    bank = c.account_flows.open_account('Dollar bank', 'BANK', '2026-09-01', '20000', currency='USD')
    portfolio = c.account_flows.open_account('Dollar certificates', 'DEPOSIT', '2026-09-01', '0', institution='CIB', currency='USD')
    certificate = _short_compound(c, {'cib': bank, 'cd': portfolio})
    assert _value(c, certificate.terms.asset_id, '2026-10-01') == Decimal('520200')


def test_a_variable_rate_change_is_dated_not_a_rewrite_of_the_schedule(c, setup):
    """IV-12J4: from 2027-01-01 the bank pays 15% instead of 20%; October to December keep 200 a month."""
    accounts, _ = setup
    certificate = _monthly(c, accounts)
    cd = accounts["cd"].id
    form = {"name": certificate.terms.name, "lockup_end_date": "2027-03-01", "maturity_date": "2029-09-01",
            "annual_rate": "15", "interest_method": "SIMPLE", "payout_frequency": "MONTHLY",
            "compounding_frequency": "MONTHLY", "destination_account_id": str(accounts["cib"].id), "term_years": "",
            "rate_from": "2026-12-01"}

    response = _client(c).post(f"/deposits/{cd}/certificates/{certificate.terms.id}/terms", data=form)

    assert response.status_code == 303, response.text[:300]
    after = c.deposits.certificate(certificate.terms.id)
    assert after.terms.annual_rate == Decimal("20")                      # the purchase rate stays
    assert c.deposits.rates(certificate.terms.id) == [(date(2026, 12, 1), Decimal("15"))]
    paid = {when.isoformat(): amount for when, amount, kind in schedule.events(after.terms, c.deposits.rates(after.terms.id))
            if kind == "INTEREST"}
    assert paid["2026-12-01"] == Decimal("200")       # the period 1 Nov to 1 Dec began at 20%
    assert paid["2027-01-01"] == Decimal("150")       # 12,000 x 15% / 12
    future = [e for e in c.deposits.future_events("2026-12-31", "2027-02-28") if e.certificate_id == after.terms.id]
    assert [e.amount for e in future] == [Decimal("150"), Decimal("150")]
    page = _text(_client(c).get(f"/investments/holding/{after.terms.asset_id}").text)
    assert "15% a year" in page and "variable" in page and "15% from 1 Dec" in page

    form["rate_from"] = "2026-08-01"
    refused = _client(c).post(f"/deposits/{cd}/certificates/{certificate.terms.id}/terms", data=form)
    assert refused.status_code == 400 and "after the purchase date" in refused.text


def test_a_dated_rate_moves_the_growing_value_of_a_compound_certificate(c, setup):
    accounts, _ = setup
    certificate = _short_compound(c, accounts)
    c.deposits.set_rate_change(certificate.terms.id, "2026-11-01", "12")
    # 200 in September, 204 in October at 24%; November at 12% on 10,404: 104.04.
    assert _value(c, certificate.terms.asset_id, "2026-12-01") == Decimal("10508.04")


def test_migration_0088_adds_the_rate_changes_table_to_an_older_profile(tmp_path, monkeypatch):
    import shutil
    from lightning.database import migrator
    from lightning.database.connection import Database
    old = tmp_path / "migrations_87"
    old.mkdir()
    for path in migrator.MIGRATIONS_DIR.glob("*.sql"):
        if int(path.name[:4]) <= 87:
            shutil.copy(path, old / path.name)
    bundled = migrator.MIGRATIONS_DIR
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", old)
    db = Database(tmp_path / "old.db")
    try:
        migrator.migrate(db)
        assert not db.has_table("cd_rate_changes")
        monkeypatch.setattr(migrator, "MIGRATIONS_DIR", bundled)
        assert migrator.migrate(db)[0] == "0088_cd_rate_changes (APPLIED)"
        assert db.has_table("cd_rate_changes") and db.scalar("SELECT COUNT(*) FROM cd_rate_changes") == 0
        assert migrator.migrate(db) == []
    finally:
        db.close()
