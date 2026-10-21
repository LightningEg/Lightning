"""The Arabic UI shows no English system text: every key PC page and the phone pages, drawn in Arabic with the
Mohab sample, have no visible text, title, aria-label or placeholder with an English word (3 or more Latin
letters) except names a person typed, codes and the few identifiers listed here."""
from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.samples import load_mohab_2026
from lightning.ui.i18n import localize_html, translate
from lightning.ui.web import create_app

PC_PAGES = ("/exports/all", "/plan/purchases/new", "/", "/budget", "/plan", "/plan/recurring", "/plan/loans", "/plan/reserves", "/investments",
            "/investments/prices", "/accounts", "/settings", "/search", "/rules", "/categories", "/counterparties",
            "/checks", "/financial-health", "/birdview/expenses", "/transactions", "/money-from-others", "/zakat")
PERIODS = ("period=ytd", "period=all", "period=month&month=2026-09", "period=custom&date_from=2026-03&date_to=2026-08")
PERIOD_PAGES = ("/", "/budget", "/birdview/expenses", "/investments", "/transactions", "/financial-health")
SETTINGS_SECTIONS = ("budget", "currencies", "document", "financial-health", "targets", "valuations", "assets-valuations", "zakat")
EXTRA_PAGES = ("/accounts/1", "/accounts/2", "/accounts/3", "/accounts/6", "/accounts/1/edit", "/accounts/1/reconcile",
               "/accounts/1/transaction/new", "/accounts/1/import", "/accounts/1/ownership/new", "/accounts/new",
               "/accounts/currencies", "/accounts/6/items/new", "/budget/raise?month=2026-10", "/budget/move?month=2026-10",
               "/budget/fill?month=2026-10", "/plan/items/new?kind=BILL", "/plan/items/new?kind=LOAN",
               "/plan/items/2/pay", "/investments/planner", "/investments/prices/markets", "/investments/assets/new",
               "/investments/assets/13/edit", "/investments/new?kind=holding&account=4", "/investments/holding/11", "/investments/reevaluations", "/rules/new",
               "/transactions/315", "/transactions/315/edit-popup", "/t/OUT-2026-08-12-001", "/transactions/deleted",
               "/reserves", "/add-transaction", "/investments/targets", "/search?q=a")
PHONE_EXTRA = ("/accounts/1", "/accounts/6", "/plan/loans", "/plan/recurring", "/plan/reserves", "/investments/holding/11",
               "/transactions/315", "/accounts/1/transaction/new", "/budget/raise?month=2026-10", "/search?q=a")
PHONE_PAGES = ("/exports/all", "/plan/purchases/new", "/", "/budget", "/plan", "/investments", "/accounts", "/transactions", "/birdview/expenses",
               "/financial-health", "/settings", "/categories", "/zakat")

# Brand, keyboard keys, data sources and the one prompt meant to be pasted into an AI tool.
ALLOWED_WORDS = {"Lightning", "Ctrl", "Enter", "Esc", "TradingView", "Yahoo", "Finance", "Mubasher", "Nasdaq",
                 "NYSE", "Arca", "Xetra", "Cboe", "BZX", "Analyze", "Excel", "UCITS", "American", "Thndr"}
LATIN = re.compile(r"[A-Za-z][A-Za-z']+")


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip, self.found = [], []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "textarea", "pre"):
            self.skip.append(tag)
        for name, value in attrs:
            if name in ("title", "aria-label", "placeholder", "alt") and value:
                self.found.append(value)

    def handle_endtag(self, tag):
        if self.skip and self.skip[-1] == tag:
            self.skip.pop()

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.found.append(data.strip())


