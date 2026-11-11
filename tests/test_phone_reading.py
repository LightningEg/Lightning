"""The phone's reading screens (IV-3AN: 3AN7 Budget, 3AN9 no wall of zeros, 3AN12 the rest, 3AN10 Arabic): what each
screen leads with, what opens a sheet, and that Arabic has no English word.

Figures come from the services; these tests read what the pages say, as the phone shows them. Digits become
Arabic-Indic in the browser (arabic-numbers.js), so the one-digit-system check is tools/phone_check.py's."""
import re

import pytest
from fastapi.testclient import TestClient

from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Credentials

from test_profile_app import create, token
from tests.screens import said

NAMES = ("Lightning", "EGP", "Microbus", "Carrefour", "ACME", "Landlord")  # the brand, the currency and names the sample typed


@pytest.fixture(scope="module")
def phone(tmp_path_factory):
    folder = tmp_path_factory.mktemp("phone-reading")
    cfg = Credentials("http://127.0.0.1:9866")
    app = profile_app(cfg, folder / "docs", devices=Devices(folder / "app", port=0), phone=True)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        page = browser.get("/")
        browser.post("/demo", data={"__session": token(page.text, "__session")})
        yield browser


def _text(html: str) -> str:
    return re.sub(r"(?s)<(script|style)\b.*?</\1>|<[^>]+>", " ", html)


def _english(html: str) -> list[str]:
    """Latin words of three letters or more in what a page shows, less the brand, the currency and typed names."""
    text = _text(html)
    for name in NAMES:
        text = text.replace(name, "")
    return re.findall(r"[A-Za-z]{3,}", text)


def _in_arabic(browser, *paths):
    session = token(browser.get("/settings").text, "__session")
    browser.post("/settings/locale", data={"locale": "ar", "__session": session})
    try:
        return [browser.get(path).text for path in paths]
    finally:
        browser.post("/settings/locale", data={"locale": "en", "__session": session})


def test_the_category_sheet_and_its_payments_are_arabic(phone):
    """3AN7 + 3AN10: a category sheet and its payments fragment have no English word."""
    html = phone.get("/budget?period=month").text   # the old Budget still draws the category sheets (a query steps past the new one)
    src = re.search(r'data-fold-src="(/budget/category/\d+/payments\?month=[\d-]+)"', html).group(1)
    page, filled, empty = _in_arabic(phone, "/budget?period=month", src, src.split("?")[0] + "?month=2020-01")
    assert _english(page) == [] and _english(filled) == [] and _english(empty) == []
    sheet = page[page.index('class="phone-sheet-panel"'):]
    assert any(word in sheet[:sheet.index("</details>")] for word in ("المعدل", "عدّيت الحد"))  # the pace or over sentence
    assert "آخر المدفوعات" in filled and "لسه ماصرفتش" in empty


def test_cash_planning_forecast_months_ahead_and_what_is_promised_are_rows_that_open_sheets(phone):
    html = phone.get("/plan").text
    forecast = html[html.index('id="plan-forecast"'):]
    assert forecast.count('class="phone-sheet-row"') >= 3  # the forecast, each month ahead, what is promised
    assert 'class="card phone-card" id="plan-forecast"' not in html and "<article" not in forecast.split("What is promised")[1]
    assert "Each month ahead" in forecast and "chart-trend" in forecast and "What you owe" in forecast.split("What is promised")[1]
    assert re.search(r'(?s)<details class="phone-sheet-row">\s*<summary[^>]*>.*?Each month ahead', html)


def test_recurring_leads_with_the_list_and_links_the_fixed_costs_ratio_to_financial_health(phone):
    html = phone.get("/plan/recurring").text
    assert html.index('id="recurring-list"') < html.index('id="recurring-totals"')
    rows = html[html.index('id="recurring-list"'):html.index('id="recurring-totals"')]
    assert not re.search(r"\d\.00\b", rows)  # rows drop ".00" (C10)
    assert re.search(r'<a class="phone-row" href="/financial-health"><span>Fixed costs to income', html)
    assert "<table" not in html and "plan-figure" not in html


