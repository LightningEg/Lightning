"""NF-5G5 broker statements (owner 2026-11-04: Interactive Brokers first): an IBKR activity statement posts into the
broker's currency pockets, the same ledger as typing each event; importing it again records nothing twice; the
statement's open positions are checked against the ledger. Dummy data only."""
from decimal import Decimal as D
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import LightningError
from lightning.database.currencies import CurrencyRegistry
from lightning.investments.broker_import import BrokerImport, read_ibkr
from lightning.ui.web import create_app

STATEMENT = (Path(__file__).parent / "fixtures" / "broker" / "ibkr_activity.csv").read_bytes()
DAYS = ("2026-09-01", "2026-09-03", "2026-09-05", "2026-09-10", "2026-09-30", "2026-10-31", "2026-11-30",
        "2026-12-01", "2026-12-02", "2026-12-05", "2026-12-06", "2026-12-31")


def _ibkr(c):
    for code, rate in (("USD", "50"), ("EUR", "55")):
        CurrencyRegistry(c.db).register(code)
        for day in DAYS:
            c.fx.save(code, day, rate)
    return c.account_flows.open_account("IBKR", "BROKERAGE", "2026-09-01", "2000", institution="Interactive Brokers",
                                        currency="USD")


def test_the_statement_reads_trades_conversions_income_and_positions():
    s = read_ibkr(STATEMENT)
    kinds = [(e.kind, e.symbol or e.text) for e in s.events]
    assert kinds == [("deposit", "Electronic Fund Transfer"), ("buy", "QQQM"), ("convert", "EUR.USD"), ("buy", "SAP"),
                     ("sell", "QQQM"), ("dividend", "QQQM"), ("interest", "USD Credit Interest for Nov-2026"),
                     ("fee", "Market data fee")]
    dividend = next(e for e in s.events if e.kind == "dividend")
    assert (dividend.amount, dividend.tax) == (D("4"), D("0.6"))
    assert s.instruments["SAP"].mic == "XETR" and s.instruments["QQQM"].fund
    assert s.positions == {("QQQM", "USD"): D("3"), ("SAP", "EUR"): D("2")} and s.period_end == "2026-12-31"


def test_importing_posts_into_pockets_once_and_the_positions_match(c, setup):
    ibkr = _ibkr(c)
    s = read_ibkr(STATEMENT)
    done = BrokerImport(c).post(ibkr.id, s)
    assert [r.message for r in done.rows if r.status == "problem"] == []
    assert done.count("posted") == 7 and done.count("listed") == 1      # the deposit is recorded from the bank
    eur = c.accounts.pocket_for(ibkr, "EUR")
    assert eur.parent_id == ibkr.id
    day = "2026-12-31"
    # USD: 2,000 − 1,001 − 550 − 2 (conversion fee) + 459 + 3.40 (dividend after tax) + 1.50 − 3
    assert c.reporting.account_balance(ibkr.id, day) == D("907.90")
    assert c.reporting.account_balance(eur.id, day) == D("98.75")          # 500 − 401.25
    assert all(row["matches"] for row in BrokerImport(c).check_positions(ibkr.id, s))
    again = BrokerImport(c).post(ibkr.id, s)
    assert again.count("posted") == 0 and again.count("imported") == 7
    assert c.reporting.account_balance(ibkr.id, day) == D("907.90")


def test_the_import_is_the_same_ledger_as_typing_each_event(c, setup, tmp_path):
    """Phase 4's proof: the same events typed by hand give the same cash and holdings."""
    ibkr = _ibkr(c)
    BrokerImport(c).post(ibkr.id, read_ibkr(STATEMENT))
    imported = {a.currency: c.reporting.account_balance(a.id, "2026-12-31") for a in [ibkr, *c.accounts.pockets(ibkr.id)]}
    from lightning.bootstrap import build
    t = build(tmp_path / "typed.db")
    try:
        typed = _ibkr(t)
        eur = t.accounts.pocket_for(typed, "EUR", create=True)
        qqqm = t.assets.create_investment("INVESCO NASDAQ 100 ETF", "FUND.EQUITY", "QQQM", mic="XNAS", currency="USD")
        sap = t.assets.create_investment("SAP SE", "STOCK", "SAP", mic="XETR", currency="EUR")
        t.investments.buy_total("2026-09-03", typed.id, qqqm.id, "5", "1001", fees="1")
        t.transactions.record_conversion("2026-09-05", typed.id, eur.id, "550", "500", fee="2")
        t.investments.buy_total("2026-09-10", eur.id, sap.id, "2", "401.25", fees="1.25")
        t.investments.sell_total("2026-12-01", typed.id, qqqm.id, "2", "459", fees="1")
        t.investments.dividend("2026-12-02", typed.id, qqqm.id, "4", tax="0.6")
        t.investments.broker_interest("2026-12-05", typed.id, "1.5")
        t.investments.broker_fee("2026-12-06", typed.id, "3")
        by_hand = {a.currency: t.reporting.account_balance(a.id, "2026-12-31") for a in [typed, *t.accounts.pockets(typed.id)]}
        assert imported == by_hand
        assert t.investments.holding(eur.id, sap.id, "2026-12-31") == D("2")
    finally:
        t.db.close()


def test_a_problem_row_is_reported_and_the_rest_post(c, setup):
    ibkr = _ibkr(c)
    odd = STATEMENT.replace(b"Dividends,Data,Total", b"Dividends,Data,USD,2026-12-03,ZZZZ(US0000000000) Cash Dividend,7\n"
                                                      b"Dividends,Data,Total")
    done = BrokerImport(c).post(ibkr.id, read_ibkr(odd))
    problems = [r for r in done.rows if r.status == "problem"]
    assert [r.event.symbol for r in problems] == ["ZZZZ"] and "No holding of ZZZZ" in problems[0].message
    assert done.count("posted") == 7


def test_only_an_ibkr_statement_and_only_a_brokerage(c, setup):
    accounts, _ = setup
    with pytest.raises(LightningError):
        read_ibkr(b"Date,Amount\n2026-09-01,10\n")
    with pytest.raises(LightningError):
        BrokerImport(c).preview(accounts["cib"].id, read_ibkr(STATEMENT))


def test_the_import_page_previews_then_posts(c, setup):
    ibkr = _ibkr(c)
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    page = client.get(f"/accounts/{ibkr.id}/broker-import")
    assert page.status_code == 200 and "Interactive Brokers" in page.text
    preview = client.post(f"/accounts/{ibkr.id}/broker-import", files={"file": ("activity.csv", STATEMENT, "text/csv")})
    assert preview.status_code == 200 and "QQQM" in preview.text and "Record it from your bank" in preview.text
    assert c.reporting.account_balance(ibkr.id, "2026-12-31") == D("2000")       # nothing posted yet
    done = client.post(f"/accounts/{ibkr.id}/broker-import", data={"confirm": "1"},
                       files={"file": ("activity.csv", STATEMENT, "text/csv")}, follow_redirects=False)
    assert done.status_code == 200 and "Positions match" in done.text
    assert c.reporting.account_balance(ibkr.id, "2026-12-31") == D("907.90")
