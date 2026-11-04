"""NF-7Y: what "What you own" leans on that is old or missing. The notes explain; they never change an amount, and
an input with nothing to date (no price, no rate) is told apart from one that is simply old."""
from decimal import Decimal as D

import pytest

from lightning.database.currencies import CurrencyRegistry
from lightning.planning.freshness import NO_PRICE, NO_RATE, STALE_PRICE, STALE_RATE


@pytest.fixture
def held(c, setup):
    """A stock bought on 2026-09-10 with a price from that day, and 10 dollars held."""
    accounts, _ = setup
    stock = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI")
    c.transactions.record_transfer("2026-09-02", accounts["cib"].id, accounts["thndr"].id, "30000")
    c.investments.buy_total("2026-09-10", accounts["thndr"].id, stock.id, "10", "1000")
    c.assets.set_price(stock.id, "2026-09-10", "100")
    return c, stock


def kinds(c, day):
    return [(note.kind, note.subject, note.source_date) for note in c.freshness.for_what_you_own(day)]


def test_a_recent_price_says_nothing_and_an_old_one_says_from_when(held):
    c, stock = held
    assert not [k for k in kinds(c, "2026-09-30") if k[0] in (STALE_PRICE, NO_PRICE)]
    notes = kinds(c, "2026-12-31")                                         # 112 days after the last price
    assert (STALE_PRICE, stock.name, "2026-09-10") in notes
    note = next(n for n in c.freshness.for_what_you_own("2026-12-31") if n.kind == STALE_PRICE)
    assert note.known and note.link == "/investments/prices" and note.figure == "what_you_own"
    assert c.freshness.days_old(note, "2026-12-31") == 112


def test_a_holding_with_no_price_is_unknown_not_old():
    """A holding valuation could not price is told apart from an old one: no date, and a way to fix it."""
    from types import SimpleNamespace
    from lightning.planning.freshness import FreshnessService
    reporting = SimpleNamespace(stale_prices=lambda day: [], fx_positions=SimpleNamespace(all=lambda a, b: []))
    position = SimpleNamespace(at=lambda day, **kwargs: SimpleNamespace(unvalued=("THNDR — Gold fund — no price",)))
    note, = FreshnessService(reporting, position).for_what_you_own("2026-09-30")
    assert (note.kind, note.subject, note.source_date, note.known) == (NO_PRICE, "THNDR", None, False)
    assert note.link == "/investments/prices"
    assert FreshnessService.days_old(note, "2026-09-30") is None


def test_a_foreign_currency_without_a_recent_rate_is_stale_then_missing(c):
    CurrencyRegistry(c.db).register("USD")
    c.fx.save("USD", "2026-09-01", "50")
    c.account_flows.open_account("Dollars", "BANK", "2026-09-01", "10", currency="USD", opening_balance_date="2026-09-01")
    assert (STALE_RATE, "USD", "2026-09-01") in kinds(c, "2026-09-30")       # 29 days: still used, shown "as of"
    c.fx.save("USD", "2026-09-29", "52")
    assert not [k for k in kinds(c, "2026-09-30") if k[1] == "USD"]
    gone = next(n for n in c.freshness.for_what_you_own("2026-12-31") if n.subject == "USD")
    assert gone.kind == NO_RATE and not gone.known and "tab=rates" in gone.link


def test_the_notes_never_change_an_amount(held):
    c, _ = held
    before = (c.position.at("2026-12-31").what_you_own, c.reporting.net_worth("2026-12-31").total)
    c.freshness.for_what_you_own("2026-12-31")
    after = (c.position.at("2026-12-31").what_you_own, c.reporting.net_worth("2026-12-31").total)
    assert before == after and isinstance(before[0], D)


def test_the_explanation_popup_lists_them_in_both_languages(held):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    c, _ = held
    app = create_app(c)
    with TestClient(app) as browser:
        page = browser.get("/explain/owned?period=all&month=2026-12")
        assert page.status_code == 200
        assert "is valued from a price dated 2026-09-10, 112 days ago." in page.text
        assert "What this figure leans on" in page.text and 'href="/investments/prices"' in page.text
        browser.post("/settings/locale", data={"locale": "ar"}, follow_redirects=False)
        arabic = browser.get("/explain/owned?period=all&month=2026-12")
        assert arabic.status_code == 200
        assert "متقيّم بسعر بتاريخ" in arabic.text and "الرقم ده معتمد على إيه" in arabic.text
        assert "is valued from a price" not in arabic.text


