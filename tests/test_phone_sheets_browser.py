"""The phone's sheets in a real browser (3R): a sheet holds only its form, Save says what is missing, a learned
category is filled in, the raise offer is a page card that stays, and the tab bar steps aside for the keyboard."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
CHROMIUM = Path("/opt/pw-browsers/chromium")
if not CHROMIUM.exists():
    CHROMIUM = Path(shutil.which("chromium") or str(CHROMIUM))

TOKEN = "() => document.querySelector('meta[name=lightning-session]').content"
OPEN_SHEET = """(url) => { const a = document.createElement('a'); a.href = url; a.setAttribute('data-popup-open', '');
  document.body.append(a); a.click(); a.remove(); }"""


@pytest.fixture(scope="module")
def playwright_chromium():
    if not CHROMIUM.exists():
        pytest.skip("Chromium is not installed")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        yield p.chromium


def _signed_in_page(chromium, root, phone):
    """A browser page on a dummy profile with the sample household: the phone frame (phone) or the PC one."""
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Host

    host = Host(lambda c: profile_app(c, root / "docs", devices=Devices(root / "app", port=0), phone=phone)).start()
    try:
        browser = chromium.launch(executable_path=str(CHROMIUM), args=["--no-sandbox"])
        options = dict(viewport={"width": 390, "height": 800}, is_mobile=True, has_touch=True) if phone \
            else dict(viewport={"width": 1366, "height": 800})
        page = browser.new_page(**options)
        page.goto(host.launch_url)
        page.goto(host.origin + "/profiles/new")
        page.fill("input[name=name]", "Sheets")
        page.fill("input[name=password]", "a dummy phone password")
        page.fill("input[name=confirm]", "a dummy phone password")
        page.fill("input[name=answer]", "Dummy")
        if page.locator("select[name=question]").count():
            page.select_option("select[name=question]", index=1)
        elif page.locator("input[name=question]").count():
            page.fill("input[name=question]", "Dummy question?")
        page.click("button[type=submit]")
        recovery = re.search(r"\d{4}-\d{4}-\d{4}", page.content()).group(0)
        if page.locator("form[action='/profiles/confirm'] input[name=recovery][type=text]").count():
            page.fill("input[name=recovery]", recovery)
        page.click("form[action='/profiles/confirm'] button[type=submit]")
        page.goto(host.origin + "/")
        page.evaluate("""async () => {
          const token = document.querySelector('meta[name=lightning-session]').content;
          await fetch('/demo', {method: 'POST', body: new URLSearchParams({__session: token})});
        }""")
        yield page, host.origin
        browser.close()
    finally:
        host.stop()


@pytest.fixture(scope="module")
def phone_page(playwright_chromium, tmp_path_factory):
    yield from _signed_in_page(playwright_chromium, tmp_path_factory.mktemp("phone-sheets"), True)


@pytest.fixture(scope="module")
def pc_page(playwright_chromium, tmp_path_factory):
    yield from _signed_in_page(playwright_chromium, tmp_path_factory.mktemp("pc-sheets"), False)


def _wait(page, expression, seconds=3):
    """Poll a page expression (wait_for_function evaluates a string, which the page's CSP refuses)."""
    for _ in range(int(seconds * 20)):
        if page.evaluate(expression):
            return
        page.wait_for_timeout(50)
    raise AssertionError(f"still false after {seconds} s: {expression}")


def _open_entry_sheet(page, origin):
    page.goto(origin + "/accounts/1")
    page.evaluate(OPEN_SHEET, "/accounts/1/transaction/new")
    page.wait_for_selector("dialog[open] input[name=amount]")


def test_a_sheet_holds_only_its_form_and_hides_the_tab_bar(phone_page):
    page, origin = phone_page
    _open_entry_sheet(page, origin)
    assert page.locator("dialog .phone-page-actions, dialog .section-bar, dialog .history-form").count() == 0
    assert "sheet-open" in page.evaluate("document.documentElement.className")
    assert page.evaluate("getComputedStyle(document.querySelector('.phone-tabbar')).display") == "none"
    page.evaluate("document.querySelector('[data-popup-close]').click()")
    page.wait_for_selector("dialog[open]", state="detached")
    assert "sheet-open" not in page.evaluate("document.documentElement.className")
    assert page.evaluate("getComputedStyle(document.querySelector('.phone-tabbar')).display") != "none"


def test_save_without_a_category_says_what_is_missing(phone_page):
    page, origin = phone_page
    _open_entry_sheet(page, origin)
    page.fill("dialog input[name=amount]", "12")
    select = page.locator("dialog select[name=category_id]")
    assert select.evaluate("el => el.required") is False  # the hidden select cannot show a message
    page.click("dialog button.phone-save")
    assert page.locator("dialog[open]").count() == 1  # not saved
    focused = page.evaluate("""() => ({tag: document.activeElement.tagName, role: document.activeElement.getAttribute('role'),
        message: document.activeElement.validationMessage})""")
    assert (focused["tag"], focused["role"]) == ("INPUT", "combobox")  # the visible category field
    assert focused["message"] == "Choose an option from the list."
    page.check("dialog input[name=kind][value=transfer]", force=True)  # a transfer needs no category
    assert select.evaluate("el => el.disabled")
    assert page.locator("dialog .counterparty-picker:has(select[name=category_id]) input[role=combobox]").evaluate(
        "el => !el.required")


def test_a_counterparty_with_a_learned_category_fills_it_in(phone_page):
    page, origin = phone_page
    _open_entry_sheet(page, origin)
    category = page.evaluate("""() => document.querySelector('dialog [name=category_id] option[data-movement=OUTFLOW]').value""")
    name = page.evaluate("""async ([category]) => {
      const token = document.querySelector('meta[name=lightning-session]').content;
      await fetch('/counterparties', {method: 'POST', body: new URLSearchParams({__session: token,
        counterparty_action: 'create', name: 'Corner Kiosk', default_category_id: category})});
      return 'Corner Kiosk'; }""", [category])
    page.evaluate("document.querySelector('[data-popup-close]').click()")
    page.wait_for_selector("dialog[open]", state="detached")
    _open_entry_sheet(page, origin)
    assert page.locator("dialog [name=category_id]").evaluate("el => el.value") == ""
    page.fill("dialog input[name=counterparty]", name)
    page.locator("dialog .counterparty-option", has_text=name).first.click()
    assert page.locator("dialog [name=category_id]").evaluate("el => el.value") == category
    page.fill("dialog input[name=amount]", "31.50")
    page.click("dialog button.phone-save")
    page.wait_for_selector("dialog[open]", state="detached")
    page.get_by_text("Corner Kiosk").first.wait_for()  # the saved row is on the page


def test_the_keyboard_hides_the_tab_bar(phone_page):
    page, origin = phone_page
    page.goto(origin + "/search")
    page.locator("main input[type=search], main input[type=text]").first.focus()
    page.set_viewport_size({"width": 390, "height": 450})  # what the keyboard does to the viewport
    _wait(page, "document.documentElement.classList.contains('keyboard-open')")
    assert page.evaluate("getComputedStyle(document.querySelector('.phone-tabbar')).display") == "none"
    page.evaluate("document.activeElement.blur()")
    page.set_viewport_size({"width": 390, "height": 800})
    _wait(page, "!document.documentElement.classList.contains('keyboard-open')")
    assert page.evaluate("getComputedStyle(document.querySelector('.phone-tabbar')).display") != "none"


def test_the_raise_offer_is_a_page_card_that_stays(phone_page):
    page, origin = phone_page
    page.goto(origin + "/budget")
    page.evaluate("""async () => {
      const token = document.querySelector('meta[name=lightning-session]').content;
      const form = new DOMParser().parseFromString(await (await fetch('/plan/items/new')).text(), 'text/html');
      const account = form.querySelector('[name=account_id]').value;
      const category = [...form.querySelectorAll('[name=category_id] option')].find((o) => o.value).value;
      await fetch('/plan/items', {method: 'POST', body: new URLSearchParams({__session: token, kind: 'INCOME',
        name: 'Salary', amount: '60000', frequency: 'MONTHLY', interval_count: '1', start_date: '2026-11-01',
        account_id: account, category_id: category, past_due: 'later'})}); }""")
    page.goto(origin + "/budget")
    card = page.locator("section.raise-prompt")
    assert card.count() == 1 and page.locator(".flash.raise-prompt").count() == 0
    assert card.evaluate("el => getComputedStyle(el).position") != "fixed"
    top = page.locator(".phone-appbar").bounding_box()
    assert card.bounding_box()["y"] >= top["y"] + top["height"]  # below the top bar, never over it
    page.wait_for_timeout(5500)  # past the 5 second timer that removes plain messages
    assert card.locator("a.btn.primary").is_visible() and card.locator("a.phone-quiet").is_visible()


def test_the_pc_popup_says_what_is_missing_and_fills_a_learned_category(pc_page):
    page, origin = pc_page
    _open_entry_sheet(page, origin)
    assert page.locator("dialog .section-bar, dialog .history-form").count() == 0
    page.fill("dialog input[name=amount]", "12")
    page.click("dialog button[type=submit]")
    assert page.locator("dialog[open]").count() == 1
    focused = page.evaluate("() => [document.activeElement.tagName, document.activeElement.validationMessage]")
    assert focused == ["INPUT", "Choose an option from the list."]
    category = page.evaluate("document.querySelector('dialog [name=category_id] option[data-movement=OUTFLOW]').value")
    page.evaluate("""async (category) => {
      const token = document.querySelector('meta[name=lightning-session]').content;
      await fetch('/counterparties', {method: 'POST', body: new URLSearchParams({__session: token,
        counterparty_action: 'create', name: 'Corner Kiosk', default_category_id: category})}); }""", category)
    _open_entry_sheet(page, origin)
    page.fill("dialog input[name=counterparty]", "Corner Kiosk")
    page.locator("dialog .counterparty-option", has_text="Corner Kiosk").first.click()
    assert page.locator("dialog [name=category_id]").evaluate("el => el.value") == category
    page.fill("dialog input[name=amount]", "31.50")
    page.click("dialog button[type=submit]")
    page.wait_for_selector("dialog[open]", state="detached")
    page.get_by_text("Corner Kiosk").first.wait_for()  # the saved row is on the page
