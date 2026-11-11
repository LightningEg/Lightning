"""One page skeleton on the PC (IV-12Y2) and the answer on one screen (IV-12Z1), kept by a test.

Every tab in `sections.SECTIONS` is opened on the sample household at 1366 x 768 and measured:

- one H1, equal to the tab's own name (owner, 2026-11-10: the sidebar already names the section); a section's first
  tab is the section's front page and may carry the section's name (Overview, Cash planning, Investments);
- an answer sentence (`.page-status`) of at most 16 words that does not repeat the title (A05, A09);
- Undo, when shown, in the header row (`.topbar`), never on a second row inside the page;
- at most one filled (primary) button on the first screen;
- at most 2.5 screens tall as it first opens, registers excepted (IV-12Z: the rest opens on request).

Today's failures are listed in ALLOWED, each with the item that fixes it. A step that fixes a tab removes its name
from the list; `test_the_allow_list_is_not_stale` fails when a listed tab already passes, so the list only shrinks.
"""
from __future__ import annotations

import re

import pytest
from tests.browser_support import chromium_executable, require_chromium

pytest.importorskip("playwright.sync_api")
CHROMIUM = chromium_executable()

MAX_WORDS = 16
MAX_SCREENS = 2.5
REGISTERS = {"transactions", "categories"}  # long lists by nature (IV-12Z1)

# (rule, tab key) -> the item that fixes it. Remove an entry in the commit that fixes it.
ALLOWED: dict[tuple[str, str], str] = {
    ("length", "holdings"): "IV-12Z4",
}

MEASURE = """() => {
  const top = document.querySelector('.topbar');
  const main = document.querySelector('.main');
  const h1s = [...document.querySelectorAll('h1')].filter(h => h.offsetParent !== null);
  const status = top && top.querySelector('.page-status, .page-line');
  const undoTop = !!(top && top.querySelector('[data-history]'));
  const undoAll = document.querySelectorAll('.main [data-history]').length;
  const primaries = [...document.querySelectorAll('.main .btn.primary, .main button.primary, .topbar .btn.primary, .topbar button.primary')]
    .filter(b => { const r = b.getBoundingClientRect(); return r.width && r.height && r.top < innerHeight && getComputedStyle(b).visibility !== 'hidden'; })
    .map(b => b.textContent.trim());
  return {
    h1: h1s.map(h => h.textContent.trim()),
    status: status ? status.textContent.trim() : '',
    undoTop, undoAll,
    primaries,
    screens: document.documentElement.scrollHeight / innerHeight,
  };
}"""


def _tabs():
    """(key, accepted titles, href) for every tab."""
    from lightning.ui.sections import SECTIONS
    return [(tab.key, (tab.label, section.label) if i == 0 else (tab.label,), tab.href)
            for section in SECTIONS for i, tab in enumerate(section.tabs)]


@pytest.fixture(scope="module")
def measured(tmp_path_factory):
    """Each tab of the sample household, measured as it first opens at 1366 x 768."""
    require_chromium()
    from playwright.sync_api import sync_playwright
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Host

    root = tmp_path_factory.mktemp("skeleton")
    host = Host(lambda c: profile_app(c, root / "docs", devices=Devices(root / "app", port=0))).start()
    out = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(CHROMIUM), args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            page.goto(host.launch_url)
            page.goto(host.origin + "/profiles/new")
            page.fill("input[name=name]", "Skeleton")
            page.fill("input[name=password]", "a dummy skeleton password")
            page.fill("input[name=confirm]", "a dummy skeleton password")
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
            from lightning.ui.sections import locate
            for key, titles, url in _tabs():
                response = page.goto(host.origin + url)
                assert response is not None and response.status < 400, f"{url}: HTTP {response and response.status}"
                landed = locate(page.evaluate("location.pathname"))[1]
                if landed is None or landed.key != key:
                    continue  # a tab switched off in the sample (Zakat until it is turned on)
                page.mouse.move(1, 1)
                page.evaluate("async () => { await document.fonts.ready; }")
                out[key] = {"titles": titles, **page.evaluate(MEASURE)}
                out[key]["both_ways"] = page.locator(".kpi-card:has(.fig-open) .kc-open").count()
            page.goto(host.origin + "/plan")  # NF-12AB3: the figure opens its working in place; Escape closes it
            figure = page.locator(".lead-card .fig-open").first
            panel = page.locator("#" + figure.get_attribute("aria-controls"))
            opened = [panel.is_visible()]
            figure.click()
            opened.append(panel.is_visible())
            page.keyboard.press("Escape")
            opened.append(panel.is_visible())
            figure.focus()
            page.keyboard.press("Enter")
            opened.append(panel.is_visible())
            out["_working"] = opened
            browser.close()
    finally:
        host.stop()
    return out


def _failures(measured) -> dict[tuple[str, str], str]:
    found = {}
    for key, m in measured.items():
        if key.startswith("_"):
            continue
        if m.get("both_ways"):
            found[("working", key)] = "a KPI both opens its working and links away"
        if len(m["h1"]) != 1 or m["h1"][0] not in m["titles"]:
            found[("title", key)] = f"H1 {m['h1']} is not the tab's name {m['titles'][0]!r}"
        words = len(m["status"].split())
        if not words:
            found[("sentence", key)] = "no answer sentence"
        elif not m["status"].endswith((".", "?")):
            found[("sentence", key)] = f"a label, not a sentence: {m['status']!r}"
        elif words > MAX_WORDS or m["status"].rstrip(".").casefold() in {x.casefold() for x in m["titles"]}:
            found[("sentence", key)] = f"sentence of {words} words: {m['status']!r}"
        if m["undoAll"] and not m["undoTop"]:
            found[("undo", key)] = "Undo sits inside the page, not in the header row"
        if len(m["primaries"]) > 1:
            found[("primary", key)] = f"{len(m['primaries'])} filled buttons: {m['primaries']}"
        if key not in REGISTERS and m["screens"] > MAX_SCREENS:
            found[("length", key)] = f"{m['screens']:.1f} screens"
    return found


def test_every_tab_follows_the_skeleton(measured):
    unexpected = {k: v for k, v in _failures(measured).items() if k not in ALLOWED}
    assert not unexpected, "\n".join(f"{rule} · {key}: {why}" for (rule, key), why in sorted(unexpected.items()))


def test_the_allow_list_is_not_stale(measured):
    fixed = sorted(k for k in ALLOWED if k not in _failures(measured))
    assert not fixed, f"these pass now; remove them from ALLOWED: {fixed}"


def test_the_allow_list_names_real_tabs_and_items():
    keys = {key for key, _, _ in _tabs()}
    for (rule, key), item in ALLOWED.items():
        assert rule in {"title", "sentence", "undo", "primary", "length", "working"}, rule
        assert key in keys, key
        assert re.fullmatch(r"(IV|BV|IT|BT|NF)-\d+[A-Z]+\d*", item), item


def test_a_headline_figure_opens_its_working_in_place(measured):
    """NF-12AB3 (A08.1): closed, then open on a click, closed by Escape, open again with Enter."""
    assert measured["_working"] == [False, True, False, True]