def test_reserves_names_financial_health_in_the_app_bar(phone):
    html = phone.get("/plan/reserves").text
    assert re.search(r'class="phone-appbar-title">Financial health<', html)
    assert "Safety" not in re.search(r'(?s)<header class="phone-appbar">.*?</header>', html).group(0)


def test_investments_draws_no_chart_card_until_it_has_two_months(phone, monkeypatch):
    """3AN9: a card that only says "Not enough history yet" is a wall of nothing; the holdings follow the hero."""
    from lightning.ui import charts
    assert "phone-invest-card" in phone.get("/investments").text  # two months or more: the chart, then the holdings
    real = charts.trend
    monkeypatch.setattr(charts, "trend", lambda *a, **k: {**real(*a, **k), "too_short": True})
    html = phone.get("/investments").text
    assert "phone-invest-card" not in html and "phone-invest-seg" not in html
    assert html.index('id="holdings-heading"') < html.index('id="alloc-heading"')  # the owner's order after the hero


def test_spending_opens_on_this_month_with_the_lead_four_categories_other_and_more_analysis(phone):
    from lightning.core.dates import month_of, today
    html = phone.get("/birdview/expenses").text
    assert 'class="phone-appbar-title">Spending<' in html and "Birdview" not in html and "Expense analysis" not in html
    assert re.search(r'<summary class="phone-period-now"[^>]*>%s</summary>' % said(month_of(today())), html)  # this month, not last
    assert "so-far-line" not in html
    where = html[html.index('id="where-heading"'):]
    rows = re.findall(r'<a class="phone-row" href="[^"]+"><span>([^<]+)<small>\d+% of money out', where)
    assert 1 <= len(rows) <= 5 and ("Other" in rows or len(rows) <= 4)
    assert ">More analysis<" in where and 'data-fold-src="/birdview/expenses/more?' in where
    for heavy in ("treemap", "cal-months", "multiples", "cluster-bars", "chart-sankey", "phone-flow", "phone-months", "<table"):
        assert heavy not in html, heavy  # the heat map, flows, small multiples and month grid left the first page


def test_spending_more_analysis_loads_apart_with_the_heat_map_and_the_flows(phone):
    fragment = phone.get("/birdview/expenses/more").text
    assert "<html" not in fragment
    for part in ("cal-months", "phone-flow", "phone-months"):
        assert part in fragment, part


def test_spending_light_first_page_does_not_draw_the_rest(phone, monkeypatch):
    """3AN12: the first page reads only the lead and the category rows; its heavy charts are never worked out."""
    from lightning.ui import visuals

    def boom(*args, **kwargs):
        raise AssertionError("the first page drew a chart that lives in More analysis")
    for name in ("day_calendars", "cash_flow_charts", "month_calendar", "spending_trend", "counterparty_bars", "account_bars"):
        monkeypatch.setattr(visuals, name, boom)
    assert phone.get("/birdview/expenses").status_code == 200


def _phone_client(c, monkeypatch, today):
    from lightning.ui.web import create_app
    from lightning.ui.phone.router import mount_phone
    monkeypatch.setenv("LIGHTNING_TODAY", today)
    app = create_app(c)
    mount_phone(app)   # the real phone app: its router answers first (3AY11)

    @app.middleware("http")
    async def as_phone(request, call_next):
        request.state.phone = True
        return await call_next(request)

    return TestClient(app)


def test_a_month_with_nothing_spent_offers_last_month_with_its_figure(c, setup, monkeypatch):
    """3AN9: no wall of zeros; Spending opens on this month and says what last month was."""
    accounts, cats = setup
    c.transactions.record_in_account(accounts["cib"].id, "2026-09-03", "-1200", cats["EXP.PERSONAL.FOOD"].id, None, "Carrefour", "")
    html = _phone_client(c, monkeypatch, "2026-10-02").get("/birdview/expenses").text
    assert "No spending in this period" in html and "More analysis" not in html
    assert re.search(r'<a class="phone-row" href="/birdview/expenses\?period=month&amp;month=2026-09"><span>Last month<small>September 2026</small></span><b>1,200</b>', html)


def test_spending_more_analysis_is_arabic(phone):
    page, fragment = _in_arabic(phone, "/birdview/expenses", "/birdview/expenses/more")
    assert _english(page) == [] and _english(fragment) == []
