"""Brand audit in a real browser (guideline A03, A05, A10.3, A16): on the main PC pages, with the Mohab sample at
1366 × 768 px, nothing is upper-case, text is only in A03 colours, plain links are Ink and underlined, H1 to H3 are Ink,
no field is white or boxed, money out in the register is rose and never a positive figure, and the register fits its card.
Skipped when Playwright or Chromium is missing (CI has neither), so it runs by hand:
`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python -m pytest tests/test_brand_audit.py -q`."""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("playwright")
CHROMIUM = Path("/opt/pw-browsers/chromium")
if not CHROMIUM.exists():
    CHROMIUM = Path(shutil.which("chromium") or str(CHROMIUM))

PAGES = ("/plan/purchases/new", "/exports/all", "/setup/salary", "/", "/transactions", "/accounts", "/accounts/1", "/accounts/currencies", "/settings", "/investments",
         "/investments/prices", "/budget", "/plan", "/birdview/expenses", "/financial-health", "/categories",
         "/profiles")
# A03: Ink, Ink 2, Muted, Meadow text, Azure, Strong rose, Nile, and white on Nile or on the vivid gradient.
TEXT = ["#0D2233", "#304A5C", "#566E7E", "#097852", "#0B6DD6", "#C93D72", "#0A2442", "#FFFFFF"]

COLLECT = """() => {
  const TEXT = %TEXT%;
  const hex = c => { const m = c.match(/[\\d.]+/g); if (!m) return null; if (m.length > 3 && +m[3] === 0) return null;
    return '#' + m.slice(0, 3).map(x => (+x).toString(16).padStart(2, '0')).join('').toUpperCase(); };
  const out = {upper: [], colors: [], links: [], heads: [], fields: [], rose: [], overflow: [], jump: [], kpi: []};
  const name = el => el.tagName + '.' + String(el.className && el.className.baseVal === undefined ? el.className : '').trim().split(/\\s+/).slice(0, 2).join('.');
  for (const el of document.querySelectorAll('body *')) {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    if (!r.width || !r.height || s.visibility === 'hidden' || s.display === 'none' || el.closest('[hidden],[inert]')) continue;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    const text = el.textContent.trim().slice(0, 28);
    if (own && s.textTransform === 'uppercase') out.upper.push(name(el) + ' ' + text);
    if (own && !['OPTION', 'SCRIPT', 'STYLE'].includes(el.tagName)) {
      const k = hex(s.color); if (k && !TEXT.includes(k)) out.colors.push(name(el) + ' ' + k + ' ' + text);
      if (k === '#C93D72') out.rose.push(name(el) + ' ' + text);
    }
    if (el.tagName === 'A' && own && el.closest('.main')) {
      const plain = s.display.startsWith('inline') && !hex(s.backgroundColor) && parseFloat(s.borderTopWidth) === 0 && parseFloat(s.paddingLeft) <= 4;
      const k = hex(s.color), u = s.textDecorationLine.includes('underline');
      if (plain && (k !== '#0D2233' || !u)) out.links.push(name(el) + ' ' + k + (u ? ' u' : ' -') + ' ' + text);
      else if (!plain && (k === '#0B6DD6' || k === '#097852') && !hex(s.backgroundColor)) out.links.push(name(el) + ' (control) ' + k + ' ' + text);
    }
    if (/^H[1-3]$/.test(el.tagName) && hex(s.color) !== '#0D2233') out.heads.push(el.tagName + ' ' + hex(s.color) + ' ' + text);
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName) && !['hidden', 'checkbox', 'radio', 'file', 'submit', 'button', 'range', 'color'].includes(el.type)) {
      const bg = hex(s.backgroundColor), line = parseFloat(s.borderTopWidth) > 0 && hex(s.borderTopColor);
      if (!el.readOnly && (bg === '#FFFFFF' || line)) out.fields.push(name(el) + ' ' + (el.name || el.id) + ' bg ' + bg + ' border ' + line);
    }
  }
  for (const c of document.querySelectorAll('.main .card')) {
    if (c.scrollWidth > c.clientWidth + 1 || [...c.querySelectorAll('*')].some(w => w.clientWidth && w.scrollWidth > w.clientWidth + 1 && ['auto', 'scroll'].includes(getComputedStyle(w).overflowX))) out.overflow.push(name(c));
  }
  // A08 and A09 (guideline 3.32): two to four KPI cards fill a row, every card compares, the figures share a line.
  for (const row of document.querySelectorAll('.main .kpi-row')) {
    const cards = [...row.querySelectorAll(':scope > .kpi-card')];
    if (cards.length < 2 || cards.length > 4) out.kpi.push('a KPI row of ' + cards.length);
    const bottoms = [];
    for (const card of cards) {
      const label = (card.querySelector('.kc-label') || {}).textContent || '?';
      const compare = card.querySelector('.kc-compare');
      if (!compare || !compare.textContent.trim()) out.kpi.push(label + ' has no comparison');
      const figure = card.querySelector('.kc-figure');
      if (figure && card.getBoundingClientRect().top === row.getBoundingClientRect().top) bottoms.push(figure.getBoundingClientRect().bottom);
    }
    if (bottoms.length > 1 && Math.max(...bottoms) - Math.min(...bottoms) > 2) out.kpi.push('figures of a row sit on different lines');
  }
  const jump = document.querySelector('#page-jump');
  if (jump && innerWidth > 760) {
    jump.hidden = false;
    const resting = getComputedStyle(jump).opacity === '0';  // U1: it shows only near the corner or while scrolling
    const button = jump.getBoundingClientRect(), main = document.querySelector('.main');
    if (main) {
      const r = main.getBoundingClientRect(), s = getComputedStyle(main);
      const content = {left: r.left + parseFloat(s.paddingLeft), right: r.right - parseFloat(s.paddingRight)};
      if (!resting && !(button.right + 12 <= content.left || button.left - 12 >= content.right)) out.jump.push('Page control overlaps the content column');
    }
  }
  return out; }""".replace("%TEXT%", json.dumps(TEXT))


