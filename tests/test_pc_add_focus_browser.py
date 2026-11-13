"""IV-3BF4/5: PC Add starts with amount and shows Lightning's own validation well."""
from __future__ import annotations

from tests.test_pc_layout_browser import pc_page  # noqa: F401 - shared dummy profile fixture


def test_add_starts_on_amount_and_saves_once(pc_page):
    page, origin = pc_page
    page.goto(origin + "/accounts/1/transaction/new")
    amount = page.locator("#popup-amount")
    assert amount.evaluate("el => el === document.activeElement")
    assert page.locator("h1", has_text="Add transaction").count() == 1
    assert page.locator("h2", has_text="Add transaction").count() == 0
    assert not page.locator(".transaction-effect").is_visible()
    amount.fill("120")
    assert amount.input_value() == "120"
    page.locator("#popup-counterparty").fill("BF Test Merchant")
    page.locator("#popup-category").evaluate("""el => {
        const option = [...el.options].find(o => o.value && o.dataset.movement === 'OUTFLOW');
        el.value = option.value; el.dispatchEvent(new Event('change', {bubbles: true}));
    }""")
    page.locator("form[action='/accounts/1/transaction/new'] button[type=submit]").click()
    # BV-12AG: the form posts in the background, then opens the page the server names; wait for it before moving on.
    page.wait_for_url(lambda url: "/transaction/new" not in url)
    page.goto(origin + "/transactions")
    assert page.get_by_text("BF Test Merchant").count() == 1


def test_empty_amount_shows_branded_error_and_focus(pc_page):
    page, origin = pc_page
    page.goto(origin + "/accounts/1/transaction/new")
    page.locator("form[action='/accounts/1/transaction/new'] button[type=submit]").click()
    amount = page.locator("#popup-amount")
    assert amount.evaluate("el => el === document.activeElement && el.matches(':invalid')")
    well = page.locator("#popup-amount + .field-error")
    assert well.is_visible()
    assert well.inner_text() == "Enter an amount."
    assert amount.get_attribute("aria-describedby") == well.get_attribute("id")
