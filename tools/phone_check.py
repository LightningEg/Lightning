"""Check every main page in the phone frame at 360 and 320 px wide (guideline C12): nothing may scroll
sideways or be clipped past the viewport. Starts the phone app on a dummy profile with the sample household. Needs Playwright and Chromium.

    python tools/phone_check.py [--arabic] [--shots folder]      # prints pages with sideways overflow or clipped elements
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PAGES = ("/home", "/activity", "/activity?tab=review", "/budget/flexible", "/money", "/money/accounts", "/money/bills", "/money/report", "/pc?for=/checks", "/add/bills", "/plan/purchases/new", "/exports/all", "/setup/salary", "/", "/birdview/expenses", "/financial-health", "/budget", "/plan", "/plan/recurring", "/plan/loans",
         "/plan/reserves", "/accounts/currencies", "/investments", "/investments?holdings=all", "/investments/planner", "/investments/prices", "/accounts", "/transactions",
         "/money-from-others", "/zakat", "/settings", "/categories", "/counterparties", "/checks", "/profiles",
         "/profiles/devices", "/accounts/1", "/accounts/1/transaction/new", "/accounts/add-transaction", "/sms", "/search", "/search?q=food")
SMS = ("تم خصم 147.87 EGP من بطاقة الخصم المباشر رقم 2093 عند Uber                  Dow يوم 06/10/26 الساعه 11:13 "
       "المتاح 3512.40EGP للمزيد إتصل ب ١٩٦٢٣")
WIDEST = """() => { const w = innerWidth; let worst = null, right = w;
  for (const el of document.querySelectorAll('body *')) { const r = el.getBoundingClientRect();
    if (r.width && r.right > right + 0.5) { right = r.right; worst = el; } }
  if (!worst) return null;
  return {right: Math.round(right), tag: worst.tagName.toLowerCase(), cls: worst.className && worst.className.baseVal === undefined ? worst.className : '', text: (worst.innerText || '').slice(0, 40)}; }"""

# Unlike scrollWidth, this catches content cut by overflow:hidden on the frame.
# Ignore concealed details, off-canvas controls and horizontally scrollable regions.
CLIPPED = """() => {
  const found = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height || !el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}) ||
        (r.left >= -0.5 && r.right <= innerWidth + 0.5)) continue;
    if (!el.matches('input:not([type=hidden]), select, textarea, button, a') &&
        !Array.from(el.childNodes).some(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim())) continue;
    let clipped = false, ignore = false;
    for (let parent = el.parentElement; parent; parent = parent.parentElement) {
      const ps = getComputedStyle(parent), pr = parent.getBoundingClientRect();
      if (parent.tagName === 'DETAILS' && !parent.open && !el.closest('summary')) { ignore = true; break; }
      if ((ps.overflowX === 'auto' || ps.overflowX === 'scroll') && parent.scrollWidth > parent.clientWidth) {
        ignore = true; break;
      }
      if (ps.overflowX === 'hidden' || ps.overflowX === 'clip') {
        if (r.right <= pr.left || r.left >= pr.right) { ignore = true; break; }
        if (r.left < pr.left - 0.5 || r.right > pr.right + 0.5) clipped = true;
      }
    }
    if (!clipped || ignore) continue;
    found.push({left: Math.round(r.left), right: Math.round(r.right), tag: el.tagName.toLowerCase(),
      text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 40)});
  }
  return found.slice(0, 10);
}"""


def run(shots: Path | None = None, *, arabic: bool = False) -> list[str]:
    from playwright.sync_api import sync_playwright
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Host

    problems: list[str] = []
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        host = Host(lambda c: profile_app(c, root / "docs", devices=Devices(root / "app", port=0), phone=True)).start()
        try:
            with sync_playwright() as p:
                chromium = Path("/opt/pw-browsers/chromium")
                browser = p.chromium.launch(executable_path=str(chromium) if chromium.exists()
                                           else shutil.which("chromium"))
                page = browser.new_page(viewport={"width": 360, "height": 800}, device_scale_factor=2, is_mobile=True,
                                        has_touch=True)
                page.goto(host.launch_url)
                page.goto(host.origin + "/profiles/new")
                page.fill("input[name=name]", "Mohab")
                for field in ("password", "confirm"):
                    page.fill(f"input[name={field}]", "a dummy phone password")
                page.fill("input[name=answer]", "Dummy")
                if page.locator("select[name=question]").count():
                    page.select_option("select[name=question]", index=1)
                elif page.locator("input[name=question]").count():
                    page.fill("input[name=question]", "Dummy question?")
                page.click("form[action='/profiles/new'] button[type=submit]")
                key = re.search(r"\d{4}-\d{4}-\d{4}", page.content()).group(0)
                if page.locator("form[action='/profiles/confirm'] input[name=recovery][type=text]").count():
                    page.fill("input[name=recovery]", key)
                page.click("form[action='/profiles/confirm'] button[type=submit]")
                page.goto(host.origin + "/")
                page.evaluate("""async () => { const t = document.querySelector('meta[name=lightning-session]').content;
                    await fetch('/demo', {method: 'POST', body: new URLSearchParams({__session: t})}); }""")
                review = page.evaluate("""async (sms) => { const t = document.querySelector('meta[name=lightning-session]').content;
                    await fetch('/sms/paste', {method: 'POST', body: new URLSearchParams({__session: t, messages: sms})});
                    const r = await fetch('/sms/assign', {method: 'POST', body: new URLSearchParams({__session: t, ending: '2093', account_id: '1'})});
                    return new URL(r.url).pathname; }""", SMS)
                circle = page.evaluate("""async () => { const t = document.querySelector('meta[name=lightning-session]').content;
                    await fetch('/zakat/enabled', {method: 'POST', body: new URLSearchParams({__session: t, on: '1'})});
                    const r = await fetch('/accounts/new', {method: 'POST', body: new URLSearchParams({__session: t,
                        name: "Office gam'eya", account_type: 'GAMEYA', currency: 'EGP'})});
                    const found = new URL(r.url).pathname.match(/gameya\\/(\\d+)/);
                    if (!found) return '';
                    await fetch('/gameya/' + found[1] + '/terms', {method: 'POST', body: new URLSearchParams({__session: t,
                        organiser: 'Um Ali', members: '10', installment: '2000', first_date: '2026-08-05', my_turn: '3',
                        funding_account_id: '1', payout_account_id: '1', payout: '', interest: 'none', annual_rate: '0'})});
                    return '/gameya/' + found[1]; }""")
                if arabic:
                    page.evaluate("""async () => { const t = document.querySelector('meta[name=lightning-session]').content;
                        await fetch('/settings/locale', {method: 'POST', body: new URLSearchParams({__session: t, locale: 'ar'})}); }""")
                pages = (*PAGES, review, *([circle] if circle else []))  # the bank import's review, as an SMS reaches it; a gam'eya circle
                for width in (360, 320):
                    page.set_viewport_size({"width": width, "height": 800})
                    if width == 320:  # J1 (3AY7): with the number keyboard up (about 340 px left) Save is still on screen
                        page.set_viewport_size({"width": 320, "height": 340})
                        page.goto(host.origin + "/accounts/add-transaction")
                        page.focus("#popup-amount")
                        box = page.locator(".phone-save-bar .phone-save").first.bounding_box()
                        if not box or box["y"] < 0 or box["y"] + box["height"] > 340:
                            problems.append(f"320 /accounts/add-transaction: Save is off screen with the keyboard open ({box})")
                        page.set_viewport_size({"width": 320, "height": 800})
                    for path in pages:
                        response = page.goto(host.origin + path)
                        if response is None or response.status >= 400:
                            problems.append(f"{width} {path}: HTTP {response.status if response else '?'}")
                            continue
                        over = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
                        if over > 0:
                            problems.append(f"{width} {path}: {over}px sideways; widest {page.evaluate(WIDEST)}")
                        # Every row that opens a sheet (D1, 3AN12) opens it and the sheet fits too.
                        for index in range(page.locator(".phone-sheet-row > summary:visible").count()):
                            page.locator(".phone-sheet-row > summary:visible").nth(index).click()
                            page.wait_for_timeout(400)
                            wide = page.evaluate("() => { const p = document.querySelector('.phone-sheet-row[open] .phone-sheet-panel');"
                                                 " return document.documentElement.scrollWidth - innerWidth"
                                                 " + (p && p.scrollWidth > p.clientWidth + 1 ? 1 : 0); }")
                            if wide > 0:
                                problems.append(f"{width} {path}: sheet {index + 1} scrolls sideways")
                            page.evaluate("() => document.querySelectorAll('.phone-sheet-row[open]').forEach((d) => { d.open = false; })")
                        if arabic and not (page.locator("html").get_attribute("lang") or "").startswith("ar"):
                            problems.append(f"{width} {path}: Arabic locale was not applied")
                        if path == "/profiles":
                            masthead = page.locator(".masthead")
                            if masthead.count() and not masthead.evaluate("""e => {
                                const toggle = e.querySelector('.gate-language button');
                                return toggle && toggle.getBoundingClientRect().height >= 48 &&
                                  [...e.children].every(c => { const r = c.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth; });
                            }"""):
                                problems.append(f"{width} {path}: clipped profile header or small language switch")
                        if path == "/counterparties" and page.locator(".alias-details").count():
                            page.locator(".alias-details").first.evaluate("el => el.open = true")
                        if path == "/accounts/currencies":
                            sheet = page.locator(".phone-period-sheet").first
                            if sheet.count():
                                sheet.evaluate("e => e.open = true")
                                custom = sheet.locator(".phone-period-custom > span").first
                                if not custom.count() or not custom.is_visible() or not custom.evaluate("""e => {
                                    const r = e.getBoundingClientRect();
                                    return r.left >= 0 && r.right <= innerWidth && e.scrollWidth <= e.clientWidth;
                                }"""):
                                    problems.append(f"{width} {path}: clipped custom period")
                                sheet.evaluate("e => e.open = false")
                        if path == "/plan":
                            headings = page.evaluate("""() => [...document.querySelectorAll('.phone-flat-rows h2, .phone-flat-rows h3')]
                                .filter(e => { const r = e.getBoundingClientRect(), p = e.closest('.phone-flat-rows').getBoundingClientRect();
                                    return r.left < p.left - .5 || r.right > p.right + .5 || e.scrollWidth > e.clientWidth + 1; })
                                .map(e => e.textContent.trim())""")
                            if headings:
                                problems.append(f"{width} {path}: clipped headings {headings}")
                        if path == "/investments?holdings=all":
                            views = page.locator(".phone-invest-views")
                            if views.count():
                                clipped_views = views.evaluate("""e => [...e.querySelectorAll('a')]
                                    .filter(a => a.scrollWidth > a.clientWidth || a.getBoundingClientRect().right > innerWidth)
                                    .map(a => a.textContent.trim())""")
                                if clipped_views:
                                    problems.append(f"{width} {path}: clipped views {clipped_views}")
                        clipped = page.evaluate(CLIPPED)
                        if clipped:
                            problems.append(f"{width} {path}: clipped past viewport {clipped}")
                        if shots is not None and width == 360:
                            shots.mkdir(parents=True, exist_ok=True)
                            name = path.strip("/").replace("/", "-").replace("?", "-").replace("=", "-") or "overview"
                            page.screenshot(path=str(shots / f"{name}.png"), full_page=True)
                browser.close()
        finally:
            host.stop()
    return problems


if __name__ == "__main__":
    shots = Path(sys.argv[sys.argv.index("--shots") + 1]) if "--shots" in sys.argv else None
    found = run(shots, arabic="--arabic" in sys.argv)
    print("\n".join(found) or "Nothing scrolls sideways or clips past the viewport at 360 or 320.")
    sys.exit(1 if found else 0)
