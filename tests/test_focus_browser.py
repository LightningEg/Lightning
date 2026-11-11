"""IV-3BF1: keyboard focus stays visible in normal and forced-colour Windows themes."""
from __future__ import annotations

from tests.test_pc_layout_browser import pc_page  # noqa: F401 - shared dummy profile fixture


def test_pc_keyboard_focus_is_visible(pc_page):
    page, origin = pc_page
    for route in ("/", "/transactions"):
        page.goto(origin + route)
        for forced in (False, True):
            page.emulate_media(forced_colors="active" if forced else "none")
            page.locator("body").focus()
            for _ in range(8):
                page.keyboard.press("Tab")
                visible = page.evaluate("""() => {
                    const el = document.activeElement;
                    const css = getComputedStyle(el);
                    return el !== document.body && (css.boxShadow !== 'none' ||
                        (css.outlineStyle !== 'none' && css.outlineWidth !== '0px'));
                }""")
                assert visible, (route, forced, page.evaluate("document.activeElement.outerHTML"))
                if forced:
                    assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") != "none"
