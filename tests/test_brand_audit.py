"""Brand audit in a real browser (guideline A03, A05, A10.3, A16): on the main PC pages, with the Mohab sample at
1366 × 768 px, nothing is upper-case, text is only in A03 colours, plain links are Ink and underlined, H1 to H3 are Ink,
no field is white or boxed, fieldsets do not draw nested boxes, chart end labels do not overlap, money out in the
register is rose and never a positive figure, and the register fits its card.
Skipped on a machine without Playwright or Chromium; required in CI (tests/browser_support.py)."""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest
from tests.browser_support import chromium_executable, require_chromium

pytest.importorskip("playwright")
CHROMIUM = chromium_executable()

PAGES = ("/plan/purchases/new", "/exports/all", "/setup/salary", "/", "/transactions", "/accounts", "/accounts/1", "/accounts/currencies", "/settings", "/investments",
         "/investments/prices", "/budget", "/plan", "/birdview/expenses", "/financial-health", "/categories", "/settings?section=budget",
         "/profiles", "/plan/recurring", "/plan/loans", "/plan/reserves", "/activity", "/sms", "/transactions/deleted",
         "/checks", "/counterparties")
# A05: under the title, the page's answer and its dates; never a slogan or what the tab is for (3S4, 3S6).
STATUS_PAGES = ("/birdview/expenses", "/activity", "/sms", "/transactions/deleted", "/checks", "/counterparties")
# A03: Ink, Ink 2, Muted, Meadow text, Azure, Strong rose, Nile, and white on Nile or on the vivid gradient.
TEXT = ["#0D2233", "#304A5C", "#566E7E", "#097852", "#0B6DD6", "#C93D72", "#0A2442", "#FFFFFF"]

