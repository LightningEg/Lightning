"""BV-12AG: a save never reloads the page you are on (owner, 2026-11-13: on everywhere, each page checked).

Every PC page's content is one part (base.html, data-refresh="page") that app.js swaps in place after a save. This test
opens every tab and the pages they link to in Mohab's year, swaps each in place and checks the page still works: the
same event listeners on the same kinds of elements before and after, and no script error. A page that cannot be
swapped faithfully loads the ordinary way; the only ones allowed to are those holding a control app.js sets up when a
page first opens (RELOAD_ONLY in app.js): today the transaction registers. Then the cases a swap must not hide: a form
answered with a page of its own, and a language change, which redraws the whole window."""
import re
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from lightning.runtime.app import SessionGate
from lightning.runtime.http import Guard, Host
from lightning.runtime.roles import SessionRole
from lightning.samples import load_mohab_2026
from lightning.ui.sections import SECTIONS
from lightning.ui.web import create_app
from tests.browser_support import require_chromium

# Pages that keep loading whole after a save, and why (the register's selection, inline edit and right-click menu are
# set up once when the page opens). Listed for the owner in ai/ARCHITECTURE.md, UI contract, Save in place.
FULL_LOAD = re.compile(r"^/(transactions(/\d+)?|deposits/\d+|accounts/\d+|accounts/\d+/import/\d+)$")
SKIP = re.compile(r"^/(static|exports|samples|profiles|__|sync|journal)(/|$)|logout|/lock|\.(csv|json|xlsx|png|svg|ics|pdf|zip)$|/download|/export")
RELOAD_ONLY = (".ledger, .transaction-select, .category-input, .counterparty-input, .import-category, "
               ".import-transfer-suggestion, .investment-entry-form, .quantity-input, [data-unrequires], "
               "select[data-chip-add], [data-command-open], [data-fullscreen-toggle], #page-jump, input[data-strength]")
LISTENS_ON_PAGE = """() => [...document.querySelectorAll('[data-refresh] script:not([src])')]
    .some(s => /(document|window)\\.addEventListener|setInterval/.test(s.textContent))"""


@pytest.fixture
def app_page(c):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    chromium = require_chromium()
    load_mohab_2026(c)
    session = SimpleNamespace(container=c, paths=None, journal=None, borrowed=None, role=SessionRole.HOME,
                              token="test-swap-session", csrf="test-swap-csrf")
    app = create_app(c)

    @app.get("/profiles/health")
    async def health():
        return {"locked": False, "session": session.token}

    host = Host(lambda cfg: Guard(SessionGate(app, session), cfg)).start()
    try:
        with sync_playwright() as p:
            with p.chromium.launch(executable_path=chromium, args=["--no-sandbox"]) as browser:
                context = browser.new_context(viewport={"width": 1400, "height": 900})
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(host.launch_url)
                yield page, context.new_cdp_session(page), host, errors
    finally:
        host.stop()


def _listeners(cdp):
    """Event listeners on the content part, counted by element kind and event: what a swap must set up again."""
    found = cdp.send("Runtime.evaluate", {"expression": "[...document.querySelectorAll('[data-refresh], [data-refresh] *')]"})
    props = cdp.send("Runtime.getProperties", {"objectId": found["result"]["objectId"], "ownProperties": True})
    counts = {}
    for prop in props["result"]:
        if not prop["name"].isdigit():
            continue
        listeners = cdp.send("DOMDebugger.getEventListeners", {"objectId": prop["value"]["objectId"]})["listeners"]
        kind = re.sub(r"-\d+", "", prop["value"]["description"].split(" ")[0])  # date-field-3 is numbered per load
        for listener in listeners:
            key = f"{kind}:{listener['type']}"
            counts[key] = counts.get(key, 0) + 1
    return counts


def _pages(page, host):
    """Every tab, then each page a tab links to (one per path), in the order found."""
    paths = []
    for href in [tab.href for section in SECTIONS for tab in section.tabs]:
        if href not in paths:
            paths.append(href)
    for tab in list(paths):
        page.goto(host.origin + tab)
        for href in page.eval_on_selector_all("[data-refresh] a[href]", "links => links.map(a => a.getAttribute('href'))"):
            parts = urlsplit(href)
            if parts.netloc or not parts.path.startswith("/") or SKIP.search(parts.path):
                continue
            if all(urlsplit(p).path != parts.path for p in paths):
                paths.append(parts.path + (f"?{parts.query}" if parts.query else ""))
    return paths


