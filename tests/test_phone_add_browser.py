"""J1 on the phone (IV-3AY7): from Home, a payment is saved in three taps (Add, a category chip, Save) with the amount
typed, and the person is back on Home. A real browser, the real sheet and script."""
from types import SimpleNamespace

import pytest

from lightning.runtime.app import SessionGate
from lightning.runtime.http import Guard, Host
from lightning.runtime.roles import SessionRole
from lightning.samples import load_mohab_2026
from lightning.ui.phone.router import mount_phone
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


@pytest.fixture
def phone(c):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    chromium = require_chromium()
    load_mohab_2026(c)
    session = SimpleNamespace(container=c, paths=None, journal=None, borrowed=None, role=SessionRole.HOME,
                              token="test-add-session", csrf="test-add-csrf")
    app = create_app(c)
    mount_phone(app)

    @app.get("/profiles/health")
    async def health():
        return {"locked": False, "session": session.token}

    gate = SessionGate(app, session)
    gate.phone = True
    host = Host(lambda cfg: Guard(gate, cfg)).start()
    try:
        with sync_playwright() as p:
            with p.chromium.launch(executable_path=chromium, args=["--no-sandbox"]) as browser:
                page = browser.new_page(viewport={"width": 320, "height": 640}, is_mobile=True, has_touch=True)
                page.goto(host.launch_url)
                yield page, host
    finally:
        host.stop()


def test_a_payment_takes_three_taps_from_home(phone, c):
    page, host = phone
    before = c.db.scalar("SELECT COUNT(*) FROM transactions")
    page.goto(host.origin + "/home")
    taps = 0
    page.locator("a.phone-add").tap(); taps += 1
    page.wait_for_selector("#popup-amount")
    page.fill("#popup-amount", "42")
    page.locator("[data-category-chips] .phone-chip[data-category]:visible").first.tap(); taps += 1
    page.locator(".phone-save-bar .phone-save").tap(); taps += 1
    page.wait_for_url("**/home*")
    page.wait_for_selector(".phone-flash")
    assert taps == 3 and c.db.scalar("SELECT COUNT(*) FROM transactions") == before + 1


def _enable_dictation_stub(page):
    page.evaluate("""() => {
        window.lightningVoiceAvailable = true;
        window.dispatchEvent(new Event("voiceavailable"));
        document.addEventListener("click", e => {
            const mic = e.target.closest("[data-voice-mic]");
            if (!mic) return;
            e.preventDefault();
            const id = new URL(mic.href).searchParams.get("id");
            window.lightningVoiceResult(id, window.testPhrase);
        });
    }""")


def test_mohab_dictates_cash_then_confirms_the_amount(phone, c):
    page, host = phone
    before = c.db.scalar("SELECT COUNT(*) FROM transactions")
    page.goto(host.origin + "/home")
    page.locator("a.phone-add").tap()
    page.wait_for_selector("#popup-amount")
    _enable_dictation_stub(page)
    category_id = page.locator("[data-category-chips] [data-category]:visible").first.get_attribute("data-category")
    category = page.locator(f'#popup-category option[value="{category_id}"]').text_content().strip()
    page.evaluate("label => window.testPhrase = label + ' yesterday'", category)
    page.locator("[data-voice-mic]").tap()
    assert page.locator("[data-voice-status]").inner_text() == "How much did you spend?"
    day = page.locator("#popup-date").input_value()
    chosen = page.locator("#popup-category").input_value()
    assert chosen
    page.evaluate("window.testPhrase = '50 dollars'")
    page.locator("[data-voice-mic]").tap()
    assert "How many Egyptian pounds" in page.locator("[data-voice-status]").inner_text()
    assert page.locator("#popup-amount").input_value() == ""
    page.evaluate("window.testPhrase = 'ميه وخمسين'")
    page.locator("[data-voice-mic]").tap()
    assert page.locator("#popup-amount").input_value() == "150"
    assert page.locator("#popup-category").input_value() == chosen
    assert page.locator("#popup-date").input_value() == day
    assert c.db.scalar("SELECT COUNT(*) FROM transactions") == before
    page.fill("#popup-amount", "149")
    page.locator(".phone-save-bar .phone-save").tap()
    page.wait_for_url("**/home*")
    page.wait_for_selector(".phone-flash")
    assert c.db.scalar("SELECT COUNT(*) FROM transactions") == before + 1

def test_category_choices_survive_an_amount_follow_up(phone):
    page, host = phone
    page.goto(host.origin + "/home")
    page.locator("a.phone-add").tap()
    page.wait_for_selector("#popup-amount")
    _enable_dictation_stub(page)
    names = page.locator("[data-category-chips] [data-category]:visible").all_text_contents()
    first, second = [name.strip() for name in names[:2]]
    page.evaluate("text => window.testPhrase = text", f"{first} or {second} yesterday")
    page.locator("[data-voice-mic]").tap()
    assert page.locator("[data-voice-status]").inner_text() == "How much did you spend?"
    assert page.locator("[data-voice-choices] button").count() == 0
    page.evaluate("window.testPhrase = 'eighty'")
    page.locator("[data-voice-mic]").tap()
    assert page.locator("[data-voice-status]").inner_text() == "Which category fits this expense?"
    page.locator("[data-voice-choices]").get_by_role("button", name=second, exact=True).tap()
    assert page.locator("#popup-category option:checked").text_content().strip() == second
    assert page.locator("#popup-amount").input_value() == "80"
