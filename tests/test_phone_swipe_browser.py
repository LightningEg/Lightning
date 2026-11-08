"""3AD3: on the phone, swiping a transaction row toward the start reveals Set category and Delete behind it; Set
category opens the row's category sheet, a tap elsewhere closes them, and Arabic mirrors the side. Swiping toward
the end still opens the row; nothing here changes tabs (C03.3) or takes press-and-hold (C08.5)."""
from __future__ import annotations

import pytest

from tests.test_phone_sheets_browser import _signed_in_page, _wait, playwright_chromium  # noqa: F401

SWIPE = """([selector, dx]) => {
  const row = document.querySelector(selector);
  const box = row.getBoundingClientRect();
  const x = box.left + box.width / 2, y = box.top + box.height / 2;
  const touch = (cx) => new Touch({identifier: 1, target: row, clientX: cx, clientY: y});
  row.dispatchEvent(new TouchEvent('touchstart', {bubbles: true, touches: [touch(x)], changedTouches: [touch(x)]}));
  for (const step of [12, dx / 2, dx]) {
    row.dispatchEvent(new TouchEvent('touchmove', {bubbles: true, touches: [touch(x + step)], changedTouches: [touch(x + step)]}));
  }
  row.dispatchEvent(new TouchEvent('touchend', {bubbles: true, touches: [], changedTouches: [touch(x + dx)]}));
}"""
ROW = "a.phone-txn[data-cat]"


@pytest.fixture(scope="module")
def phone_page(playwright_chromium, tmp_path_factory):  # noqa: F811
    yield from _signed_in_page(playwright_chromium, tmp_path_factory.mktemp("phone-swipe"), True)


def _actions(page):
    return page.evaluate("""() => [...document.querySelectorAll('.phone-swipe-actions > *')].map((el) => {
      const r = el.getBoundingClientRect();
      return {text: el.textContent, left: r.left, right: r.right, height: r.height, width: r.width}; })""")


def test_swiping_toward_the_start_reveals_set_category_and_delete(phone_page):
    page, origin = phone_page
    page.goto(origin + "/transactions?period=all")  # the register behind a filter: the bare URL is Activity now
    page.wait_for_selector(ROW)
    count = page.locator("a.phone-txn[data-txn]").count()
    page.evaluate(SWIPE, [ROW, -120])
    page.wait_for_timeout(300)  # the row's slide (0.18 s)
    actions = _actions(page)
    assert [a["text"] for a in actions] == ["Set category", "Delete"]
    assert all(a["height"] >= 48 and a["width"] >= 48 for a in actions)
    assert actions[-1]["right"] <= 390 + 1  # on screen, at the end of the row
    row = page.evaluate(f"() => document.querySelector('{ROW}').getBoundingClientRect().right")
    assert row <= actions[0]["left"] + 1  # the row slid aside: nothing overlaps
    assert page.locator("a.phone-txn[data-txn]").count() == count  # nothing deleted by the swipe itself
    assert page.evaluate("() => location.pathname") == "/transactions"  # no tab change (C03.3)

    page.evaluate("() => document.querySelector('.phone-swipe-actions .phone-swipe-cat').click()")
    page.wait_for_selector("dialog[open] .phone-cat-chips")
    assert page.locator(".phone-swipe-actions").count() == 0


def test_a_tap_elsewhere_closes_the_actions_and_arabic_mirrors_them(phone_page):
    page, origin = phone_page
    page.goto(origin + "/transactions?period=all")  # the register behind a filter: the bare URL is Activity now
    page.wait_for_selector(ROW)
    page.evaluate(SWIPE, [ROW, -120])
    assert page.locator(".phone-swipe-actions").count() == 1
    page.evaluate("() => document.querySelector('h1, .phone-title, main').click()")
    _wait(page, "() => !document.querySelector('.phone-swipe-actions')")
    assert page.evaluate(f"() => document.querySelector('{ROW}').style.transform") == ""

    page.evaluate("""async () => { const t = document.querySelector('meta[name=lightning-session]').content;
      await fetch('/settings/locale', {method: 'POST', body: new URLSearchParams({__session: t, locale: 'ar'})}); }""")
    page.goto(origin + "/transactions?period=all")  # the register behind a filter: the bare URL is Activity now
    page.wait_for_selector(ROW)
    page.evaluate(SWIPE, [ROW, 120])  # in Arabic the start is the right-hand side
    actions = _actions(page)
    assert len(actions) == 2 and actions[0]["text"] != "Set category"  # translated
    assert min(a["left"] for a in actions) >= -1  # at the row's end, the left edge
    page.evaluate("""async () => { const t = document.querySelector('meta[name=lightning-session]').content;
      await fetch('/settings/locale', {method: 'POST', body: new URLSearchParams({__session: t, locale: 'en'})}); }""")
