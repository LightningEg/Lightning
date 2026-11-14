"""The phone keeps its frame between pages (IT-3AO2, phone-nav.js): a tab, a link in the content or the month stepper
swaps only the app bar, the content and the tab bar, and what the new page needs still works. A page that brings its
own script loads whole, and back returns to the page before."""
from types import SimpleNamespace

import pytest

from lightning.ui.date_text import month_text

from lightning.runtime.app import SessionGate
from lightning.runtime.http import Guard, Host
from lightning.runtime.roles import SessionRole
from lightning.ui.phone.router import mount_phone
from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


@pytest.fixture
def phone(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-12")  # the plan runs on past October, so both months show the stepper
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    chromium = require_chromium()
    load_mohab_2026(c)
    session = SimpleNamespace(container=c, paths=None, journal=None, borrowed=None, role=SessionRole.HOME,
                              token="test-phone-nav-session", csrf="test-phone-nav-csrf")
    app = create_app(c)
    mount_phone(app)  # the phone app's own router: Home, Budget, Activity and Money (3AY10); Activity opens from Money (IV-11M1)

    @app.get("/profiles/health")
    async def health():
        return {"locked": False, "session": session.token}

    gate = SessionGate(app, session)
    gate.phone = True
    host = Host(lambda cfg: Guard(gate, cfg)).start()
    try:
        with sync_playwright() as p:
            with p.chromium.launch(executable_path=chromium, args=["--no-sandbox"]) as browser:
                page = browser.new_page(viewport={"width": 360, "height": 800}, is_mobile=True, has_touch=True)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(host.launch_url)
                page.goto(host.origin + "/")
                page.evaluate("window.__sameFrame = true")
                yield SimpleNamespace(page=page, origin=host.origin, errors=errors,
                                      same=lambda: page.evaluate("window.__sameFrame === true"))
    finally:
        host.stop()


def test_tabs_links_and_the_month_stepper_swap_the_page_and_keep_working(phone):
    page = phone.page
    page.click(".phone-tabbar a[href='/budget']")
    page.wait_for_function("() => location.pathname === '/budget' && document.title.startsWith('Budget')")
    assert phone.same() and page.locator(".phone-tab.is-chosen").inner_text().strip() == "Budget"

    # The new Budget's month stepper is two plain links: each swaps the page and the address carries the month.
    arrived = "(m) => new URLSearchParams(location.search).get('month') === m && !document.querySelector('main[aria-busy]')"
    shown = lambda: page.locator(".phone-month-chip > span").first.inner_text().strip()  # noqa: E731
    now = shown()
    page.click(".phone-month-chip a[aria-label='Earlier month']")
    page.wait_for_function("() => new URLSearchParams(location.search).get('month')")
    earlier = page.evaluate("() => new URLSearchParams(location.search).get('month')")
    page.wait_for_function(arrived, arg=earlier)
    assert shown() == month_text(earlier) != now and phone.same()  # the chip says the month in words (IV-3BK)
    page.click(".phone-month-chip a[aria-label='Later month']")  # the stepper of the swapped page works too
    page.wait_for_function("(m) => new URLSearchParams(location.search).get('month') > m", arg=earlier)
    assert phone.same() and shown() == now

    page.go_back()
    page.wait_for_function("(m) => document.querySelector('.phone-month-chip > span')?.textContent.trim() === m", arg=month_text(earlier))
    assert phone.same()

    page.click(".phone-tabbar a[href='/plan']")   # IV-11M1: the Plan slot
    page.wait_for_function("() => location.pathname === '/plan'")
    assert phone.same() and page.locator(".phone-tab.is-chosen").inner_text().strip() == "Plan"
    page.click(".phone-tabbar a[href='/money']")
    page.wait_for_function("() => location.pathname === '/money' && !document.querySelector('main[aria-busy]')")
    page.locator("main a[href='/activity']").first.click()   # Activity opens from Money, which stays chosen
    page.wait_for_function("() => location.pathname === '/activity'")
    assert phone.same() and page.locator(".phone-tab.is-chosen").inner_text().strip() == "Money"
    _go(page, "/activity?month=2026-09")  # a month with rows (the sample's data ends before today)
    assert page.locator(".phone-txn[data-txn]").count()

    # The register keeps its period sheet, press and hold, and row sheets behind a link that carries a filter.
    _go(page, "/transactions?period=month")
    page.click("summary.phone-period-now")  # a choice in the period sheet swaps too
    page.locator(".phone-period-panel a.phone-row").filter(has_text="All time").click()
    page.wait_for_function("() => document.querySelector('.phone-period-now')?.textContent.includes('All time')"
                           " && document.querySelector('.phone-txn[data-txn]')")
    rows = page.locator(".phone-txn[data-txn]").count()
    assert rows and page.locator(".phone-txn[data-hold-ready]").count() == rows  # press and hold is set up on them
    page.locator(".phone-txn[data-popup-open]").first.click()
    page.wait_for_selector("#app-popup[open] #app-popup-content .phone-txn-sheet")  # a row opens its sheet to look at first (3AD2)
    page.go_back()
    page.wait_for_function("() => !document.querySelector('#app-popup[open]') && location.pathname === '/transactions'")

    page.click(".phone-tabbar a[href='/money']")
    page.wait_for_function("() => location.pathname === '/money'")
    page.locator("main a[href='/plan/loans']").first.click()
    page.wait_for_function("() => location.pathname === '/plan/loans'")
    assert phone.same() and page.locator(".phone-tab.is-chosen").inner_text().strip() == "Plan"   # Loans belong to the Plan slot (IV-11M1)
    assert phone.errors == []


def _go(page, href):
    page.evaluate("(href) => { document.getElementById('go')?.remove(); const a = document.createElement('a');"
                  " a.href = href; a.id = 'go'; a.textContent = 'Go'; document.querySelector('main').prepend(a); }", href)
    page.click("#go")
    page.wait_for_function("(href) => location.pathname === href.split('?')[0] && document.readyState === 'complete'"
                           " && !document.querySelector('main[aria-busy]')", arg=href)


def test_a_swapped_page_runs_its_own_scripts_and_only_those(phone):
    """Reserves brings an inline script: it runs again on each visit (no clash with the last visit's names); a script
    without the response's nonce does not run, as on a full load; a script that listens on the whole document makes
    the page load whole."""
    page = phone.page
    listen = {"on": False}

    def add_scripts(route):
        response = route.fetch()
        nonce = response.headers["content-security-policy"].split("'nonce-")[1].split("'")[0]
        extra = (f'<script nonce="{nonce}">window.__good = (window.__good || 0) + 1;</script>'
                 '<script nonce="not-this-one">window.__bad = true;</script>')
        if listen["on"]:
            extra += f'<script nonce="{nonce}">document.addEventListener("click", () => {{}});</script>'
        route.fulfill(response=response, body=response.text().replace("</main>", extra + "</main>"))

    page.route("**/plan/reserves", add_scripts)
    _go(page, "/plan/reserves")
    assert phone.same() and page.evaluate("[window.__good, window.__bad]") == [1, None]
    _go(page, "/money")
    _go(page, "/plan/reserves")
    assert phone.same() and page.evaluate("window.__good") == 2
    listen["on"] = True
    _go(page, "/money")
    _go(page, "/plan/reserves")
    assert not phone.same()  # loaded whole
    assert phone.errors == []


def test_each_slot_keeps_its_own_stack_and_back_walks_the_slot_then_home(phone):
    """3AY4 (r25 › Cross-cutting 5): a slot's pages stack above Home; switching slots drops the last slot's pages, tapping
    the chosen slot returns to its top, and Back walks the slot, then Home."""
    page = phone.page
    at = lambda path: page.wait_for_function(  # noqa: E731
        "(p) => location.pathname === p && !document.querySelector('main[aria-busy]')", arg=path)
    page.click(".phone-tabbar a[href='/money']"); at("/money")
    page.click("a[href='/money/accounts']"); at("/money/accounts")
    page.click(".phone-tabbar a[href='/money']"); at("/money")          # the chosen slot: back to its top
    page.click("a[href='/money/accounts']"); at("/money/accounts")
    page.click(".phone-tabbar a[href='/plan']"); at("/plan")            # another slot: Money's pages are dropped
    page.go_back(); at("/")                                              # Back: Home, not Money's accounts
    page.click(".phone-tabbar a[href='/money']"); at("/money")
    page.click("a[href='/money/accounts']"); at("/money/accounts")
    page.go_back(); at("/money")                                         # Back walks the slot ...
    page.go_back(); at("/")                                              # ... then Home
    assert phone.same() and not phone.errors
