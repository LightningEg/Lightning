"""Live search on the phone keeps the newest results and address (BT-3AP): a body that arrives late never overwrites
newer results, clearing the field lands on the empty search, and a response for a page already left is dropped. The
real initializer runs in a real browser; only the network answer is held back so the order is controlled."""
from pathlib import Path
from types import SimpleNamespace
import shutil

import pytest

from lightning.runtime.app import SessionGate
from lightning.runtime.http import Guard, Host
from lightning.runtime.roles import SessionRole
from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app

# Replaces fetch for the live-search calls: each call waits until the test releases it with its own body.
HOLD = """
window.__held = {}; window.__calls = [];
const realFetch = window.fetch.bind(window);
window.fetch = (url, options) => {
  const u = new URL(url, location.href);
  if (u.pathname !== '/search' || !u.searchParams.has('fragment')) return realFetch(url, options);
  const q = u.searchParams.get('q');
  window.__calls.push(q);
  return new Promise((resolve, reject) => {
    window.__held[q] = (html) => resolve({ ok: true, text: () => Promise.resolve(html) });
    if (options && options.signal) options.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
  });
};
"""


@pytest.fixture
def search(c):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    chromium = shutil.which("chromium") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None)
    if not chromium:
        pytest.skip("Chromium is not installed")
    load_mohab_2026(c)
    session = SimpleNamespace(container=c, paths=None, journal=None, borrowed=None, role=SessionRole.HOME,
                              token="test-live-search-session", csrf="test-live-search-csrf")
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
                page.goto(host.origin + "/search")
                page.evaluate(HOLD)
                yield SimpleNamespace(page=page, origin=host.origin, errors=errors)
    finally:
        host.stop()


def _type(page, text):
    page.fill("form[data-live-search] input[name=q]", text)
    page.wait_for_function("(t) => window.__calls.includes(t)", arg=text.strip())


def _release(page, query, html):
    page.evaluate("([q, h]) => window.__held[q](h)", [query, html])
    page.wait_for_timeout(50)


def test_a_late_body_never_overwrites_newer_results_or_the_address(search):
    page = search.page
    results = page.locator("#search-results")
    _type(page, "old")
    _type(page, "new")
    _release(page, "new", "<p>NEW RESULTS</p>")
    assert results.inner_text().strip() == "NEW RESULTS"
    assert "q=new" in page.evaluate("location.search")
    _release(page, "old", "<p>OLD RESULTS</p>")      # the old request arrives last
    assert results.inner_text().strip() == "NEW RESULTS"
    assert "q=new" in page.evaluate("location.search")
    assert not search.errors


def test_clearing_the_field_lands_on_the_empty_search_not_the_last_word(search):
    page = search.page
    results = page.locator("#search-results")
    _type(page, "rent")
    _release(page, "rent", "<p>RENT</p>")
    page.fill("form[data-live-search] input[name=q]", "")
    page.wait_for_function("() => window.__calls.includes('')")
    page.evaluate("window.__held['']('<p>EVERYTHING</p>')")
    page.wait_for_timeout(50)
    assert results.inner_text().strip() == "EVERYTHING"
    assert "q=" not in page.evaluate("location.search")
    _release(page, "rent", "<p>RENT AGAIN</p>")       # a straggler for the word that was cleared
    assert results.inner_text().strip() == "EVERYTHING"


def test_an_answer_for_a_page_already_left_is_dropped(search):
    page = search.page
    _type(page, "late")
    before = page.evaluate("location.href")
    page.evaluate("document.querySelector('form[data-live-search]').remove()")   # the page was swapped out
    _release(page, "late", "<p>TOO LATE</p>")
    assert "TOO LATE" not in page.locator("#search-results").inner_text()
    assert page.evaluate("location.href") == before
    assert not search.errors
