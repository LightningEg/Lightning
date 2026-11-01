"""Audit 13: drive the phone's quick tasks at 360 x 800 on the sample household; count taps, measure where actions sit.

    python reports/2026-11-01-phone-convenience-audit/evidence/flows.py <out-folder>    # from the repo root; needs Playwright
Prints JSON: per page the first-screen content and the y of each action; per task the taps and what each step showed.
"""
import json, re, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
from playwright.sync_api import sync_playwright
from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Host

TARGETS = """() => [...document.querySelectorAll('main a, main button, main summary, main input, main select, main [role=button]')]
  .filter(e => { const r = e.getBoundingClientRect(); return r.width && r.height && !e.closest('dialog:not([open]), details:not([open]) > :not(summary)'); })
  .map(e => { const r = e.getBoundingClientRect(); return {t: (e.innerText||e.value||e.getAttribute('aria-label')||e.name||'').trim().replace(/\\s+/g,' ').slice(0,28),
     y: Math.round(r.top + scrollY), h: Math.round(r.height), w: Math.round(r.width)}; })"""
SHEET = """() => { const s = document.querySelector('#app-popup'); if (!s) return null;
  const f = [...s.querySelectorAll('input, select, textarea, button')].filter(e => e.getBoundingClientRect().height)
     .map(e => ({tag: e.tagName.toLowerCase(), type: e.type, name: e.name, mode: e.inputMode || '', auto: e.autofocus, ph: e.placeholder || '',
                 y: Math.round(e.getBoundingClientRect().top), h: Math.round(e.getBoundingClientRect().height), t: (e.innerText||e.value||'').trim().slice(0,24)}));
  return {text: s.innerText.slice(0, 900), fields: f, active: document.activeElement && (document.activeElement.name || document.activeElement.tagName)}; }"""

def login(page, host):
    page.goto(host.launch_url); page.goto(host.origin + "/profiles/new")
    page.fill("input[name=name]", "Mohab")
    for f in ("password", "confirm"): page.fill(f"input[name={f}]", "a dummy phone password")
    page.fill("input[name=answer]", "Dummy")
    if page.locator("select[name=question]").count(): page.select_option("select[name=question]", index=1)
    elif page.locator("input[name=question]").count(): page.fill("input[name=question]", "Dummy question?")
    page.click("button[type=submit]")
    key = re.search(r"\d{4}-\d{4}-\d{4}", page.content()).group(0)
    if page.locator("form[action='/profiles/confirm'] input[name=recovery][type=text]").count(): page.fill("input[name=recovery]", key)
    page.click("form[action='/profiles/confirm'] button[type=submit]")
    page.goto(host.origin + "/")
    page.evaluate("""async () => { const t = document.querySelector('meta[name=lightning-session]').content;
        await fetch('/demo', {method: 'POST', body: new URLSearchParams({__session: t})}); }""")