COLLECT = """() => {
  const TEXT = %TEXT%;
  const hex = c => { const m = c.match(/[\\d.]+/g); if (!m) return null; if (m.length > 3 && +m[3] === 0) return null;
    return '#' + m.slice(0, 3).map(x => (+x).toString(16).padStart(2, '0')).join('').toUpperCase(); };
  const out = {upper: [], colors: [], links: [], heads: [], fields: [], fieldsets: [], chart_labels: [], rose: [], overflow: [], jump: [], kpi: [], joined: [], breadcrumbs: []};
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
  // A16: a semantic fieldset must not draw a card inside a card; a segmented choice is a control, not a card.
  for (const el of document.querySelectorAll('.main .card fieldset:not(.planner-mode)')) {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    if (!r.width || !r.height || s.visibility === 'hidden' || el.closest('[hidden],[inert]')) continue;
    const bg = hex(s.backgroundColor);
    if (parseFloat(s.borderTopWidth) > 0 || bg) out.fieldsets.push(name(el) + ' ' + (el.querySelector('legend')?.textContent.trim() || ''));
  }
  // A12: labels for different series must not overlap when the browser draws them.
  for (const plot of document.querySelectorAll('.main .chart-plot, .main .pace-plot')) {
    const labels = [...plot.querySelectorAll('.chart-end, .pace-end small')].filter(el => {
      const r = el.getBoundingClientRect(), s = getComputedStyle(el);
      return r.width && r.height && s.visibility !== 'hidden' && !el.closest('[hidden],[inert]');
    });
    for (let i = 0; i < labels.length; i++) for (let j = i + 1; j < labels.length; j++) {
      const a = labels[i].getBoundingClientRect(), b = labels[j].getBoundingClientRect();
      if (a.left < b.right - 0.5 && a.right > b.left + 0.5 && a.top < b.bottom - 0.5 && a.bottom > b.top + 0.5)
        out.chart_labels.push(labels[i].textContent.trim() + ' / ' + labels[j].textContent.trim());
    }
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
  // 3Q: the older stat-tile rows answer to the same rules until they move to kpi_row.
  for (const row of document.querySelectorAll('.main .stat-tiles')) {
    const tiles = [...row.querySelectorAll(':scope > .stat-tile')];
    if (tiles.length < 2 || tiles.length > 4) out.kpi.push('a stat-tile row of ' + tiles.length);
    const bottoms = [];
    for (const tile of tiles) {
      const label = (tile.querySelector('.stat-tile-label') || {}).textContent || '?';
      const compare = tile.querySelector('.stat-tile-sub, .stat-compare');
      if (!compare || !compare.textContent.trim()) out.kpi.push(label.trim() + ' has no comparison');
      const figure = tile.querySelector('.stat-tile-value');
      if (figure && tile.getBoundingClientRect().top === row.getBoundingClientRect().top) bottoms.push(figure.getBoundingClientRect().bottom);
    }
    if (bottoms.length > 1 && Math.max(...bottoms) - Math.min(...bottoms) > 2) out.kpi.push('stat-tile figures sit on different lines');
  }
  // TE-3 (3H): words run together where an inline link meets text ("the same asRecurringon"), and TE-2: no "L1 › L2"
  // between category names in the rendered text of the page's content.
  const main = document.querySelector('.main');
  if (main) {
    const seen = main.innerText;
    for (const m of seen.matchAll(/\\b[a-z]{2,}[A-Z][a-z]{2,}\\b/g)) out.joined.push(m[0]);
    for (const m of seen.matchAll(/\\b(Personal|Work|Family) › [A-Z][\\w&' ]+/g)) out.breadcrumbs.push(m[0]);
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
    require_chromium()
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
                result["first_account_surface"] = page.locator('.first-account-choices').evaluate(
                    'el => [getComputedStyle(el).backgroundColor, getComputedStyle(el).boxShadow]')
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
                    result.setdefault("header_status", []).append([path, page.evaluate("""() => {
                        const head = document.querySelector('.topbar') || document;
                        const line = head.querySelector('.page-status, .page-line');
                        return line ? line.textContent.trim() : null; }""")])
                    if path == "/birdview/expenses":
                        result["spending_multiple_surfaces"] = page.locator('.multiples .multiple').evaluate_all(
                            'els => els.map(el => [getComputedStyle(el).borderTopWidth, getComputedStyle(el).backgroundColor])')
                    if path == "/categories":
                        result["category_direction_colors"] = page.locator(".cat-item select[name=direction]").first.evaluate(
                            "el => ['dir-out', 'dir-both', 'dir-in'].map(c => { el.className=c; return getComputedStyle(el).color; })")
                page.goto(host.origin + "/activity")
                result["activity_breadcrumbs"] = page.locator('.compact-row small').evaluate_all(
                    'els => els.filter(el => el.textContent.includes(" › ")).map(el => el.textContent.trim())')
                expense = page.locator(".compact-row b.neg").first
                result["activity_outflow"] = (expense.evaluate("el => [el.textContent.trim(), getComputedStyle(el).color]")
                                              if expense.count() else None)
                detail = page.locator('.compact-row[href^="/transactions/"]').filter(has=page.locator('b.neg')).first
                if detail.count():
                    page.goto(host.origin + detail.get_attribute("href"))
                    result["transaction_heading_size"] = page.locator(".topbar h1").evaluate("el => getComputedStyle(el).fontSize")
                    result["transaction_category_breadcrumbs"] = page.locator('.category-context').evaluate_all(
                        'els => els.filter(el => el.textContent.includes(" › ")).map(el => el.textContent.trim())')
                    result["transaction_primary_count"] = page.locator('.main button.primary:visible').count()
                    result["transaction_actions_layout"] = []
                    for width in (1024, 1366, 1920):
                        page.set_viewport_size({"width": width, "height": 768})
                        result["transaction_actions_layout"].append(page.locator('.transaction-actions-grid').evaluate("""el => {
                            const cards = [...el.children], a = cards[0].getBoundingClientRect(), b = cards[1].getBoundingClientRect();
                            const picker = el.querySelector('.reserve-allocate input[role="combobox"]');
                            return {paired: Math.abs(a.top-b.top) < 2,
                                    overflow: cards.some(c => c.scrollWidth > c.clientWidth + 1),
                                    clipped: !!picker && picker.scrollWidth > picker.clientWidth + 1};
                        }"""))
                    page.set_viewport_size({"width": 1366, "height": 768})
                else:
                    result["transaction_heading_size"] = None
                    result["transaction_category_breadcrumbs"] = None
                    result["transaction_actions_layout"] = None
                    result["transaction_primary_count"] = None
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
                page.goto(host.origin + "/counterparties")
                result["counterparty_overlaps"] = []
                for width in (1024, 1366, 1920):
                    page.set_viewport_size({"width": width, "height": 768})
                    result["counterparty_overlaps"].append(page.locator('.cp-row').evaluate_all("""rows => rows.flatMap(row => {
                        row.open = true;
                        const field = row.querySelector('.cp-field'), kind = row.querySelector('.counterparty-kind');
                        if (!field || !kind) return [];
                        const a = field.getBoundingClientRect(), b = kind.getBoundingClientRect();
                        return a.width && b.width && a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top
                            ? [row.querySelector('summary b')?.textContent.trim() || '?'] : [];
                    })"""))
                page.set_viewport_size({"width": 1366, "height": 768})
                first = page.locator('.cp-row').first
                first.locator('.alias-details > summary').click()
                alias = first.locator('.alias-add input[name=alias]')
                alias.fill('Audit example alias')
                result["alias_enter_hint"] = first.locator('.alias-enter-hint').is_visible()
                alias.press('Enter')
                # BV-12AG: the save refreshes the page in place; wait for the saved alias, not for a page load.
                try:
                    page.wait_for_function("() => document.querySelector('[data-refresh]').innerHTML.includes('Audit example alias')"
                                           " && !document.querySelector('.alias-add input[name=alias]')?.value", timeout=10000)
                except Exception:
                    pass
                result["alias_saved"] = 'Audit example alias' in page.content()
                # Exercise the audit itself with real browser geometry in both failing and passing states.
                page.set_content("""<main class="main"><section class="card"><p>the same as<a href="#">Recurring</a>on Categories · Personal › Eating out</p><fieldset style="border:1px solid black"><legend>Example</legend></fieldset>
                    <div class="chart-plot" style="position:relative;width:200px;height:100px">
                    <span class="chart-end" style="position:absolute;left:30px;top:10px">100</span>
                    <span class="chart-end" style="position:absolute;left:30px;top:10px">200</span></div></section></main>""")
                bad = page.evaluate(COLLECT)
                page.locator('fieldset').evaluate("el => el.style.border='0'")
                page.locator('.chart-end').last.evaluate("el => el.style.top='60px'")
                good = page.evaluate(COLLECT)
                result["detector_controls"] = [bool(bad["fieldsets"]), bool(bad["chart_labels"]),
                                               bool(good["fieldsets"]), bool(good["chart_labels"])]
                result["text_detectors"] = [bad["joined"], bad["breadcrumbs"]]
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


def test_pc_first_account_list_is_not_a_box(audit):
    assert audit["first_account_surface"] == ["rgba(0, 0, 0, 0)", "none"]


def test_pc_spending_multiples_are_not_nested_boxes(audit):
    assert audit["spending_multiple_surfaces"]
    assert all(border == "0px" and background == "rgba(0, 0, 0, 0)"
               for border, background in audit["spending_multiple_surfaces"])


def test_activity_and_transaction_categories_are_not_breadcrumbs(audit):
    assert audit["transaction_category_breadcrumbs"] is not None
    assert not audit["activity_breadcrumbs"]
    assert not audit["transaction_category_breadcrumbs"]


def test_fieldsets_do_not_draw_boxes_inside_cards(audit):
    assert not _fails(audit, "fieldsets")


def test_chart_end_labels_do_not_overlap(audit):
    assert not _fails(audit, "chart_labels")


def test_fieldset_and_label_detectors_find_and_clear_real_browser_overlap(audit):
    assert audit["detector_controls"] == [True, True, False, False]


def test_transaction_action_cards_pair_where_they_fit(audit):
    assert audit["transaction_actions_layout"] == [
        {"paired": False, "overflow": False, "clipped": False},
        {"paired": True, "overflow": False, "clipped": False},
        {"paired": True, "overflow": False, "clipped": False},
    ]


def test_transaction_has_at_most_one_visible_primary(audit):
    assert audit["transaction_primary_count"] is not None
    assert audit["transaction_primary_count"] <= 1


def test_counterparty_controls_do_not_overlap_and_alias_saves_with_enter(audit):
    assert audit["counterparty_overlaps"] == [[], [], []]
    assert audit["alias_enter_hint"] and audit["alias_saved"]


def test_titles_carry_a_status_line_not_a_description(audit):
    """A05 (3S4): the line under these titles states a figure or a fact, never what the tab is for."""
    lines = dict(audit["header_status"])
    missing = [path for path in STATUS_PAGES if not lines.get(path)]
    assert not missing, f"no status line under the title: {missing}"
    describing = {path: lines[path] for path in STATUS_PAGES
                  if re.search(r"(stay here so|become transactions|saved names, aliases|compare totals|linked to them)", lines[path])}
    assert not describing, describing


def test_no_words_run_together(audit):
    """TE-3 (3H): an inline link without its spaces reads "asRecurringon"; the rendered text never has one."""
    assert not _fails(audit, "joined")


def test_no_category_breadcrumbs_in_rendered_text(audit):
    """TE-2 (3H), A16 "L1 › L2: Header, then list": a category is its own name, the group a header or small label."""
    assert not _fails(audit, "breadcrumbs")


def test_the_text_detectors_find_what_they_look_for(audit):
    joined, crumbs = audit["text_detectors"]
    assert joined == ["asRecurringon"] and crumbs and crumbs[0].startswith("Personal › Eating out")
