"""Navigation and entry paths used throughout the finance workspace."""

import re
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from lightning.ui.web import create_app


class _SettingsGeneralStructure(HTMLParser):
    """Capture whether the General settings card sits inside a workspace grid."""

    _void_tags = {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr",
    }

    def __init__(self):
        super().__init__()
        self.stack = []
        self.heading = None
        self.general_card_in_workspace_grid = None
        self.general_card_classes = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get("class", "").split())
        if tag == "h2":
            self.heading = ""
        if tag not in self._void_tags:
            self.stack.append((tag, classes))

    def handle_data(self, data):
        if self.heading is not None:
            self.heading += data

    def handle_endtag(self, tag):
        if tag == "h2" and self.heading is not None:
            if self.heading.strip() == "Your data":
                self.general_card_in_workspace_grid = any(
                    "workspace-grid" in classes for _, classes in self.stack
                )
                self.general_card_classes = next(
                    (classes for tag, classes in reversed(self.stack) if tag == "section"), set()
                )
            self.heading = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


def test_analysis_navigation_selects_only_the_current_page(c):
    client = TestClient(create_app(c))
    for path, current in (
        ("/birdview", "/"),  # Birdview now lives in the Overview
        ("/birdview/expenses", "/birdview/expenses"),  # Spending is its own section (question-led menu, 2026-10-28)
        ("/settings", "/checks"),  # Settings opens on Data checks (2026-10-28)
        ("/counterparties", "/checks"),
    ):
        page = client.get(path)
        assert page.status_code == 200
        active = re.findall(r'<a href="([^"]+)" class="active" aria-current="page">', page.text)
        assert active == [current]


def test_arabic_locale_persists_and_renders_rtl_with_isolated_financial_data(c):
    client = TestClient(create_app(c))
    before = client.get("/")
    assert '<html lang="en" dir="ltr"' in before.text

    saved = client.post("/settings/locale", data={"locale": "ar"}, follow_redirects=False)
    assert saved.status_code == 303
    assert c.settings.get("locale") == "ar"
    page = client.get("/")
    assert '<html lang="ar-EG" dir="rtl"' in page.text
    assert "نظرة عامة" in page.text
    assert '<b dir="ltr">' in page.text  # Amount and currency stay in a left-to-right isolate.
    stylesheet = Path("lightning/ui/static/style.css").read_text(encoding="utf-8")
    assert "unicode-bidi: isolate" in stylesheet


def test_account_uses_guided_transaction_entry_and_keeps_advanced_row_secondary(c):
    c.account_flows.open_account("Wallet", "CASH", "2026-09-01", "1000")
    client = TestClient(create_app(c))
    page = client.get("/accounts/1")
    assert page.status_code == 200
    # The quick-add row is always open on the account page (owner decision, a1d7944); the guided
    # popup form stays available for other entry points.
    assert '<tr class="add-row quick-add-row" id="quick-add">' in page.text
    assert client.get("/accounts/1/transaction/new").status_code == 200
    assert 'href="/accounts/1/import"' in page.text


def test_custom_period_apply_keeps_custom_mode(c):
    c.account_flows.open_account("Wallet", "CASH", "2026-09-01", "1000")
    client = TestClient(create_app(c))
    page = client.get("/birdview?period=custom&date_from=2026-09-01&date_to=2026-09-20")
    assert page.status_code == 200
    assert 'name="period" value="custom" class="btn small">Apply' in page.text
    # Reports are picked by the month, so the range shows as From month and To month.
    assert 'name="date_from" value="2026-09"' in page.text
    assert 'name="date_to" value="2026-09"' in page.text


def test_mobile_account_navigation_uses_a_collapsible_account_section(c):
    c.account_flows.open_account("Wallet", "CASH", "2026-09-01", "1000")
    page = TestClient(create_app(c)).get("/")
    assert page.status_code == 200
    assert '<details class="side-accounts" id="sidebar-accounts">' in page.text
    assert '<summary class="mobile-accounts-summary">' in page.text
    assert 'href="/accounts/1"' in page.text


def test_cash_planning_tabs_scroll_within_the_bar_on_narrow_viewports(c):
    client = TestClient(create_app(c))
    page = client.get("/plan")
    assert page.status_code == 200
    assert 'class="plan-tabs-bar section-tabs" aria-label="Cash planning"' in page.text
    for href in ("/plan", "/plan/recurring", "/plan/loans", "/plan/reserves"):
        assert f'href="{href}"' in page.text
    # With no income planned the forecast is an empty state, not a guess (guideline A01).
    assert "Add your salary and bills to see where your cash is heading" in page.text
    cib = c.account_flows.open_account("CIB", "BANK", "2026-09-01", "1000")
    c.planning.create(kind="INCOME", name="Salary", amount="30000", frequency="MONTHLY", start_date="2026-10-01",
                      account_id=str(cib.id), category_id=str(c.categories.get_by_code("EXP.WORK.SALARY").id))
    page = client.get("/plan")
    assert '<div class="table-scroll"><table class="plan-forecast-table">' in page.text

    stylesheet = Path("lightning/ui/static/style.css").read_text(encoding="utf-8")
    tabs_rule = re.search(r"\.main \.plan-tabs-bar\s*\{([^}]*)\}", stylesheet)
    tab_rule = re.search(r"\.main \.plan-tab\s*\{([^}]*)\}", stylesheet)
    assert tabs_rule and "max-width:100%" in tabs_rule.group(1)
    assert "overflow-x:auto" in tabs_rule.group(1)
    assert "white-space:nowrap" in tabs_rule.group(1)
    assert tab_rule and "flex:0 0 auto" in tab_rule.group(1)