def test_every_page_still_works_after_a_save_in_place(app_page):
    page, cdp, host, errors = app_page
    paths = _pages(page, host)
    assert len(paths) > 40, paths
    whole, broken = [], []
    for path in paths:
        try:
            response = page.goto(host.origin + path)
        except Exception as error:  # a link that is a file (a calendar, an export) starts a download, not a page
            if "Download is starting" in str(error):
                continue
            raise
        if not response or response.status >= 400 or urlsplit(page.url).path != urlsplit(path).path:
            continue  # a link that sends you on, or a page this year has nothing for
        if not page.locator("[data-refresh]").count():
            continue  # a popup's own fragment, never a page of its own
        errors.clear()
        if page.locator(f"[data-refresh] :is({RELOAD_ONLY})").count() or page.evaluate(LISTENS_ON_PAGE):
            assert page.evaluate("() => window.lightningRefreshInPlace()") is False, path
            whole.append(urlsplit(path).path)
            continue
        before = _listeners(cdp)
        assert page.evaluate("() => window.lightningRefreshInPlace()") is True, path
        page.wait_for_timeout(50)
        after = _listeners(cdp)
        changed = sorted(f"{k} {before.get(k, 0)}→{after.get(k, 0)}" for k in set(before) | set(after)
                         if before.get(k, 0) != after.get(k, 0))
        if changed or errors:
            broken.append((path, changed, list(errors)))
    assert not broken, broken
    assert all(FULL_LOAD.match(path) for path in whole), [p for p in sorted(set(whole)) if not FULL_LOAD.match(p)]
    assert "/transactions" in whole


def test_a_save_on_an_ordinary_page_stays_and_its_message_shows(app_page):
    from playwright.sync_api import expect
    page, _cdp, host, errors = app_page
    page.goto(host.origin + "/budget/fill")
    page.evaluate("() => { window.__stayed = 1; }")
    page.locator('form[action^="/budget/fill"] input[name="selected"]').first.check()
    page.locator("[data-refresh] form[method=post] button").first.click()  # sends you to Budget: an ordinary load
    expect(page.locator("main > .flash").first).to_contain_text("Applied")
    assert urlsplit(page.url).path == "/budget"
    page.goto(host.origin + "/budget?open_group=all")
    page.evaluate("() => { window.__stayed = 1; }")
    page.locator('form[action="/budget/suggestions"] button[value=track]').first.evaluate("b => b.click()")
    expect(page.locator("main > .flash").first).to_contain_text("Preference saved.")
    assert page.evaluate("() => window.__stayed") == 1
    assert errors == []


def test_a_form_answered_with_a_page_of_its_own_shows_that_page(app_page, c):
    from playwright.sync_api import expect
    page, _cdp, host, _errors = app_page
    parent = c.categories.get_by_code("EXP.PERSONAL").id
    page.goto(host.origin + "/categories")
    # A post the server answers with a page rather than a redirect: the category form again, with its error.
    page.evaluate("""(parent) => { const f = document.createElement('form'); f.method = 'post';
        f.action = '/categories/new?parent=' + parent; f.innerHTML = '<input name="name" value=""><button>Save</button>';
        const session = document.querySelector('input[name=__session]'); if (session) f.append(session.cloneNode());
        document.querySelector('[data-refresh]').append(f); f.querySelector('button').click(); }""", parent)
    expect(page).to_have_url(re.compile(r"/categories/new\?parent=\d+$"))
    expect(page.locator("main form")).not_to_have_count(0)
    assert page.locator("[data-refresh]").count() == 1


def test_a_language_change_redraws_the_whole_window(app_page):
    from playwright.sync_api import expect
    page, _cdp, host, _errors = app_page
    page.goto(host.origin + "/settings")
    page.select_option("#ui-locale", "ar")
    expect(page.locator("html")).to_have_attribute("lang", "ar-EG")
    assert "نظرة عامة" in page.locator("aside").inner_text()
    page.select_option("#ui-locale", "en")
    expect(page.locator("html")).to_have_attribute("lang", "en")
