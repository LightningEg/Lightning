"""BT-7AG: selecting an institution updates Type once, while a later manual choice survives."""
from types import SimpleNamespace

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from lightning.runtime.app import SessionGate
from lightning.runtime.http import Guard, Host
from lightning.runtime.roles import SessionRole
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


@pytest.fixture(params=[1366, 390])
def account_page(c, request):
    chromium = require_chromium()
    session = SimpleNamespace(container=c, paths=None, journal=None, borrowed=None, role=SessionRole.HOME,
                              token="account-default-session", csrf="account-default-csrf")
    app = create_app(c)

    @app.get("/profiles/health")
    async def health():
        return {"locked": False, "session": session.token}

    host = Host(lambda cfg: Guard(SessionGate(app, session), cfg)).start()
    try:
        with sync_playwright() as pw:
            with pw.chromium.launch(executable_path=chromium, args=["--no-sandbox"]) as browser:
                page = browser.new_page(viewport={"width": request.param, "height": 900})
                page.set_default_timeout(5000)
                page.goto(host.launch_url)
                yield page, host.origin
    finally:
        host.stop()


def _type(page, value):
    # The shared picker decorates this select; exercise its real change listeners.
    page.locator("#account_type").evaluate("(el, value) => {el.value=value; el.dispatchEvent(new Event('change', {bubbles:true}));}", value)


def test_institution_switches_types_and_preserves_manual_override(c, account_page):
    page, origin = account_page
    page.goto(origin + "/accounts/new?type=DEPOSIT")
    assert page.locator("#account_type").input_value() == "DEPOSIT"
    assert page.locator("#opening-balance-section").is_hidden()
    institution = page.locator("#institution")
    institution.fill("  thndr  ")
    assert page.locator("#account_type").input_value() == "BROKERAGE"
    assert page.locator("#opening-balance-section").is_visible()
    institution.fill("cib")
    assert page.locator("#account_type").input_value() == "BANK"
    _type(page, "DEPOSIT")
    institution.dispatch_event("change")
    assert page.locator("#account_type").input_value() == "DEPOSIT"
    institution.fill("")
    institution.fill("CIB")
    assert page.locator("#account_type").input_value() == "BANK"
    _type(page, "GAMEYA")
    institution.fill(c.institutions.match("thndr").arabic_name)
    assert page.locator("#account_type").input_value() == "BROKERAGE"
    institution.fill("Example unknown institution")
    assert page.locator("#account_type").input_value() == "BROKERAGE"


def test_edit_hydration_keeps_saved_specialized_account_type(c, account_page):
    account = c.account_flows.open_account("Example portfolio", "DEPOSIT", "2026-09-01", "0", institution="CIB")
    page, origin = account_page
    page.goto(origin + f"/accounts/{account.id}/edit")
    assert page.locator("#account_type").input_value() == "DEPOSIT"
    page.locator("#institution").dispatch_event("change")
    assert page.locator("#account_type").input_value() == "DEPOSIT"
    page.locator("#institution").fill("thndr")
    assert page.locator("#account_type").input_value() == "BROKERAGE"


def test_larger_register_page_can_select_and_edit_one_hundred_entries(c, setup, account_page):
    account, food = setup[0]["cib"], setup[1]["EXP.PERSONAL.FOOD"]
    made = [c.transactions.record_outflow("2026-09-10", account.id, "1", food.id,
                                         counterparty="Example page merchant") for _ in range(115)]
    page, origin = account_page
    page.goto(origin + f"/accounts/{account.id}?q=Example+page+merchant")
    page.locator("#register-page-size").select_option("100")
    page.locator("form.register-page-size button").click()
    assert "page_size=100" in page.url and "q=Example" in page.url
    expect(page.locator(".transaction-select")).to_have_count(100)
    page.locator("#select-visible").check()
    assert page.locator(".transaction-select:checked").count() == 100
    assert page.locator("#selection-count").inner_text() == "100 selected"
    page.locator("#edit-selected").click()
    page.locator('[form="f-edit"][name="notes"]').fill("Example bulk edit")
    page.locator("#f-edit").evaluate("f => f.requestSubmit()")
    page.get_by_role("button", name="All 100 rows", exact=True).click()
    page.wait_for_selector("tr.editing", state="detached")
    assert sum(c.transactions.get(t.id).notes == "Example bulk edit" for t in made) == 100
    assert "page_size=100" in page.url
