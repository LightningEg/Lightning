"""The phone's Transactions tab (phone overhaul 2026-10-22): find, check and sort a payment with one thumb.

Search, the chips (All, In, Out, Transfers, To sort), the month stepper with Select beside it, the period's
Money in and Money out, the list with each day's net. The chips are ?kind= on the register route; without it,
and on the PC, the register is what it always was."""
from __future__ import annotations

import re
from decimal import Decimal as D
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def _phone(c) -> TestClient:
    app = create_app(c)

    @app.middleware("http")
    async def use_phone(request, call_next):
        request.state.phone = True
        return await call_next(request)

    return TestClient(app)


@pytest.fixture
def month(c, setup):
    """September 2026: pay in, food and a software bill out, a move to the wallet, and two rows nobody has sorted."""
    accounts, cats = setup
    cib, wallet = accounts["cib"], accounts["wallet"]
    t = c.transactions
    t.record_in_account(cib.id, "2026-09-02", "45000", cats["EXP.WORK.SALARY"].id, None, "ACME Egypt", "")
    t.record_in_account(cib.id, "2026-09-03", "-1200", cats["EXP.PERSONAL.FOOD"].id, None, "Carrefour", "")
    t.record_in_account(cib.id, "2026-09-04", "-300", cats["EXP.WORK.SOFTWARE"].id, None, "Figma", "")
    t.record_transfer("2026-09-05", cib.id, wallet.id, "2000")
    # What an import posts before anyone chose a category.
    t.record_outflow("2026-09-06", cib.id, "80", c.categories.get_by_code("EXP.UNACCOUNTED").id, counterparty="Kiosk",
                     allow_system_category=True)
    t.record_inflow("2026-09-07", cib.id, "500", c.categories.get_by_code("INC.UNACCOUNTED").id, counterparty="Someone",
                    allow_system_category=True)
    t.record_in_account(cib.id, "2026-10-02", "-700", cats["EXP.PERSONAL.FOOD"].id, None, "Seoudi", "")
    return c, accounts, cats


def _queries(html: str, path: str = "/transactions") -> list[dict]:
    """Every link on the page into ``path``, as its query."""
    found = []
    for href in re.findall(r'href="([^"]*)"', html):
        url = urlsplit(unescape(href))
        if url.path == path:
            found.append({k: v[0] for k, v in parse_qs(url.query).items()})
    return found


def _has(queries: list[dict], **wanted: str) -> bool:
    return any(all(query.get(k) == v for k, v in wanted.items()) for query in queries)


def _names(html: str) -> list[str]:
    return re.findall(r'<span class="phone-txn-who"><b>([^<]+)</b>', html)


def test_the_chips_are_one_row_with_the_count_of_rows_to_sort(month):
    c, accounts, _ = month
    page = _phone(c).get("/transactions?month=2026-09").text
    chips = re.search(r'<nav class="phone-chips phone-reg-chips".*?</nav>', page, re.S).group(0)
    assert [re.sub(r"<[^>]+>", " ", chip).split() for chip in re.findall(r"<a [^>]*>.*?</a>", chips, re.S)] == [
        ["All"], ["In"], ["Out"], ["Transfers"], ["To", "sort", "2"]]
    assert 'class="phone-chip is-chosen"' in chips and chips.count("is-chosen") == 1
    # The count is the period's: October has nothing to sort.
    october = _phone(c).get("/transactions?month=2026-10").text
    assert 'class="phone-chip-n"' not in october and ">To sort<" in october


