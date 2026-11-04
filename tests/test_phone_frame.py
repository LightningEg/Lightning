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
    assert 'class="phone-kpis"' in html and html.count('class="phone-kpi ') == 2  # C06.1, 3AN4: two tiles, Net worth and Left in plan
    assert "Savings rate" not in html and "Investing rate" not in html  # they live on Financial health (owner, 2026-11-02)
    assert "stat-tile-spark" not in html  # no sparkline in a phone tile
    fold = phone.get("/overview/fold/money-in").text  # the money-in fold loads when opened (backend roadmap B1)
    assert "chart-sankey" not in html + fold and 'class="phone-flow"' in fold  # C07.3.3
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
    pick = phone.get("/accounts/add-transaction?pick=1").text
    assert "To which account?" in pick and "/accounts/1/transaction/new" in pick


def test_add_opens_on_the_amount_with_an_account_already_chosen(phone):
    """3AN3 (C05.2): no list of accounts first. Without a remembered account Add opens on the one used most; after an entry
    it opens on that account; the sheet's From chip changes it. ?pick=1 still shows the list."""
    phone.cookies.delete("lightning_last_account")
    first = phone.get("/accounts/add-transaction").text
    assert "To which account?" not in first and 'name="amount"' in first and "autofocus" in first
    assert 'data-account-chip' in first and "data-sms-paste" in first
    sheet = phone.get("/accounts/2/transaction/new").text
    category = re.search(r'<option value="(\d+)" data-movement="OUTFLOW"', sheet).group(1)
    phone.post("/accounts/2/transaction/new", data={
        "__session": token(sheet, "__session"), "kind": "out", "amount": "7", "category_id": category,
        "counterparty": "Kiosk two", "date": "2026-10-06", "return_to": "/accounts/2"})
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


def test_one_navigation_the_app_bar_title_is_plain_text_and_every_old_menu_page_is_still_reachable(phone):
    """3AN2: the app bar's page menu (a second way to move) is gone; the title is text. Each page it used to reach is
    a tab, a row on More, or reached from a page that has its own way back."""
    more = phone.get("/more").text
    for path in PAGES + ("/more", "/review", "/plan/reserves"):
        html = phone.get(path).text
        assert "phone-page-menu" not in html and "phone-page-grid" not in html and "⌄" not in html, path
    assert 'class="phone-appbar-title"' in phone.get("/").text
    tabs = ("/", "/budget", "/transactions")
    for href in ("/plan", "/investments", "/accounts", "/settings", "/financial-health", "/review", "/birdview/expenses",
                 "/plan/reserves"):
        assert f'href="{href}"' in more, href
    for href in tabs:
        assert f'href="{href}"' in phone.get("/").text
    assert 'href="/profiles"' in phone.get("/settings").text  # Profile and lock, from Settings
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


def test_more_is_flat_and_the_weekly_review_keeps_more_chosen(phone):
    """IV-3AL4 and IV-3AL7: More has no card of buttons (a bill's row opens its pay sheet) and no subtitles; the
    weekly review, reached from More, keeps More chosen with ‹ More in the app bar."""
    more = phone.get("/more").text
    assert 'class="btn small"' not in more and "Backups, language" not in more
    assert more.index('id="bills-heading"') < more.index('id="money-heading"') < more.index('id="settings-heading"')
    assert re.search(r'class="phone-row phone-hub-bill[^"]*" data-popup-open href="/plan/items/\d+/pay', more)
    review = phone.get("/review").text
    assert re.search(r'class="phone-tab is-chosen" href="/more"', review)
    assert 'class="phone-back" href="/more"' in review and '<a class="btn" href="/">' not in review


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
        ("/settings", "/more", "More"),
        ("/rules", "/more", "More"),
        ("/categories", "/more", "More"),
        ("/counterparties", "/more", "More"),
        ("/checks", "/more", "More"),
        ("/investments/planner", "/investments", "Investments"),
        ("/accounts/1/import", "/accounts/1", "Accounts"),
        ("/settings?section=budget", "/budget", "Budget"),
    ):
        html = phone.get(path).text
        assert f'class="phone-back" href="{destination}"' in html
        assert f'<span>{label}</span></a>' in html
    html = phone.get('/transactions', headers={'referer': 'http://127.0.0.1:9861/budget'}).text
    assert 'class="phone-back" href="/budget"' in html


def test_phone_settings_use_more_instead_of_five_tabs(phone):
    for path in ("/settings", "/rules", "/categories", "/counterparties", "/checks"):
        assert 'class="plan-tabs-bar section-tabs"' not in phone.get(path).text
    more = phone.get("/more").text
    for path in ("/settings", "/rules", "/categories", "/counterparties", "/checks"):
        assert f'href="{path}"' in more
