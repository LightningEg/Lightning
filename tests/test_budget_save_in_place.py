"""BV-12AF: saving in the PC Budget keeps you where you are (owner, 2026-11-12: no reload on save).

A limit typed in Edit plan saves and its row's figures change without the page reloading, editing stays open and the
field keeps its row; Track and the bulk rules post in the background and come back still in Edit plan, with the
server's message."""
from types import SimpleNamespace

import pytest

from lightning.runtime.app import SessionGate
from lightning.runtime.http import Guard, Host
from lightning.runtime.roles import SessionRole
from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


@pytest.fixture
def budget_page(c):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    chromium = require_chromium()
    load_mohab_2026(c)
    session = SimpleNamespace(container=c, paths=None, journal=None, borrowed=None, role=SessionRole.HOME,
                              token="test-budget-session", csrf="test-budget-csrf")
    app = create_app(c)

    @app.get("/profiles/health")
    async def health():
        return {"locked": False, "session": session.token}

    host = Host(lambda cfg: Guard(SessionGate(app, session), cfg)).start()
    try:
        with sync_playwright() as p:
            with p.chromium.launch(executable_path=chromium, args=["--no-sandbox"]) as browser:
                page = browser.new_page(viewport={"width": 1400, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(host.launch_url)
                yield page, host, errors
    finally:
        host.stop()


def _open_edit_plan(page, host):
    page.goto(host.origin + "/budget?open_group=all#groups")
    page.evaluate("() => { window.__stayed = 1; document.querySelectorAll('#groups details').forEach(d => d.open = true); }")


def test_a_limit_saves_in_place_and_editing_stays_open(budget_page):
    from playwright.sync_api import expect
    page, host, errors = budget_page
    _open_edit_plan(page, host)
    form = page.locator("form[data-budget-rule]").first
    action = form.get_attribute("action")
    row = page.locator(f'form[action="{action}"]').locator("xpath=..")
    planned_before = row.locator("span.num").first.inner_text()
    field = form.locator("input[name=rule]")
    field.fill("1234")
    field.press("Enter")

    expect(page.locator(f'form[action="{action}"] .save-state')).to_have_text("Saved")
    assert page.locator(f'form[action="{action}"]').locator("xpath=..").locator("span.num").first.inner_text() == "1,234"
    assert planned_before != "1,234"
    assert page.evaluate("() => window.__stayed") == 1, "the page reloaded"
    assert page.locator("#groups details.budget-l1[open]").count() > 0, "the open groups closed"
    assert "Done" in page.locator("#groups .card-heading").inner_text(), "Edit plan ended"
    # The next field in the new rows is still wired: a second save also stays in place.
    second = page.locator("form[data-budget-rule]").nth(1)
    second.locator("input[name=rule]").fill("777")
    second.locator("input[name=rule]").press("Enter")
    expect(page.locator("form[data-budget-rule]").nth(1).locator(".save-state")).to_have_text("Saved")
    assert page.evaluate("() => window.__stayed") == 1
    assert errors == []


def test_track_and_bulk_rules_keep_edit_plan_open(budget_page):
    from playwright.sync_api import expect
    page, host, errors = budget_page
    _open_edit_plan(page, host)
    track = page.locator('form[action="/budget/suggestions"] button[value=track]').first
    if track.count():
        track.click()
        expect(page.locator("main > .flash").first).to_contain_text("Preference saved.")
        assert page.evaluate("() => window.__stayed") == 1, "Track reloaded the page"
        assert "Done" in page.locator("#groups .card-heading").inner_text()
        page.evaluate("() => document.querySelectorAll('#groups details').forEach(d => d.open = true)")

    bulk = page.locator("form.budget-bulk").first
    bulk_id = bulk.get_attribute("id")
    page.locator(f'[form="{bulk_id}"][name=category_id]').first.check()
    page.locator(f"#{bulk_id} button[value=average3]").click()
    page.locator("dialog.ask-dialog[open] [data-ask=yes]").click()
    expect(page.locator("main form.notice")).to_contain_text("Bulk rules applied.")
    assert page.evaluate("() => window.__stayed") == 1, "the bulk rule reloaded the page"
    assert "Done" in page.locator("#groups .card-heading").inner_text()
    assert errors == []
