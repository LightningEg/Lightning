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
    position = SimpleNamespace(at=lambda day: SimpleNamespace(unvalued=("THNDR — Gold fund — no price",)))
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