def _english(page: str, names: set[str]) -> list[str]:
    parser = _Text()
    parser.feed(page)
    bad = []
    names = sorted(names, key=len, reverse=True)
    for text in parser.found:
        for name in names:
            text = text.replace(name, " ")
        text = re.sub(r"[A-Z]{2,5}-\d{4}-\d\d-\d\d-\d{3}", " ", text)
        text = re.sub(r"\S+\.[A-Za-z0-9]+|\S*/\S+", " ", text)  # file names, paths and versions
        words = [w for w in LATIN.findall(text) if not w.isupper() and w not in ALLOWED_WORDS]
        if words:
            bad.append(text[:100])
    return bad


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_TODAY", "2026-10-02")
        patch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
        c = build(tmp_path_factory.mktemp("ar") / "t.db")
        load_mohab_2026(c)
        yield c, _typed_names(c)
        c.db.close()


def _typed_names(c) -> set[str]:
    """Every account, counterparty, plan, asset and note in the sample: what a person typed stays as typed.
    Built-in category, asset-class and currency names are left out, so they must be shown in Arabic."""
    con = getattr(c.db, "conn", None) or getattr(c.db, "connection", None) or c.db
    names = set()
    own = {"financial_assets": "is_cash = 0 AND code NOT LIKE 'GLD:%' AND code NOT LIKE 'REF:%'"}
    for table in ("financial_assets", "accounts", "transactions", "counterparties", "counterparty_aliases",
                  "money_from_others", "cash_reserves", "planned_items", "cd_certificates",
                  "physical_item_valuations", "physical_item_trade_details", "other_asset_valuations", "physical_items",
                  "saved_views"):
        columns = [row[1] for row in con.execute(f"PRAGMA table_info({table})")]
        for column in ("name", "notes", "description", "institution", "counterparty", "alias", "item_kind", "memo"):
            if column in columns:
                where = own.get(table, "1")
                names.update(r[0] for r in con.execute(f"SELECT {column} FROM {table} WHERE {where}")
                             if isinstance(r[0], str))
    for note in [n for n in names if "#" in n]:   # a tag is shown as its own chip beside the rest of the note
        names |= set(re.findall(r"#\w+", note)) | {re.sub(r"\s*#\w+", "", note).strip()}
    names |= {translate(n, "ar") for n in names}  # a typed note that begins with a system word is half-translated
    return {n for n in names if len(n) > 2}


def _client(c, phone: bool):
    app = create_app(c)
    if phone:
        inner = app

        async def phone_app(scope, receive, send):
            if scope["type"] == "http":
                scope.setdefault("state", {})["phone"] = True
            await inner(scope, receive, send)
        app = phone_app
    client = TestClient(app)
    assert client.post("/settings/locale", data={"locale": "ar"}, follow_redirects=False).status_code == 303
    return client


@pytest.mark.parametrize("phone", [False, True], ids=["pc", "phone"])
def test_arabic_pages_have_no_english_system_text(sample, phone):
    c, names = sample
    # System category names are stored in English and shown translated; a person's own names stay as typed.
    user_names = names
    client = _client(c, phone)
    problems = {}
    for path in (PHONE_PAGES if phone else PC_PAGES):
        page = client.get(path)
        assert page.status_code == 200, path
        assert 'dir="rtl"' in page.text
        bad = _english(page.text, user_names)
        if bad:
            problems[path] = sorted(set(bad))[:6]
    assert not problems, problems


@pytest.mark.parametrize("phone", [False, True], ids=["pc", "phone"])
def test_arabic_period_variants_and_detail_pages_have_no_english_system_text(sample, phone):
    c, names = sample
    client = _client(c, phone)
    paths = [f"{page}?{period}" for page in PERIOD_PAGES for period in PERIODS]
    paths += [f"/settings?section={section}" for section in SETTINGS_SECTIONS]
    paths += list(PHONE_EXTRA if phone else EXTRA_PAGES)
    problems = {}
    for path in paths:
        page = client.get(path)
        if page.status_code == 404:
            continue  # a page the sample has no row for
        assert page.status_code == 200, path
        bad = _english(page.text, names)
        if bad:
            problems[path] = sorted(set(bad))[:6]
    assert not problems, problems


