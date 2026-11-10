"""PC Add starts on the amount and says its name once (IV-3BF4)."""
from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from tests.test_focus_browser import pc_page  # noqa: E402,F401  (the dummy profile with the sample household)


def _open(page, origin):
    page.set_viewport_size({"width": 1366, "height": 900})
    page.goto(origin + "/accounts/1/transaction/new")


def test_the_amount_has_focus_and_no_fake_zero(pc_page):
    page, origin = pc_page
    _open(page, origin)
    assert page.evaluate("document.activeElement.id") == "popup-amount"
    assert page.get_attribute("#popup-amount", "placeholder") is None
    page.keyboard.type("120")
    assert page.input_value("input[name=amount]") == "120"


def test_the_name_is_said_once_and_no_empty_well(pc_page):
    page, origin = pc_page
    _open(page, origin)
    headings = [h for h in page.locator("h1, h2").all() if h.is_visible() and "Add transaction" in h.inner_text()]
    assert len(headings) == 1
    assert not page.locator("[data-transaction-effect]").is_visible()


def test_saving_creates_one_transaction_of_120(pc_page):
    page, origin = pc_page
    page.goto(origin + "/transactions")
    before = page.inner_text("body").count("120.00")
    _open(page, origin)
    page.keyboard.type("120")
    page.locator("label.transaction-choice", has_text="Money out").click()
    page.evaluate("""() => { const s = document.querySelector('#popup-category'); s.value = [...s.options].find(o => o.value).value;
      s.dispatchEvent(new Event('change', {bubbles: true})); }""")
    page.locator("form button.primary", has_text="Add transaction").click()
    page.wait_for_load_state()
    page.goto(origin + "/transactions")
    assert page.inner_text("body").count("120.00") == before + 1