def test_account_and_all_transactions_share_an_internally_scrollable_register(c):
    c.account_flows.open_account("Wallet", "CASH", "2026-09-01", "1000")
    client = TestClient(create_app(c))
    for path in ("/accounts/1", "/transactions"):
        page = client.get(path)
        assert page.status_code == 200
        assert '<div class="register-table-scroll"><table class="register-rows">' in page.text
        assert 'id="quick-add"' in page.text
        assert 'id="select-visible"' in page.text


def test_general_settings_card_is_not_nested_in_workspace_grid(c):
    page = TestClient(create_app(c)).get("/settings?section=general")
    assert page.status_code == 200
    structure = _SettingsGeneralStructure()
    structure.feed(page.text)
    assert structure.general_card_in_workspace_grid is False
    assert {"card", "settings-list"} <= structure.general_card_classes


def test_responsive_layout_css_contracts_for_budget_and_period_controls():
    stylesheet = Path("lightning/ui/static/style.css").read_text(encoding="utf-8")
    summary_container = re.search(r"\.main \.budget-top\s*\{([^}]*)\}", stylesheet)
    meters_container = re.search(r"#budget-meters\s*\{([^}]*)\}", stylesheet)
    assert summary_container and "container" in summary_container.group(1) and "inline-size" in summary_container.group(1)
    assert meters_container and "container" in meters_container.group(1) and "inline-size" in meters_container.group(1)
    container_rules = re.findall(r"@container[^\{]*\{([^}]*)\}", stylesheet, re.S)
    assert any(".main .budget-top-grid" in rule and "grid-template-columns:1fr" in rule for rule in container_rules)
    assert any(".main .bullets" in rule and "grid-template-columns:1fr" in rule for rule in container_rules)

    period_scrollers = re.findall(r"\.site-period-control \.period-buttons\s*\{([^}]*)\}", stylesheet)
    assert any(
        all(value in rule for value in ("flex-wrap:nowrap", "overflow-x:auto", "scrollbar-width:none"))
        for rule in period_scrollers
    )
    period_buttons = re.findall(r"\.site-period-control \.period-button\s*\{([^}]*)\}", stylesheet)
    assert any("flex:0 0 auto" in rule and "white-space:nowrap" in rule for rule in period_buttons)
    webkit_scrollbar = re.search(
        r"\.site-period-control \.period-buttons::-webkit-scrollbar\s*\{([^}]*)\}", stylesheet
    )
    assert webkit_scrollbar and "display:none" in webkit_scrollbar.group(1)


# Status messages are announced, and the register's balance stays inside a scrollable table.
ROOT = Path(__file__).resolve().parents[1]


def test_server_rendered_messages_have_live_region_semantics():
    template = (ROOT / "lightning/ui/templates/base.html").read_text(encoding="utf-8")

    assert 'class="flash" role="status" aria-live="polite" aria-atomic="true">{{ msg|tr(locale) }}' in template
    assert 'class="flash error" role="alert" aria-live="assertive" aria-atomic="true">{{ error|tr(locale) }}' in template


def test_flash_behavior_covers_errors_popups_and_late_insertions():
    app_js = (ROOT / "lightning/ui/static/app.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "lightning/ui/static/style.css").read_text(encoding="utf-8")

    assert 'isError ? "alert" : "status"' in app_js
    assert 'isError ? "assertive" : "polite"' in app_js
    assert "}, 5000));" in app_js
    assert "new MutationObserver" in app_js and "characterData: true" in app_js
    assert 'flashObserver.observe(popupFlashRoot,' in app_js
    assert 'flashObserver.observe(document.body' not in app_js
    assert "initFlashMessages(content, true)" in app_js  # popup responses, including validation errors
    assert "initFlashMessages(flash, true)" in app_js  # message restored after a popup save
    assert ".flash.error { background: var(--rose-soft); color: var(--ink); }" in stylesheet
    assert "@media(prefers-reduced-motion:reduce)" in stylesheet


def test_register_is_a_spreadsheet_with_a_balance_column_after_the_amount():
    register = (ROOT / "lightning/ui/templates/register.html").read_text(encoding="utf-8")
    stylesheet = (ROOT / "lightning/ui/static/style.css").read_text(encoding="utf-8")

    assert '<div class="register-table-scroll"><table class="register-rows">' in register
    for column in ("register-date-cell", "register-counterparty-cell", "register-category-cell",
                   "register-notes-cell", "register-row-action", "register-balance-cell"):
        assert column in register
    assert register.index("register-row-action") < register.index("register-balance-cell")
    assert "register-meta-line" not in register  # one line per row since 0.5 spreadsheet register
    assert 'class="action-heading"' not in register
    assert 'money(False, 0)' in register
    scroll_rule = re.search(r"\.main \.register-table-scroll\s*\{([^}]*)\}", stylesheet)
    table_rule = re.search(r"\.main \.register-table-scroll\s*>\s*table\s*\{([^}]*)\}", stylesheet)
    number_rule = re.search(r"\.num\s*\{([^}]*)\}", stylesheet)
    assert scroll_rule and "overflow-x:auto" in scroll_rule.group(1)
    assert table_rule and "min-width:0" in table_rule.group(1)
    assert number_rule and "white-space: nowrap" in number_rule.group(1)
