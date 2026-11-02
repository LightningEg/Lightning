"""Search on the phone (IV-3AN, 3AN6; closes the search half of IV-3T3): payments first, live as you type, then names, then pages
and actions under their own heading; no "Ctrl K", no Search button."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lightning.ui.web import create_app
from test_phone_capture import _phone, month  # noqa: F401  (the fixture and the phone client)


# ---- Search for money -------------------------------------------------------------------------------------------------

def test_search_finds_payments_first_then_names_then_pages(month):
    c, accounts, cats = month
    phone = _phone(c)
    page = phone.get("/search?q=Carrefour").text
    assert "Ctrl K" not in page and ">Search<" not in page.split("phone-live-search")[1].split("</form>")[0]   # no hint, no button
    assert page.index('id="search-payments"') < page.index('id="search-names"')
    assert page.count('class="phone-txn"') == 2 and "Carrefour" in page                                  # both payments, as rows
    assert 'href="/transactions?q=Carrefour"' in page                                                      # the name behind them
    by_amount = phone.get("/search?q=1200").text
    assert "Carrefour" in by_amount and 'id="search-payments"' in by_amount                             # an amount finds the payment
    by_category = phone.get("/search?q=Groceries").text
    assert by_category.count('class="phone-txn"') >= 3
    pages = phone.get("/search?q=budget").text
    assert 'id="search-pages"' in pages and 'href="/budget"' in pages
    assert pages.find('id="search-pages"') > pages.find("phone-live-search")
    nothing = phone.get("/search?q=zzzzzz").text
    assert "Nothing matches" in nothing


def test_search_is_live_the_results_alone_come_as_a_fragment(month):
    c, _, _ = month
    phone = _phone(c)
    fragment = phone.get("/search?q=Seoudi&fragment=1").text
    assert "<html" not in fragment and "Seoudi" in fragment and 'class="phone-txn"' in fragment
    assert 'data-live-search="#search-results"' in phone.get("/search").text
    launcher = phone.get("/search").text
    assert 'id="search-pages"' in launcher and 'id="search-payments"' not in launcher
    pc = TestClient(create_app(c)).get("/search").text
    assert "data-live-search" not in pc and "Press Ctrl K" in pc                                          # the PC page is what it was
    assert phone.get("/search?q=Seoudi&format=json").json()["results"]                                      # the command bar's JSON stays


def test_search_shows_at_most_eight_payments_and_links_to_all_of_them(month):
    c, accounts, cats = month
    for day in range(1, 13):
        c.transactions.record_in_account(accounts["cib"].id, f"2026-08-{day:02d}", "-10", cats["EXP.PERSONAL.FOOD"].id, None, "Bakery", "")
    page = _phone(c).get("/search?q=Bakery").text
    assert page.count('class="phone-txn"') == 8 and "See all 12" in page