def test_cash_checks_have_exact_31_day_boundary_and_historical_cutoff(c, setup):
    bank = setup[0]['cib']
    c.reconciliation.close(bank.id, '2026-09-30', '50000')
    assert not [n for n in c.freshness.for_free_cash('2026-10-31') if n.subject == bank.name]
    note, = [n for n in c.freshness.for_free_cash('2026-11-01') if n.subject == bank.name]
    assert note.kind == 'old_check' and note.source_date == '2026-09-30'
    earlier, = [n for n in c.freshness.for_free_cash('2026-09-29') if n.subject == bank.name]
    assert earlier.kind == 'no_check' and earlier.source_date is None
    assert c.reporting.account_balance(bank.id) == 50000


def test_foreign_cash_rate_affects_forecast_but_not_free_cash(c):
    CurrencyRegistry(c.db).register('USD')
    c.fx.save('USD', '2026-09-01', '50')
    c.account_flows.open_account('Dollar bank', 'BANK', '2026-09-01', '10', currency='USD')
    assert not c.freshness.for_free_cash('2026-09-30')
    assert any(n.kind == STALE_RATE for n in c.freshness.for_forecast('2026-09-30'))


def test_unconfirmed_certificate_receipts_explain_cash_without_assuming_receipt(c, setup):
    from test_workflow_receipts import _certificate
    _certificate(c, setup[0])
    before = c.db.conn.total_changes
    notes = c.freshness.for_free_cash('2026-10-02')
    assert any(n.kind == 'unconfirmed_receipt' and n.source_date == '2026-10-01' for n in notes)
    assert c.db.conn.total_changes == before


def test_pending_replica_edits_are_explained_without_entering_cash(devices):
    from test_journal_finance import groups
    from lightning.sync.journal.proxy import JournalServices
    _, pc = devices
    c = JournalServices(pc)
    before = pc.balances()
    pc.save(groups(pc))
    for method in (c.freshness.for_what_you_own, c.freshness.for_free_cash, c.freshness.for_forecast):
        assert any(n.kind == 'pending_edits' and n.link == '/journal' for n in method('2026-09-30'))
    assert pc.balances() == before


@pytest.mark.parametrize('phone', [False, True])
@pytest.mark.parametrize('locale', ['en', 'ar'])
def test_cash_and_forecast_explanations_are_accessible_in_both_frames(c, setup, phone, locale):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    c.settings.set('locale', locale)
    app = create_app(c)
    @app.middleware("http")
    async def frame(request, call_next):
        request.state.phone = phone
        return await call_next(request)
    with TestClient(app) as client:
        for url in ('/explain/free-cash?period=all', '/plan/inputs'):
            response = client.get(url)
            assert response.status_code == 200
            assert 'data-freshness="no_check"' in response.text
            if locale == 'ar':
                assert 'Review inputs' not in response.text


from test_journal_finance import devices  # noqa: E402,F401


def test_foreign_cash_explicitly_counted_as_spendable_uses_rate_notes(c):
    CurrencyRegistry(c.db).register('USD')
    c.fx.save('USD','2026-09-01','50')
    a=c.account_flows.open_account('Spendable dollars','BANK','2026-09-01','10',currency='USD')
    c.accounts.set_spendable(a.id,True)
    assert any(n.kind==STALE_RATE for n in c.freshness.for_free_cash('2026-09-30'))


def test_zero_foreign_account_without_a_scheduled_use_does_not_affect_forecast(c):
    CurrencyRegistry(c.db).register('USD')
    c.account_flows.open_account('Unused dollar bank','BANK','2026-09-01','0',currency='USD')
    assert not any(n.kind in (NO_RATE,STALE_RATE) for n in c.freshness.for_forecast('2026-09-30'))