def test_each_chip_narrows_the_list(month):
    c, accounts, _ = month
    phone = _phone(c)
    everything = _names(phone.get("/transactions?month=2026-09").text)
    assert {"ACME Egypt", "Carrefour", "Figma", "Kiosk", "Someone"} <= set(everything)
    assert set(_names(phone.get("/transactions?month=2026-09&kind=in").text)) == {"ACME Egypt", "Someone"}
    assert set(_names(phone.get("/transactions?month=2026-09&kind=out").text)) == {"Carrefour", "Figma", "Kiosk"}
    moved = phone.get("/transactions?month=2026-09&kind=transfer").text
    assert "Transfer" in moved and not {"ACME Egypt", "Carrefour"} & set(_names(moved))
    assert set(_names(phone.get("/transactions?month=2026-09&kind=unsorted").text)) == {"Kiosk", "Someone"}
    # An unknown kind is ignored, as is a missing one.
    assert _names(phone.get("/transactions?month=2026-09&kind=nonsense").text) == everything
    # The chip keeps the other choices, and the chosen one is Nile.
    out = phone.get("/transactions?month=2026-09&q=a&kind=out").text
    assert re.search(r'<a class="phone-chip is-chosen" href="[^"]*kind=out"', out)
    assert _has(_queries(out), month="2026-09", q="a", kind="in")
    assert {"month": "2026-09", "q": "a"} in _queries(out)      # All drops only the kind


def test_the_tiles_are_the_periods_cash_flow(month):
    c, accounts, _ = month
    flow = c.reporting.cash_flow("2026-09-01", "2026-09-30")
    page = _phone(c).get("/transactions?month=2026-09").text
    tiles = re.search(r'<section class="phone-kpis phone-reg-kpis".*?</section>', page, re.S).group(0)
    assert f"+{flow.inflows:,.0f}" in tiles and f"−{flow.outflows:,.0f}" in tiles
    assert flow.inflows == D("45500") and flow.outflows == D("1580")   # the move to the wallet is neither
    # All time is the whole ledger's; an account's own page has its own, and only once a period is chosen.
    whole = c.reporting.cash_flow("1900-01-01", "9999-12-31")
    assert f"+{whole.inflows:,.0f}" in _phone(c).get("/transactions").text
    cib = accounts["cib"].id
    assert "phone-reg-kpis" not in _phone(c).get(f"/accounts/{cib}").text
    assert "+45,500" in _phone(c).get(f"/accounts/{cib}?month=2026-09").text


def test_a_search_makes_the_tiles_those_of_what_it_found(month):
    c, _, _ = month
    page = _phone(c).get("/transactions?q=Carrefour").text
    tiles = re.search(r'<section class="phone-kpis phone-reg-kpis".*?</section>', page, re.S).group(0)
    assert "−1,200" in tiles and ">0<" in tiles


def test_the_tab_has_no_back_link_but_an_accounts_page_has(month):
    c, accounts, _ = month
    phone = _phone(c)
    tab = phone.get("/transactions").text
    assert 'class="phone-back"' not in tab and 'class="phone-appbar-title"' in tab   # the mark and the page's name
    assert 'class="phone-back" href="/accounts"' in phone.get(f"/accounts/{accounts['cib'].id}").text


def test_each_day_carries_its_net(month):
    c, _, _ = month
    page = _phone(c).get("/transactions?month=2026-09").text
    assert 'class="phone-day-net"' in page
    assert re.search(r'<span class="phone-day-net">\+45,000</span>', page)


def test_the_month_stepper_keeps_what_you_searched_and_ends_at_this_month(month):
    c, _, _ = month
    phone = _phone(c)
    page = phone.get("/transactions?month=2026-09&q=Kiosk&kind=out").text
    bar = re.search(r'<div class="phone-reg-bar">.*?<div class="phone-reg-bar-end">', page, re.S).group(0)
    assert {"q": "Kiosk", "kind": "out", "month": "2026-08"} in _queries(bar)
    assert {"q": "Kiosk", "kind": "out", "month": "2026-10"} in _queries(bar)
    # This month is the last: the arrow forward is a dimmed mark, not a link.
    now = phone.get("/transactions?month=2026-12").text   # conftest pins today to 2026-12-31
    assert 'class="phone-reg-step is-off"' in now
    # With no month chosen the control says All time and has no arrows.
    free = phone.get("/transactions").text
    assert "All time" in free and 'aria-label="Previous month"' not in free


def test_the_sheet_offers_the_periods_and_year_to_date_is_the_registers_own_preset(month):
    c, _, _ = month
    phone = _phone(c)
    page = phone.get("/transactions").text
    asked = _queries(page)
    assert {"preset": "year_to_date"} in asked and {"month": "2026-11"} in asked   # last month, with today pinned to December
    ytd = phone.get("/transactions?preset=year_to_date").text
    assert "Year to date" in ytd and "ACME Egypt" in ytd
    custom = phone.get("/transactions?preset=custom&date_from=2026-09-03&date_to=2026-09-04").text
    assert set(_names(custom)) == {"Carrefour", "Figma"} and "2026-09-03 to 2026-09-04" in custom


