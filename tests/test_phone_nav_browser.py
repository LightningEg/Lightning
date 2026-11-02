"""The phone keeps its frame between pages (IT-3AO2, phone-nav.js): a tab, a link in the content or the month stepper
swaps only the app bar, the content and the tab bar, and what the new page needs still works. A page that brings its
own script loads whole, and back returns to the page before."""
from pathlib import Path
from types import SimpleNamespace
import shutil

import pytest

from lightning.runtime.app import SessionGate
from lightning.runtime.http import Guard, Host
from lightning.runtime.roles import SessionRole
from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app


@pytest.fixture
def phone(c):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    chromium = shutil.which("chromium") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None)
    if not chromium:
        pytest.skip("Chromium is not installed")
    load_mohab_2026(c)
    session = SimpleNamespace(container=c, paths=None, journal=None, borrowed=None, role=SessionRole.HOME,
                              token="test-phone-nav-session", csrf="test-phone-nav-csrf")
    app = create_app(c)

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

    # The stepper writes the month into its box at once; the page has arrived when the address carries it.
    arrived = "(m) => new URLSearchParams(location.search).get('month') === m && !document.querySelector('main[aria-busy]')"
    page.click(".phone-period [data-month-shift='-1']")
    earlier = page.locator(".phone-period [data-month-select]").input_value()
    page.wait_for_function(arrived, arg=earlier)
    page.click(".phone-period [data-month-shift='-1']")  # the stepper of the swapped page works too
    page.wait_for_function(arrived, arg=page.locator(".phone-period [data-month-select]").input_value())
    assert phone.same()

    page.go_back()
    page.wait_for_function("(m) => document.querySelector('.phone-period [data-month-select]')?.value === m", arg=earlier)
    assert phone.same()

    page.click(".phone-tabbar a[href='/transactions']")
    page.wait_for_function("() => location.pathname === '/transactions'")
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

    page.click(".phone-tabbar a[href='/more']")
    page.wait_for_function("() => location.pathname === '/more'")
    page.locator("main a[href='/plan']").first.click()
    page.wait_for_function("() => location.pathname === '/plan'")
    assert phone.same() and page.locator(".phone-tab.is-chosen").inner_text().strip() == "More"
    assert phone.errors == []


def _go(page, href):
    page.evaluate("(href) => { document.getElementById('go')?.remove(); const a = document.createElement('a');"
                  " a.href = href; a.id = 'go'; a.textContent = 'Go'; document.querySelector('main').prepend(a); }", href)
    page.click("#go")
    page.wait_for_function("(href) => location.pathname === href && document.readyState === 'complete'"
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
    _go(page, "/more")
    _go(page, "/plan/reserves")
    assert phone.same() and page.evaluate("window.__good") == 2
    listen["on"] = True
    _go(page, "/more")
    _go(page, "/plan/reserves")
    assert not phone.same()  # loaded whole
    assert phone.errors == []