def _collect(page):
    """Measure only once the page is at rest: fonts loaded and two frames drawn, so the page-jump control's fade
    has settled (BT-1L: under a parallel run it was measured mid-transition)."""
    page.evaluate("async () => { await document.fonts.ready; await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); }")
    return page.evaluate(COLLECT)


@pytest.fixture(scope="module")
def audit():
    if not CHROMIUM.exists():
        pytest.skip("Chromium is not installed")
    from playwright.sync_api import sync_playwright
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Host

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        host = Host(lambda c: profile_app(c, root / "docs", devices=Devices(root / "app", port=0))).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=str(CHROMIUM))
                page = browser.new_page(viewport={"width": 1366, "height": 768})
                page.goto(host.launch_url)
                page.goto(host.origin + "/profiles/new")
                result = {"/profiles/new": _collect(page)}
                page.fill("input[name=name]", "Mohab")
                for field in ("password", "confirm"):
                    page.fill(f"input[name={field}]", "a dummy audit password")
                page.fill("input[name=answer]", "Dummy")
                if page.locator("select[name=question]").count():
                    page.select_option("select[name=question]", index=1)
                elif page.locator("input[name=question]").count():
                    page.fill("input[name=question]", "Dummy question?")
                page.click("button[type=submit]")
                key = re.search(r"\d{4}-\d{4}-\d{4}", page.content()).group(0)
                if page.locator("form[action='/profiles/confirm'] input[name=recovery][type=text]").count():
                    page.fill("input[name=recovery]", key)
                page.click("form[action='/profiles/confirm'] button[type=submit]")
                page.goto(host.origin + "/")
                result["/welcome"] = _collect(page)
                result["sample_load_style"] = page.locator(".sample-box-load").first.evaluate(
                    "el => [getComputedStyle(el).color, getComputedStyle(el).textDecorationLine]")
                page.evaluate("""async () => { const t = (document.querySelector('meta[name=lightning-session]')||{}).content
                    || document.querySelector('input[name=__session]').value;
                    await fetch('/demo', {method: 'POST', body: new URLSearchParams({__session: t})}); }""")
                for path in PAGES:
                    response = page.goto(host.origin + path)
                    assert response is not None and response.status < 400, f"{path}: HTTP {response and response.status}"
                    page.mouse.move(1, 1)  # a pointer resting on a field would show its hover border
                    result[path] = _collect(page)
                    if path == "/categories":
                        result["category_direction_colors"] = page.locator(".cat-item select[name=direction]").first.evaluate(
                            "el => ['dir-out', 'dir-both', 'dir-in'].map(c => { el.className=c; return getComputedStyle(el).color; })")
                page.goto(host.origin + "/activity")
                expense = page.locator(".compact-row b.neg").first
                result["activity_outflow"] = (expense.evaluate("el => [el.textContent.trim(), getComputedStyle(el).color]")
                                              if expense.count() else None)
                detail = page.locator('.compact-row[href^="/transactions/"]').first
                if detail.count():
                    page.goto(host.origin + detail.get_attribute("href"))
                    result["transaction_heading_size"] = page.locator(".topbar h1").evaluate("el => getComputedStyle(el).fontSize")
                else:
                    result["transaction_heading_size"] = None
                page.goto(host.origin + "/")
                page.keyboard.press("Control+k")
                page.locator(".command-input").fill("budget")
                page.keyboard.press("Escape")
                result["command_closed_on_escape"] = not page.locator("#command-bar").evaluate("el => el.open")
                page.goto(host.origin + "/investments")
                holding = page.locator('a[href*="/investments/holding/"]').first
                if holding.count():
                    page.goto(host.origin + holding.get_attribute("href"))
                    reference = page.locator(".chart-plan.is-reference")
                    result["holding_cost_reference"] = (reference.evaluate("el => getComputedStyle(el).stroke")
                                                        if reference.count() else None)
                else:
                    result["holding_cost_reference"] = None
                browser.close()
        finally:
            host.stop()
    return result