def test_select_value_updates_views_and_activity_are_still_there(month):
    c, accounts, _ = month
    phone = _phone(c)
    page = phone.get("/transactions?month=2026-09").text
    assert _has(_queries(page), month="2026-09", select="1")                      # Select (C08.5)
    assert 'href="/activity"' in page and 'href="/transactions/deleted"' in page  # in the ⋯ menu
    assert 'id="phone-view-name"' in page and "Save view" in page                # Views
    selecting = phone.get("/transactions?month=2026-09&select=1").text
    assert 'id="phone-merge-selected"' in selecting and 'id="phone-bulk"' in selecting and "Done" in selecting
    # The account's page keeps its own ⋯, now with Review activity in it.
    cib = accounts["cib"].id
    assert 'href="/activity"' in phone.get(f"/accounts/{cib}").text


def test_value_updates_stay_reachable(c, setup):
    account = c.account_flows.open_account("THNDR 2", "BROKERAGE", "2026-09-01", "10000")
    asset = c.assets.create_investment("First fund", "FUND.EQUITY", "F1")
    c.investments.add_holding(account.id, asset.id, "10", "1000", "2026-09-01")
    c.assets.set_price(asset.id, "2026-09-30", "110")
    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")
    page = _phone(c).get(f"/accounts/{account.id}").text
    assert "Show value updates (1)" in page


def test_the_pc_register_is_unchanged_without_kind(month):
    c, accounts, _ = month
    pc = TestClient(create_app(c))
    page = pc.get("/transactions?month=2026-09").text
    assert "phone-reg" not in page and "phone-chip" not in page and "phone-kpi" not in page
    assert {"ACME Egypt", "Carrefour", "Kiosk"} <= set(re.findall(r"ACME Egypt|Carrefour|Kiosk", page))
    assert "kind=" not in page   # no chip, no parameter
    # The parameter is there for a PC caller too, and narrows the same way.
    only_in = pc.get("/transactions?month=2026-09&kind=in").text
    assert "row-in" in only_in and "row-out" not in only_in and "row-transfer" not in only_in


def test_the_unsorted_rows_are_counted_in_the_reporting_service(month):
    c, accounts, cats = month
    found = c.reporting.register_unsorted(None, "2026-09-01", "2026-09-30")
    assert len(found) == 2 and len(c.reporting.register_unsorted(accounts["wallet"].id, "2026-09-01", "2026-09-30")) == 0
    assert c.reporting.register_flows(accounts["cib"].id, "2026-09-01", "2026-09-30") == (D("45500"), D("1580"))
    assert c.reporting.register_flows(None, "2026-09-01", "2026-09-30") == (D("45500"), D("1580"))


def test_saved_views_are_listed_in_their_sheet_and_open_with_their_summary(month):
    c, _, _ = month
    phone = _phone(c)
    opened = phone.post("/transactions/views", follow_redirects=True,
                        data={"name": "September", "preset": "custom", "date_from": "2026-09-01", "date_to": "2026-09-30"})
    assert opened.status_code == 200 and "Views: September" in opened.text
    assert "Summary and export" in opened.text and "Delete view" in opened.text
    assert "2026-09-01 to 2026-09-30" in opened.text and "Carrefour" in opened.text and "Seoudi" not in opened.text
    assert 'class="phone-row is-chosen"' in opened.text      # the open view is ticked in the sheet
    listed = phone.get("/transactions").text
    assert "<span>September</span>" in listed and "Summary and export" not in listed
    # A view of all time says All time, not the far dates behind it.
    everything = phone.post("/transactions/views", follow_redirects=True, data={"name": "Everything", "preset": "all_time"})
    assert re.search(r'<summary class="phone-period-now"[^>]*>All time</summary>', everything.text)
    assert "9999-12-31" not in "".join(re.findall(r'<nav class="phone-chips.*?</nav>', everything.text, re.S))