res = {"pages": {}, "tasks": {}}
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    host = Host(lambda c: profile_app(c, root / "docs", devices=Devices(root / "app", port=0), phone=True)).start()
    with sync_playwright() as p:
        exe = "/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else shutil.which("chromium")
        b = p.chromium.launch(executable_path=exe)
        page = b.new_page(viewport={"width": 360, "height": 800}, device_scale_factor=1, is_mobile=True, has_touch=True)
        login(page, host)
        shot = lambda n: page.screenshot(path=str(OUT / f"{n}.png"))
        for path in ["/", "/budget", "/transactions", "/more", "/accounts", "/plan"]:
            page.goto(host.origin + path)
            ts = page.evaluate(TARGETS)
            res["pages"][path] = {"first_screen_targets": [t for t in ts if t["y"] < 735],
                                  "first_row_y": page.evaluate("() => { const r = [...document.querySelectorAll('main section h2, main h2')].find(h => /Latest|Categories|Next 14|Coming up|Today/.test(h.innerText)); return r ? Math.round(r.getBoundingClientRect().top) : null }")}
        # Task 1: add an expense from Overview
        page.goto(host.origin + "/"); steps = []
        page.click(".phone-add"); page.wait_for_timeout(600); steps.append(page.evaluate(SHEET)); shot("t1-1-add")
        page.locator("#app-popup a, #app-popup button").filter(has_text="Cash wallet").first.click(); page.wait_for_timeout(900)
        steps.append(page.evaluate(SHEET)); shot("t1-2-entry")
        page.screenshot(path=str(OUT / "t1-2-entry-full.png"), full_page=True)
        res["tasks"]["add expense"] = steps
        # Task 2: the page menu behind the title
        page.goto(host.origin + "/")
        page.click("details.phone-page-menu summary"); page.wait_for_timeout(300); shot("t2-page-menu")
        res["tasks"]["title menu"] = page.locator(".phone-page-grid").inner_text()[:500]
        # Task 3: Needs you open
        page.goto(host.origin + "/")
        nd = page.locator("main details, main summary, main a").filter(has_text="Open").first
        if nd.count(): nd.click(); page.wait_for_timeout(500); shot("t3-needs-you")
        res["tasks"]["needs you"] = page.locator("main").inner_text()[300:1100]
        # Task 4: tap a transaction row
        page.goto(host.origin + "/transactions")
        row = page.locator("main a, main [role=button], main .phone-row").filter(has_text="ACME Egypt").first
        if row.count(): row.click(); page.wait_for_timeout(800); shot("t4-row-sheet"); res["tasks"]["row tap"] = {"url": page.url, "sheet": page.evaluate(SHEET)}
        # Task 5: search
        page.goto(host.origin + "/")
        page.locator("header a[href*=search], header button[aria-label*=earch], a[aria-label*=earch]").first.click(); page.wait_for_timeout(600)
        shot("t5-search"); res["tasks"]["search"] = {"url": page.url, "text": page.locator("body").inner_text()[:500]}
        # Task 6: From SMS
        page.goto(host.origin + "/sms"); shot("t6-sms"); res["tasks"]["sms"] = page.locator("main").inner_text()[:600]
        # Task 7: budget category tap
        page.goto(host.origin + "/budget")
        page.locator("main a").filter(has_text="Food & Groceries").first.click(); page.wait_for_timeout(700)
        shot("t7-budget-category"); res["tasks"]["budget category"] = {"url": page.url, "text": page.locator("main").inner_text()[:500]}
        # Task 8: 320 wide and Arabic overview
        page.set_viewport_size({"width": 320, "height": 700}); page.goto(host.origin + "/"); shot("t8-overview-320")
        page.goto(host.origin + "/transactions"); shot("t8-transactions-320")
        b.close()
    host.stop()
(OUT / "flows.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
print(json.dumps(res, indent=1, ensure_ascii=False)[:12000])

# Arabic and dark: the three daily screens and the entry sheet (run with a second argument "ar").
if len(sys.argv) > 2 and sys.argv[2] == "ar":
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        host = Host(lambda c: profile_app(c, root / "docs", devices=Devices(root / "app", port=0), phone=True)).start()
        with sync_playwright() as p:
            exe = "/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else shutil.which("chromium")
            b = p.chromium.launch(executable_path=exe)
            page = b.new_page(viewport={"width": 360, "height": 800}, device_scale_factor=1, is_mobile=True, has_touch=True, color_scheme="dark")
            login(page, host)
            page.evaluate("""async () => { const t = document.querySelector('meta[name=lightning-session]').content;
                await fetch('/settings/locale', {method: 'POST', body: new URLSearchParams({__session: t, locale: 'ar'})}); }""")
            for path, name in (("/", "ar-overview"), ("/budget", "ar-budget"), ("/transactions", "ar-transactions"), ("/more", "ar-more")):
                page.goto(host.origin + path); page.screenshot(path=str(OUT / f"{name}.png"))
            page.goto(host.origin + "/accounts/1"); page.click(".phone-add"); page.wait_for_timeout(900)
            page.screenshot(path=str(OUT / "ar-entry.png"))
            b.close()
        host.stop()
