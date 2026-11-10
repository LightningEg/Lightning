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
    assert "viewport-fit=cover" in html and "/static/phone-bundle.css" in html
    assert "/static/phone-fields.js" in html  # a tapped field opens empty, its old text back if left empty
    names = re.findall(r'class="phone-tab-name">([^<]+)<', html)
    assert names == ["Home", "Budget", "Add", "Activity", "Money"]  # IV-3AY10: Home, Budget, Add, Activity, Money


def test_the_chosen_section_and_the_period_words(phone):
    html = phone.get("/budget").text
    assert re.search(r'class="phone-tab is-chosen" href="/budget" aria-current="page"', html)
    assert re.search(r'class="phone-tab is-chosen" href="/" aria-current="page"', phone.get("/").text)  # Home, IV-3AY10
    overview = phone.get("/?period=month").text  # the older Overview, still behind a query until 3AY11 removes it
    assert ">Monthly<" not in overview and 'class="period-buttons"' not in overview  # one month stepper, no sideways chips
    assert 'class="phone-period-sheet"' in overview and ">Last month<" in overview  # the month opens Choose period
    assert re.search(r'class="phone-tab is-chosen" href="/money"', phone.get("/plan").text)  # Cash planning lives under Money
    assert re.search(r'class="phone-tab is-chosen" href="/activity"', phone.get("/transactions").text)  # redirected to Activity


def test_the_pc_keeps_its_own_frame(tmp_path):
    cfg = Credentials("http://127.0.0.1:9862")
    app = profile_app(cfg, tmp_path / "docs", devices=Devices(tmp_path / "app", port=0))
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        html = browser.get("/").text
    assert 'class="shell"' in html and "phone-tabbar" not in html and "phone.css" not in html


def test_overview_uses_the_phone_forms(phone):
    html = phone.get("/?period=month").text
    assert 'class="phone-kpis"' in html and html.count('class="phone-kpi ') == 2  # C06.1, 3AN4: two tiles, Net worth and Left in plan
    assert "Savings rate" not in html and "Investing rate" not in html  # they live on Financial health (owner, 2026-11-02)
    assert "stat-tile-spark" not in html  # no sparkline in a phone tile
    kpis = html.split('class="phone-kpis"', 1)[1].split("</section>", 1)[0]
    tiles = kpis.split('class="phone-kpi ')[1:]
    assert all('class="phone-kpi-sub"' in tile for tile in tiles)  # 3T6: each tile compares, Left in plan under its meter
    fold = phone.get("/overview/fold/money-in").text  # the money-in fold loads when opened (backend roadmap B1)
    assert "chart-sankey" not in html + fold and 'class="phone-flow"' in fold  # C07.3.3
    assert "chart-cfall" not in html and "scheme-flow" in html  # C07.3.2: the waterfall as rows
    assert 'class="mcal"' not in html and 'class="phone-months"' in html  # C07.3.4
    assert re.search(r'class="phone-lead">[\d,]+ <small>EGP</small>', html)  # whole EGP on the big figure