def _fails(audit, key):
    return {path: found[key] for path, found in audit.items() if isinstance(found, dict) and found[key]}


def test_nothing_is_upper_case(audit):
    assert not _fails(audit, "upper")


def test_text_is_only_in_a03_colours(audit):
    assert not _fails(audit, "colors")


def test_links_are_ink_and_underlined(audit):
    assert not _fails(audit, "links")


def test_headers_are_ink(audit):
    assert not _fails(audit, "heads")


def test_fields_are_soft_wells(audit):
    assert not _fails(audit, "fields")


def test_register_amounts_in_rose_are_only_money_out(audit):
    """Owner, 2026-10-30: register money out reads rose (money in stays green). Anything else that is an amount in
    strong rose on a register page, a positive figure for example, is a colour off its meaning (A03)."""
    rows = [row for row in audit["/transactions"]["rose"] + audit["/accounts/1"]["rose"] if "amount" in row]
    assert not [row for row in rows if not row.split("amount", 1)[1].strip().startswith(("\u2212", "-"))]


def test_pages_fit_their_cards(audit):
    assert not _fails(audit, "overflow")


def test_kpi_rows_compare_and_line_up(audit):
    assert not _fails(audit, "kpi")


def test_page_jump_stays_outside_the_figures(audit):
    assert not _fails(audit, "jump")


def test_holding_average_cost_uses_neutral_reference(audit):
    assert audit["holding_cost_reference"] == "rgb(197, 211, 208)"


def test_category_direction_text_uses_meaningful_colours(audit):
    assert audit["category_direction_colors"] == ["rgb(13, 34, 51)", "rgb(13, 34, 51)", "rgb(9, 120, 82)"]


def test_sample_load_action_is_ink_and_underlined(audit):
    assert audit["sample_load_style"] == ["rgb(13, 34, 51)", "underline"]


def test_escape_closes_command_bar_with_a_query(audit):
    assert audit["command_closed_on_escape"]


def test_activity_outflow_is_signed_and_ink(audit):
    assert audit["activity_outflow"] is not None
    amount, color = audit["activity_outflow"]
    assert amount.startswith("−")
    assert color == "rgb(13, 34, 51)"


def test_transaction_title_has_page_heading_size(audit):
    assert audit["transaction_heading_size"] == "28px"
