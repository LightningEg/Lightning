"""Delete remains an explicit action in both languages, including local form handlers."""
from types import SimpleNamespace

import pytest

from lightning.runtime.app import SessionGate
from lightning.runtime.http import Guard, Host
from lightning.runtime.roles import SessionRole
from lightning.samples import load_mohab_2026
from lightning.ui.i18n import translate
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


@pytest.fixture
def delete_page(c):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    chromium = require_chromium()
    load_mohab_2026(c)
    session = SimpleNamespace(container=c, paths=None, journal=None, borrowed=None, role=SessionRole.HOME,
                              token="test-delete-session", csrf="test-delete-csrf")
    app = create_app(c)

    @app.get("/profiles/health")
    async def health():
        return {"locked": False, "session": session.token}

    host = Host(lambda cfg: Guard(SessionGate(app, session), cfg)).start()
    try:
        with sync_playwright() as p:
            with p.chromium.launch(executable_path=chromium, args=["--no-sandbox"]) as browser:
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(host.launch_url)
                yield page, host
    finally:
        host.stop()


@pytest.mark.parametrize("locale", ["en", "ar"])
def test_category_delete_enter_cancels_and_click_confirms(delete_page, c, locale):
    from playwright.sync_api import expect
    page, host = delete_page
    c.settings.set("locale", locale)
    page.goto(host.origin + "/categories")
    button = page.locator("button[data-confirm-delete]").first
    form = button.locator("xpath=ancestor::form")
    action = form.get_attribute("action")
    posts = []
    page.on("request", lambda request: posts.append(request.url)
            if request.method == "POST" and request.url == host.origin + action else None)

    button.click()
    dialog = page.locator("dialog.ask-dialog[open]")
    expect(dialog).to_have_class("ask-dialog tone-danger")
    expect(dialog.locator('[data-ask="yes"]')).to_have_class("btn is-danger")
    expect(dialog.locator('[data-ask="yes"]')).to_have_text(translate("Delete", locale))
    expect(dialog.locator('[data-ask="no"]')).to_be_focused()
    expect(dialog.locator("h2")).to_have_text(
        translate("Delete this category?", locale))
    expect(dialog.locator("p")).not_to_be_empty()
    page.keyboard.press("Enter")
    expect(dialog).to_have_count(0)
    expect(button).to_be_visible()
    assert posts == []

    button.click()
    with page.expect_request(lambda request: request.method == "POST" and request.url == host.origin + action):
        dialog.locator('[data-ask="yes"]').click()
    page.wait_for_load_state("networkidle")
    assert posts.count(host.origin + action) == 1
    expect(page.locator("dialog.ask-dialog[open]")).to_have_count(0)


@pytest.mark.parametrize("locale", ["en", "ar"])
@pytest.mark.parametrize("source", ["delegated", "counterparty", "category-edit"])
def test_delete_marker_does_not_depend_on_wording(delete_page, c, locale, source):
    from playwright.sync_api import expect
    page, host = delete_page
    c.settings.set("locale", locale)
    page.goto(host.origin + "/categories")
    if source == "delegated":
        # A delete marker stays authoritative even without a deletion verb.
        page.evaluate("""() => {
          const form = document.createElement('form');
          form.dataset.confirmDelete = 'Continue? This changes your data.';
          form.innerHTML = '<button id="marked-delete">Continue</button>';
          document.body.append(form);
        }""")
        button = page.locator("#marked-delete")
    elif source == "counterparty":
        page.goto(host.origin + "/counterparties")
        page.locator("details.cp-row > summary").first.click()
        button = page.locator("[data-counterparty-delete] button").first
    else:
        action = page.locator("button[data-confirm-delete]").first.locator("xpath=ancestor::form").get_attribute("action")
        page.goto(host.origin + action.removesuffix("/row") + "/edit")
        button = page.locator("[data-confirm-delete] button")
    button.click()
    dialog = page.locator("dialog.ask-dialog[open]")
    expect(dialog).to_have_class("ask-dialog tone-danger")
    expect(dialog.locator('[data-ask="yes"]')).to_have_text(translate("Delete", locale))
    expect(dialog.locator('[data-ask="no"]')).to_be_focused()
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