def test_localize_html_translates_text_and_attributes_and_leaves_data():
    page = '<p title="Save">Save</p><b>Carrefour</b><script>var a="Save";</script>'
    out = localize_html(page)
    assert 'title="حفظ"' in out and ">حفظ<" in out
    assert "Carrefour" in out and 'var a="Save"' in out


def test_patterns_and_months():
    assert translate("Delete Eating Out", "ar") == "احذف المطاعم"
    assert translate("Oct 2026", "ar") == "أكتوبر 2026"
    assert translate("Personal › Food & Groceries", "ar") == "شخصي › الأكل والبقالة"


def test_a_name_or_list_closing_a_sentence_is_translated():
    """Keynotes close a list of category names with a full stop (Budget › Categories over plan)."""
    assert translate("Transportation.", "ar") == "المواصلات."
    assert translate("Transportation, Eating Out and 2 more.", "ar") == "المواصلات، المطاعم و2 كمان."
    assert translate("CIB, THNDR", "ar") == "CIB, THNDR"  # typed names stay as typed


def test_dates_are_iso_and_month_columns_keep_time_left_to_right(sample):
    """A06.1 and A06.2: no "1 January 2026"; the month grid is a time axis, so it does not mirror, and its short
    labels are month numbers rather than English initials."""
    c, _ = sample
    client = _client(c, False)
    investments = client.get("/investments").text
    body = investments[investments.index("</head>"):]
    assert "1 يناير" not in body and "1 January" not in body
    assert "-01-01" in body  # Dividends collected: from yyyy-01-01 to today
    overview = client.get("/").text
    if "mcal-months" in overview:
        assert 'class="cal-months mcal-months" dir="ltr"' in overview
        assert re.search(r"<i>(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)</i>", overview) is None


@pytest.mark.parametrize("phone", [False, True], ids=["pc", "phone"])
def test_the_browser_translations_load_before_the_page_scripts(sample, phone):
    """Page scripts (the category count, dialogs) call window.lightningT as they run, so it is set in the head."""
    c, _ = sample
    page = _client(c, phone).get("/categories").text
    assert page.index("window.lightningT=") < page.index("</head>")


def test_choosing_arabic_in_settings_carries_to_the_profile_pages(sample):
    """Profile settings and the locked chooser cannot read the encrypted settings, so they read this cookie."""
    c, _ = sample
    client = _client(c, False)
    response = client.post("/settings/locale", data={"locale": "ar"}, follow_redirects=False)
    assert "lightning_ui_locale=ar" in response.headers.get("set-cookie", "")
    response = client.post("/settings/locale", data={"locale": "fr"}, follow_redirects=False)
    assert "lightning_ui_locale=en" in response.headers.get("set-cookie", "")


def test_arabic_pages_use_the_mirrored_stylesheets_and_they_match_their_source(sample):
    """style.rtl.css, phone.rtl.css and profiles.rtl.css are written by tools/build_rtl_css.js from the English files:
    an Arabic page links them, an English page never does, and none is older than its source."""
    import hashlib
    from pathlib import Path
    static = Path(__file__).resolve().parents[1] / "lightning" / "ui" / "static"
    for source in ("style", "phone", "profiles"):
        head = (static / f"{source}.rtl.css").read_text(encoding="utf-8").split("\n", 1)[0]
        digest = hashlib.sha256((static / f"{source}.css").read_bytes()).hexdigest()[:16]
        assert digest in head, f"{source}.css changed: run tools/build_rtl_css.js"
    c, _names = sample
    arabic = _client(c, False).get("/").text
    assert "/static/style.rtl.css" in arabic and "/static/style.css" not in arabic
    assert "/static/phone.rtl.css" in _client(c, True).get("/").text
    english_client = TestClient(create_app(c))
    english_client.post("/settings/locale", data={"locale": "en"}, follow_redirects=False)
    english = english_client.get("/").text
    assert "/static/style.css" in english and ".rtl.css" not in english
    english_client.post("/settings/locale", data={"locale": "ar"}, follow_redirects=False)  # the sample is shared