@pytest.mark.parametrize("path, marker", [("/budget?period=month", 'class="phone-plan-bar'), ("/plan", 'id="plan-build"'),
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
    assert 'href="/accounts/add-transaction?return_to=/accounts%3Fview%3Dall"' in phone.get("/accounts?view=all").text  # the older list
    assert 'href="/accounts/add-transaction?return_to=/money"' in phone.get("/money").text  # Add returns to its slot (3AY7)
    pick = phone.get("/accounts/add-transaction?pick=1").text
    assert "To which account?" in pick and "/accounts/1/transaction/new" in pick


def test_add_opens_on_the_amount_with_an_account_already_chosen(phone):
    """3AN3 (C05.2): no list of accounts first. Without a remembered account Add opens on the one used most; after an entry
    it opens on that account; the sheet's From chip changes it. ?pick=1 still shows the list."""
    phone.cookies.delete("lightning_last_account")
    first = phone.get("/accounts/1/transaction/new").text
    assert "To which account?" not in first and 'name="amount"' in first and "autofocus" in first
    assert 'data-account-chip' in first and "data-sms-paste" in first
    sheet = phone.get("/accounts/2/transaction/new").text
    category = re.search(r'<option value="(\d+)" data-movement="OUTFLOW"', sheet).group(1)
    saved = phone.post("/accounts/2/transaction/new", data={
        "__session": token(sheet, "__session"), "kind": "out", "amount": "7", "category_id": category,
        "counterparty": "Phone kiosk", "date": "2026-10-06", "return_to": "/accounts/2"})
    assert saved.status_code == 200, re.findall(r'<[^>]*class="[^"]*(?:error|flash)[^"]*"[^>]*>(.*?)</[^>]+>', saved.text, re.S)
    quick = phone.get("/accounts/add-transaction").text
    assert "To which account?" not in quick and 'action="/accounts/2/transaction/new"' in quick
    assert "To which account?" in phone.get("/accounts/add-transaction?pick=1").text


def test_paste_bank_sms_reads_one_message_into_the_sheet(phone):
    """Phone roadmap M3: a pasted CIB message comes back as the sheet's fields; nothing is saved."""
    sheet = phone.get("/accounts/1/transaction/new").text
    before = phone.get("/transactions").text.count("IRAN ZAMALEK")
    text = ("تم سحب مبلغ  EGP 5000.00  من بطاقة الخصم المباشر المنتهية بـ **7351 من CIB KZ IRAN ZAMALEK "
            "في 04/10/26 19:28 ، الرصيد المتاح EGP 12904.50")
    read = phone.post("/sms/read-one", data={"__session": token(sheet, "__session"), "text": text})
    assert read.status_code == 200
    body = read.json()
    assert body["amount"] == "5000.00" and body["kind"] == "out" and body["date"] == "2026-10-04"
    assert "IRAN ZAMALEK" in body["counterparty"]
    assert phone.get("/transactions").text.count("IRAN ZAMALEK") == before
    nothing = phone.post("/sms/read-one", data={"__session": token(sheet, "__session"), "text": "Your code is 1234"})
    assert nothing.status_code == 422


def test_paste_english_card_message_fills_amount_date_and_shop(phone):
    """IV-7AJ: a message no bank pattern reads still fills what it says: amount, way, its own day and the shop."""
    sheet = phone.get("/accounts/1/transaction/new").text
    text = "Your debit card ending with 1234 was charged EGP 250.00 at TALABAT on 08/11/26"
    read = phone.post("/sms/read-one", data={"__session": token(sheet, "__session"), "text": text})
    assert read.status_code == 200
    body = read.json()
    assert body["amount"] == "250.00" and body["kind"] == "out"
    assert body["date"] == "2026-11-08" and body["counterparty"] == "TALABAT"


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
    assert '<table' not in html and 'settings-row' in html  # Settings itself is rows, not a stacked table
    assert "Pair a PC" in phone.get("/profiles/devices").text


def test_overview_puts_needs_you_before_latest(phone):
    html = phone.get("/?period=month").text
    assert html.index('class="card phone-needs') < html.index('aria-labelledby="latest-heading"')


def test_one_navigation_the_app_bar_title_is_plain_text_and_every_old_menu_page_is_still_reachable(phone):
    """3AN2: the app bar's page menu (a second way to move) is gone; the title is text. Each page it used to reach is
    a tab, a row on More, or reached from a page that has its own way back."""
    money = phone.get("/money").text
    for path in PAGES + ("/money", "/money/accounts", "/money/bills", "/activity", "/review", "/plan/reserves"):
        html = phone.get(path).text
        assert "phone-page-menu" not in html and "phone-page-grid" not in html and "⌄" not in html, path
    assert 'class="phone-appbar-title"' in phone.get("/").text
    tabs = ("/", "/budget", "/activity", "/money")
    reviews = phone.get("/money/reviews").text
    for href in ("/investments", "/money/accounts", "/money/bills", "/settings", "/financial-health", "/plan/reserves",
                 "/money/reviews"):
        assert f'href="{href}"' in money, href  # Money reaches every page More used to reach
    for href in ("/money/report", "/plan", "/birdview/expenses", "/review"):
        assert f'href="{href}"' in reviews, href  # the analysis, behind Money's one Reports and reviews row (IV-11H)
    for href in tabs:
        assert f'href="{href}"' in phone.get("/").text
    assert 'href="/profiles"' in phone.get("/settings").text  # Profile and lock, from Settings
    for path in ("/rules", "/categories", "/counterparties", "/checks"):
        assert f'href="{path}"' in phone.get("/settings").text  # Settings destinations remain reachable
    assert 'class="phone-back"' in phone.get("/review").text


def _phone_app(c, monkeypatch, today):
    from lightning.ui.web import create_app
    monkeypatch.setenv("LIGHTNING_TODAY", today)
    app = create_app(c)

    @app.middleware("http")
    async def as_phone(request, call_next):
        request.state.phone = True
        return await call_next(request)

    return TestClient(app)


def test_one_needs_you_card_under_the_stepper_names_the_next_bill_and_opens_its_pay_sheet(c, setup, monkeypatch):
    """IV-3AL1, 3AN4 (J3): a bill due within three days is named in the Needs you card by payee, amount and days, and
    that line opens the bill's pay sheet (tap it, then Record and mark paid); no second card above the stepper, and
    Manage Needs you is the card's last row, not a loose link."""
    accounts, _ = setup
    c.planning.create(kind="BILL", name="Internet", amount="650", frequency="MONTHLY", start_date="2026-10-01",
                      account_id=str(accounts["cib"].id))
    c.planning.create(kind="BILL", name="Landlord", amount="12000", frequency="MONTHLY", start_date="2026-10-03",
                      account_id=str(accounts["cib"].id))
    c.planning.create(kind="BILL", name="Gym", amount="400", frequency="MONTHLY", start_date="2026-10-20",
                      account_id=str(accounts["cib"].id))
    html = _phone_app(c, monkeypatch, "2026-09-30").get("/").text
    assert 'class="card phone-card phone-soon' not in html and html.count('class="card phone-needs"') == 1
    strip = re.search(r'<details class="card phone-needs".*?</details>', html, re.S).group(0)
    assert html.index('class="phone-period"') < html.index('class="card phone-needs"')
    named = re.search(r'<a class="phone-needs-bill" data-popup-open href="(/plan/items/\d+/pay\?due=2026-10-01[^"]*)">([^<]+)</a>', strip)
    assert named and named.group(2) == "Internet 650 tomorrow"  # the earliest, by payee, amount and days
    assert "2 payments due soon" in strip and "Landlord" in strip and "Gym" not in strip  # Landlord is 3 days out
    assert "Mark paid" in strip  # each bill's row says what the tap does
    assert strip.rindex('href="/needs-you"') > strip.index("Landlord")
    assert html.count('href="/needs-you"') == 1


def test_a_bill_further_than_three_days_off_is_not_named(c, setup, monkeypatch):
    accounts, _ = setup
    c.planning.create(kind="BILL", name="Gym", amount="400", frequency="MONTHLY", start_date="2026-10-20",
                      account_id=str(accounts["cib"].id))
    html = _phone_app(c, monkeypatch, "2026-09-30").get("/").text
    assert "phone-needs-bill" not in html and "Gym" not in html


def test_the_due_line_says_today_tomorrow_days_and_late():
    from lightning.ui.routes.dashboard import _due_line
    text = lambda *a: (lambda s: s["text"].format(**s["values"]))(_due_line(*a))
    assert text("Landlord", "12,000", 2, 0) == "Landlord 12,000 in 2 days"
    assert text("Landlord", "12,000", 1, 0) == "Landlord 12,000 tomorrow"
    assert text("Landlord", "12,000", 0, 0) == "Landlord 12,000 today"
    assert text("Landlord", "12,000", 0, 1) == "Landlord 12,000, 1 day late"
    assert text("Landlord", "12,000", 0, 4) == "Landlord 12,000, 4 days late"


def test_the_weekly_review_keeps_money_chosen_and_the_old_more_is_gone(phone):
    """IV-3AL7: the weekly review, reached from Money, keeps Money chosen with ‹ Money in the app bar. IV-3AY11: More
    is gone; its address leads to Money."""
    review = phone.get("/review").text
    assert re.search(r'class="phone-tab is-chosen" href="/money"', review)
    assert 'class="phone-back" href="/money"' in review and '<a class="btn" href="/">' not in review
    gone = phone.get("/more?view=old", follow_redirects=False)
    assert gone.status_code in (302, 303, 307) and gone.headers["location"] == "/money"


def test_financial_health_puts_what_needs_you_under_its_lead_and_the_chart_in_its_own_card(phone):
    """Audit 10, F20 (C12: one chart per card): on the phone the savings rate over time leaves the lead card."""
    html = phone.get("/financial-health").text
    lead = re.search(r'(?s)<section class="card lead-card lead-hero".*?</section>', html).group(0)
    assert "lead-side" not in lead and "health-over-time-heading" not in lead
    assert html.index('id="health-limits-heading"') < html.index('class="card phone-card health-side"')


def test_financial_health_holds_the_savings_and_investing_rates_the_overview_gave_up(phone):
    """3AN4 (owner, 2026-11-02): both rates left the Overview's tiles; Financial health's Saving group shows them."""
    html = phone.get("/financial-health").text
    saving = html[html.index(">Saving<"):html.index(">Debt and monthly commitments<")]
    assert "Savings rate" in saving and "Investing rate" in saving
    assert 'href="/investments"' in saving


def test_needs_you_names_what_is_inside_and_a_match_is_not_a_bill():
    """3AN1 (P6): the payments group holds bills, interest to match and payments to check; each is named as itself."""
    from lightning.ui.routes.dashboard import _needs_parts
    match = {"label": "CD: 1 interest payment to match", "href": "/deposits/3#interest-receipts"}
    bill = {"label": "Bill due: Internet", "href": "/plan/items/1/pay?due=2026-12-01&back=%2F"}
    early = {"label": "Rent was paid early", "href": "/plan/items/2/pay?due=2026-12-01&back=%2F"}
    text = lambda groups: [part["text"] for part in _needs_parts(groups)]
    assert text([{"key": "payments", "count": 1, "items": [match]}]) == ["1 to match"]
    assert text([{"key": "payments", "count": 1, "items": [bill]}]) == ["1 bill"]
    assert text([{"key": "payments", "count": 3, "items": [bill, match, early]},
                 {"key": "activity", "count": 4, "items": []}]) == ["1 bill", "1 to match", "1 payment to check", "4 to sort out"][:3]
    assert "1 bill" not in text([{"key": "payments", "count": 2, "items": [match, match]}])
    assert text([{"key": "payments", "count": 2, "items": [match, match]}]) == ["{n} to match"]


def test_the_entry_sheet_has_no_balance_sentence_and_the_amount_starts_at_zero(phone):
    """3AN1 (P3): "Cash in X decreases by …; balance owned by You." is gone (it was half English in Arabic); the
    amount's placeholder is "0", not "0.00"."""
    session = token(phone.get("/accounts/1/transaction/new").text, "__session")
    for locale in ("en", "ar"):
        phone.post("/settings/locale", data={"locale": locale, "__session": session})
        sheet = phone.get("/accounts/1/transaction/new").text
        assert ('lang="ar-EG"' in sheet) == (locale == "ar")
        assert "data-transaction-effect" not in sheet and "transaction-effect" not in sheet
        assert 'placeholder="0"' in sheet and 'placeholder="0.00"' not in sheet
    phone.post("/settings/locale", data={"locale": "en", "__session": session})


def test_a_date_in_a_phone_hero_line_never_breaks_across_lines():
    """3AN1 (P13): at 320 "2026-12-01" split after a hyphen; the hero wraps every date in a no-break span."""
    from lightning.ui.web import templates
    html = templates.env.from_string(
        '{% from "phone/partials/hero.html" import hero with context %}'
        '{{ hero("Safe to spend", 1000, "About 50 a day until payday on 2026-12-01.") }}').render(base="EGP", locale="en")
    assert '<span class="nowrap">2026-12-01</span>' in html


def test_inner_pages_have_a_back_destination_without_browser_history(phone):
    for path, destination, label in (
        ("/settings", "/money", "Money"),
        ("/rules", "/money", "Money"),
        ("/categories", "/money", "Money"),
        ("/counterparties", "/money", "Money"),
        ("/checks", "/money", "Money"),
        ("/investments/planner", "/investments", "Investments"),
        ("/accounts/1/import", "/accounts/1", "Accounts"),
        ("/settings?section=budget", "/budget", "Budget"),
    ):
        html = phone.get(path).text
        assert f'class="phone-back" href="{destination}"' in html
        assert f'<span>{label}</span></a>' in html
    html = phone.get('/transactions?view=all', headers={'referer': 'http://127.0.0.1:9861/budget'}).text
    assert 'class="phone-back" href="/budget"' in html


def test_phone_settings_use_more_instead_of_five_tabs(phone):
    for path in ("/settings", "/rules", "/categories", "/counterparties", "/checks"):
        assert 'class="plan-tabs-bar section-tabs"' not in phone.get(path).text
    money = phone.get("/money").text
    assert 'href="/settings"' in money  # Settings sits behind Money; its own page leads to the rest
    settings = phone.get("/settings").text
    for path in ("/rules", "/categories", "/counterparties", "/checks"):
        assert f'href="{path}"' in settings


def test_budget_category_returns_to_budget_and_leads_with_register(phone):
    from html import unescape

    budget = phone.get('/budget?period=month').text  # the older Budget carries the category links
    match = re.search(r'href="(/transactions\?category_id=[^"]+)"', budget)
    assert match, 'the demo budget has a category link'
    page = phone.get(unescape(match.group(1)), headers={'referer': 'http://127.0.0.1:9861/budget'}).text
    assert re.search(r'class="phone-back" href="/budget(?:\?[^"]*)?"', page)
    assert 'class="phone-reg-filter"' in page and 'Category:' in page
    assert 'phone-reg-search' in page and 'class="phone-period-row phone-reg-period"' in page
    assert ' › ' not in page.split('class="phone-reg-filter"', 1)[1].split('</div>', 1)[0]


def test_loan_ratios_are_compared_rows_instead_of_an_unpaired_tile(phone):
    html = phone.get('/plan/loans').text
    ratios = html.split('data-loan-ratios', 1)[1].split('</div>', 1)[0]
    assert ratios.count('class="phone-row"') == 3
    assert 'Debt to net worth' in ratios and 'Debt to cash' in ratios and 'Loan payments to income' in ratios
    assert 'owed against' in ratios and 'a month of' in ratios
    assert 'class="stat-tiles"' not in html


def test_phone_import_uses_back_instead_of_a_second_button(phone):
    html = phone.get('/accounts/1/import').text
    assert 'class="phone-back" href="/accounts/1"' in html
    upload = html.split('enctype="multipart/form-data"', 1)[1].split('</form>', 1)[0]
    assert 'Review statement' in upload and '>Cancel</a>' not in upload


def test_phone_recurring_suggestion_keeps_dismissal_in_more_actions(phone):
    html = phone.get('/plan/recurring').text
    assert 'class="phone-suggest-actions"' in html
    actions = html.split('class="phone-suggest-actions"', 1)[1].split('</details>', 1)[0]
    assert 'Track</a>' in actions and 'class="action-menu phone-more-menu"' in actions
    assert '/not-recurring' in actions and 'Not recurring' in actions


def test_phone_profile_gate_switches_language_with_one_action(phone):
    html = phone.get('/profiles').text
    form = html.split('class="gate-language"', 1)[1].split('</form>', 1)[0]
    assert 'name="locale" value="ar"' in form and '<select' not in form
    csrf = re.search(r'name="csrf" value="([^"]+)"', form).group(1)
    arabic = phone.post('/profiles/locale', data={'csrf': csrf, 'locale': 'ar', 'return_to': '/profiles'}).text
    assert 'lang="ar-EG"' in arabic
    switched = arabic.split('class="gate-language"', 1)[1].split('</form>', 1)[0]
    assert 'name="locale" value="en"' in switched and '<select' not in switched
    csrf = re.search(r'name="csrf" value="([^"]+)"', switched).group(1)
    phone.post('/profiles/locale', data={'csrf': csrf, 'locale': 'en', 'return_to': '/profiles'})


def test_desktop_profile_gate_retains_language_select(tmp_path):
    cfg = Credentials("http://127.0.0.1:9862")
    app = profile_app(cfg, tmp_path / "docs", devices=Devices(tmp_path / "app", port=0), phone=False)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        html = browser.get("/profiles").text
        form = html.split('class="gate-language"', 1)[1].split('</form>', 1)[0]
        assert '<select' in form and 'name="locale"' in form


def test_the_safe_to_spend_card_opens_its_own_explanation():  # F11 (r24)
    from pathlib import Path
    from types import SimpleNamespace
    from decimal import Decimal
    from lightning.ui.routes.dashboard import _safe_tile
    tile = _safe_tile(SimpleNamespace(next_income_date="2026-12-01", safe_to_spend=Decimal("100"), free_cash=Decimal("400")))
    assert tile["href"] == "/plan#safe-section"
    phone_plan = Path(__file__).resolve().parents[1] / "lightning/ui/templates/phone/planning/plan.html"
    assert 'id="safe-section"' in phone_plan.read_text(encoding="utf-8")


def test_cash_planning_lists_the_next_payments_before_the_secondary_cash_figures(c):  # F6 (r24)
    from fastapi.testclient import TestClient
    from lightning.demo import build_demo
    from lightning.ui.web import create_app
    build_demo(c)
    page = TestClient(create_app(c)).get("/plan").text
    assert 'id="plan-next"' in page and 'aria-label="Your cash"' in page
    assert page.index('id="plan-next"') < page.index('aria-label="Your cash"')


def test_money_names_each_place_once_and_arabic_transfers_read_from_the_first_account(phone):
    """r29: Money listed Cash planning, Spending and Weekly review twice (the old More list was left under the new
    rows). In Arabic a transfer between two Latin-named accounts drew "CIB Payroll ← Vodafone Cash", which reads as money
    moving into CIB: each name is now isolated, so the line lays out right to left and the flipped arrow points onward."""
    import re
    money = phone.get("/money").text
    for href in ("/investments", "/plan/reserves", "/financial-health", "/money/reviews"):
        assert money.count(f'class="phone-row" href="{href}"') == 1, href
    session = token(phone.get("/accounts/1/transaction/new").text, "__session")
    try:
        phone.post("/settings/locale", data={"locale": "ar", "__session": session})
        activity = phone.get("/activity").text
        pairs = re.findall(r'<bdi translate="no">([^<]+)</bdi> (.) <bdi translate="no">([^<]+)</bdi>', activity)
        assert pairs and all(arrow == "←" for _, arrow, _ in pairs)
    finally:
        phone.post("/settings/locale", data={"locale": "en", "__session": session})
    assert re.search(r'<bdi translate="no">[^<]+</bdi> → <bdi translate="no">[^<]+</bdi>', phone.get("/activity").text)


def test_arabic_digits_and_their_separators_come_from_one_face():
    """r29: the lead figure (Readex Pro) drew ٬ as a comma and a row (Noto Sans Arabic) as a raised tick, so one screen
    showed two thousands separators. Readex now draws every Arabic-Indic digit and separator in body text too."""
    from pathlib import Path
    static = Path(__file__).resolve().parents[1] / "lightning" / "ui" / "static"
    fonts = (static / "fonts" / "fonts.css").read_text(encoding="utf-8")
    assert '"Lightning Arabic Figures"' in fonts and "ReadexPro-400-700-arabic.woff2" in fonts and "U+0660-066C" in fonts
    for name in ("style.css", "style.rtl.css"):
        css = (static / name).read_text(encoding="utf-8")
        assert '--body:"Lightning Arabic Figures",Manrope,"Noto Sans Arabic"' in css, name


@pytest.mark.parametrize("path", PAGES)
def test_phone_pages_have_a_status_bar_colour_and_no_text_arrows(phone, path):
    """3BG1/3BG4: the browser build tints its status bar, and no arrow is a text glyph (it points backwards in Arabic)."""
    html = phone.get(path).text
    assert 'name="theme-color"' in html
    body = html.split("<body", 1)[1]
    assert not re.search(r">\s*[›‹]\s*<", body) and not re.search(r"\s›</(?:b|a|span)>", body)


def test_phone_text_fields_name_their_enter_key(phone):
    """3BG4: the keyboard's Enter key says next or done on a form's text fields."""
    html = phone.get("/accounts/1/transaction/new").text
    assert 'id="popup-amount"' in html and re.search(r'<input[^>]*id="popup-amount"[^>]*enterkeyhint="(next|done)"', html)


def test_phone_settings_are_the_phones_rows_and_the_rest_is_best_on_a_pc(phone):
    """IV-11H (C11.3): Appearance, Language, This phone, Bank SMS, Backup, Privacy, About and licences, Delete your
    data; the PC's tools (sale factors, target allocation, price files) are one Best on your PC line, not sections."""
    html = phone.get("/settings").text
    for words in ("Appearance", "Language", "This phone", "Bank SMS", "Back up now", "Read the privacy notice", "About and licences",
                  "Delete your data", "Best on your PC"):
        assert words in html, words
    assert 'href="https://lightningeg.com/privacy.html#app"' in html and 'href="/settings/licences"' in html
    for pc in ("Sale factors", "Ask an AI", "Settings in each tab", "another computer"):
        assert pc not in html.split("Best on your PC", 1)[0], pc
    assert "Sale factors" in phone.get("/settings?section=valuations").text   # a section still opens the shared page
    licences = phone.get("/settings/licences").text
    assert "PolyForm Noncommercial" in licences and "fastapi" in licences.casefold()
    assert 'class="phone-back" href="/settings"' in licences


def test_the_phone_app_bar_is_a_soft_well_not_near_white():
    """IV-3F: the app bar takes the well tint, so it is not the white of the cards and tab bar."""
    from pathlib import Path
    static = Path(__file__).resolve().parents[1] / "lightning" / "ui" / "static"
    for name in ("phone.css", "phone.rtl.css"):
        css = (static / name).read_text(encoding="utf-8")
        bar = css.split(".phone-appbar {", 1)[1].split("}", 1)[0]
        assert "background: var(--c-well)" in bar and "244, 248, 252" not in bar, name
