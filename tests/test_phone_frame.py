"""On the phone app every page renders in the phone frame (guideline Part C).

What a browser must measure (nothing scrolls sideways at 360 and 320, C12) is in `tools/phone_check.py`; it
needs Playwright and runs locally. This test needs no browser: the frame, its five sections and no desktop
leftovers."""
import re

import pytest
from fastapi.testclient import TestClient

from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Credentials

from test_profile_app import create, token

PAGES = ("/", "/birdview/expenses", "/financial-health", "/budget", "/plan", "/plan/recurring", "/plan/loans",
         "/plan/reserves", "/investments", "/accounts", "/transactions", "/settings", "/checks")


@pytest.fixture(scope="module")
def phone(tmp_path_factory):
    folder = tmp_path_factory.mktemp("phone")
    cfg = Credentials("http://127.0.0.1:9861")
    app = profile_app(cfg, folder / "docs", devices=Devices(folder / "app", port=0), phone=True)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        page = browser.get("/")
        browser.post("/demo", data={"__session": token(page.text, "__session")})
        yield browser


@pytest.mark.parametrize("path", PAGES)
def test_every_page_renders_in_the_phone_frame(phone, path):
    page = phone.get(path)
    assert page.status_code == 200
    html = page.text
    assert html.count('class="phone-appbar"') == 1 and html.count('class="phone-tabbar"') == 1
    assert 'class="shell"' not in html and 'class="side"' not in html  # no desktop sidebar
    assert "Ctrl K" not in html  # C12: no keyboard hints on a phone
    assert html.count('class="section-bar"') <= 1
    assert "viewport-fit=cover" in html and "/static/phone.css" in html
    assert "/static/phone-fields.js" in html  # a tapped field opens empty, its old text back if left empty
    names = re.findall(r'class="phone-tab-name">([^<]+)<', html)
    assert names == ["Overview", "Budget", "Add", "Transactions", "More"]  # phone overhaul 2026-10-22: words, Add in the middle


def test_the_chosen_section_and_the_period_words(phone):
    html = phone.get("/budget").text
    assert re.search(r'class="phone-tab is-chosen" href="/budget" aria-current="page"', html)
    overview = phone.get("/").text
    assert ">Monthly<" not in overview and 'class="period-buttons"' not in overview  # one month stepper, no sideways chips
    assert 'class="phone-period-sheet"' in overview and ">Last month<" in overview  # the month opens Choose period
    assert re.search(r'class="phone-tab is-chosen" href="/more"', phone.get("/plan").text)  # Cash planning lives on More
    assert re.search(r'class="phone-tab is-chosen" href="/transactions"', phone.get("/transactions").text)


def test_the_pc_keeps_its_own_frame(tmp_path):
    cfg = Credentials("http://127.0.0.1:9862")
    app = profile_app(cfg, tmp_path / "docs", devices=Devices(tmp_path / "app", port=0))
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        html = browser.get("/").text
    assert 'class="shell"' in html and "phone-tabbar" not in html and "phone.css" not in html


def test_overview_uses_the_phone_forms(phone):
    html = phone.get("/").text
    assert 'class="phone-kpis"' in html and html.count('class="phone-kpi ') <= 4  # C06.1: four tiles, 2 × 2
    assert "stat-tile-spark" not in html  # no sparkline in a phone tile
    assert "chart-sankey" not in html and 'class="phone-flow"' in html  # C07.3.3
    assert "chart-cfall" not in html and "scheme-flow" in html  # C07.3.2: the waterfall as rows
    assert 'class="mcal"' not in html and 'class="phone-months"' in html  # C07.3.4
    assert re.search(r'class="phone-lead">[\d,]+ <small>EGP</small>', html)  # whole EGP on the big figure


@pytest.mark.parametrize("path, marker", [("/budget", 'class="phone-plan-bar'), ("/plan", 'id="plan-build"'),
                                          ("/investments", 'id="holdings-heading"')])
def test_budget_cash_and_investments_have_phone_designs(phone, path, marker):
    html = phone.get(path).text
    assert marker in html and "<table" not in html  # C07.2: tables become rows
    assert "stat-tile-spark" not in html and "btn-planner" not in html  # no sparkline; the tab is the way in
    assert html.count('class="phone-kpi ') <= 4


def test_an_account_is_a_day_list_and_the_sheet_saves(phone):
    page = phone.get("/accounts/1").text
    assert "<table" not in page and 'class="phone-day"' in page and 'class="phone-tab phone-add" href="/accounts/1/transaction/new' in page  # C08, C05.2
    assert 'type="checkbox"' not in page  # no checkbox column
    sheet = phone.get("/accounts/1/transaction/new").text
    assert 'inputmode="decimal"' in sheet and 'type="date"' in sheet and 'class="btn primary phone-save"' in sheet
    assert "Cancel" not in sheet  # C12: no two buttons side by side; back or swipe closes the sheet
    category = re.search(r'<option value="(\d+)" data-movement="OUTFLOW"', sheet).group(1)
    saved = phone.post("/accounts/1/transaction/new", data={
        "__session": token(sheet, "__session"), "kind": "out", "amount": "12.50", "category_id": category,
        "counterparty": "Phone kiosk", "date": "2026-10-06", "return_to": "/accounts/1"})
    assert saved.status_code == 200 and saved.url.path == "/accounts/1"
    assert "Phone kiosk" in phone.get("/accounts/1").text


def test_accounts_add_button_asks_which_account(phone):
    assert 'href="/accounts/add-transaction"' in phone.get("/accounts").text
    pick = phone.get("/accounts/add-transaction").text
    assert "To which account?" in pick and "/accounts/1/transaction/new" in pick


def test_profile_pages_on_the_phone_name_no_folders(phone):
    html = phone.get("/profiles").text  # unlocked: settings; locked: the chooser
    assert "on this phone" in html and "on this computer" not in html
    assert "Use another profile location" not in html and "Full database path" not in html


def test_a_profile_can_be_created_where_hard_links_are_refused(tmp_path, monkeypatch):
    """Android refuses hard links in app storage; creating a profile must still work there."""
    import os

    def refuse(*args, **kwargs):
        raise PermissionError("hard links are not allowed here")
    monkeypatch.setattr(os, "link", refuse)
    cfg = Credentials("http://127.0.0.1:9863")
    app = profile_app(cfg, tmp_path / "docs", devices=Devices(tmp_path / "app", port=0), phone=True)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        assert app.session.container is not None and app.session.paths.db_path.exists()


def test_settings_on_the_phone_leads_to_pairing_sms_and_the_profile(phone):
    html = phone.get("/settings").text
    assert 'href="/profiles/devices"' in html and 'href="/sms"' in html and 'href="/profiles"' in html
    assert "Pair a PC" in phone.get("/profiles/devices").text


def test_overview_puts_needs_you_before_latest(phone):
    html = phone.get("/").text
    assert html.index('class="card phone-needs') < html.index('aria-labelledby="latest-heading"')
