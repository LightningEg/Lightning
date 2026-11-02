"""Audit 13: drive the phone's quick tasks at 360 x 800 on the sample household; count taps, measure where actions sit.

    python reports/2026-11-01-phone-convenience-audit/evidence/flows.py <out-folder> [ar]   # from the repo root; needs Playwright
Prints JSON: per page the first-screen content and the y of each action; per task the taps and what each step showed.

A tap is one press: a button, a chip, a row, a link. Typing the amount or pasting is not counted (the audit's own count did not
count it either: "Add, account, amount, ..." was "6 and a scroll"). `taps` lists every press of the three jobs the capture
half of IV-3AN rebuilt, so the table can be re-filled from the output: J1 record a payment, J2 turn a bank SMS into a
transaction, J5 sort a row (and find a payment). Updated for 3AN3, 3AN5 and 3AN6 (2026-11-02): Add opens the sheet on the
amount, the category is a chip, Paste SMS is in the sheet, a row opens its sheet, Search is live.
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
  const save = s.querySelector('.phone-save'); const frame = s.querySelector('.app-popup-frame');
  const f = [...s.querySelectorAll('input, select, textarea, button')].filter(e => e.getBoundingClientRect().height)
     .map(e => ({tag: e.tagName.toLowerCase(), type: e.type, name: e.name, mode: e.inputMode || '', auto: e.autofocus, ph: e.placeholder || '',
                 y: Math.round(e.getBoundingClientRect().top), h: Math.round(e.getBoundingClientRect().height), t: (e.innerText||e.value||'').trim().slice(0,24)}));
  return {text: s.innerText.slice(0, 900), fields: f, active: document.activeElement && (document.activeElement.name || document.activeElement.tagName),
          save_y: save ? Math.round(save.getBoundingClientRect().bottom) : null, sheet_bottom: frame ? Math.round(frame.getBoundingClientRect().bottom) : null}; }"""
# Three rows nobody has sorted, posted the way an import posts them (the sample has none), through the app's own container in the
# server's thread (an encrypted profile's database stays on its owning thread).
SORT_ROWS = (("2026-11-01", "150", "Magic Stall"), ("2026-10-31", "85", "Corner Shop"), ("2026-10-30", "420", "Pharmacy 19011"))
SMS = ("تم سحب مبلغ  EGP 5000.00  من بطاقة الخصم المباشر المنتهية بـ **7351 من CIB KZ IRAN ZAMALEK "
       "في 04/10/26 19:28 ، الرصيد المتاح EGP 12904.50")


def serve(root):
    def factory(cfg):
        app = profile_app(cfg, root / "docs", devices=Devices(root / "app", port=0), phone=True)

        async def wrapper(scope, receive, send):
            if scope["type"] == "http" and scope["path"] == "/__seed-unsorted":
                c = app.session.container
                account = c.accounts.list(active_only=True)[0].id
                unfiled = c.categories.get_by_code("EXP.UNACCOUNTED").id
                for day, amount, who in SORT_ROWS:
                    c.transactions.record_outflow(day, account, amount, unfiled, counterparty=who, allow_system_category=True)
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"ok"})
                return
            await app(scope, receive, send)
        wrapper.session = app.session
        return wrapper
    return Host(factory).start()


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

res = {"pages": {}, "tasks": {}, "taps": {}}
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    host = serve(root)
    with sync_playwright() as p:
        exe = "/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else shutil.which("chromium")
        b = p.chromium.launch(executable_path=exe)
        context = b.new_context(viewport={"width": 360, "height": 800}, device_scale_factor=1, is_mobile=True, has_touch=True)
        context.grant_permissions(["clipboard-read", "clipboard-write"], origin=host.origin)
        page = context.new_page()
        login(page, host)
        shot = lambda n: page.screenshot(path=str(OUT / f"{n}.png"))
        for path in ["/", "/budget", "/transactions", "/more", "/accounts", "/plan"]:
            page.goto(host.origin + path)
            ts = page.evaluate(TARGETS)
            res["pages"][path] = {"first_screen_targets": [t for t in ts if t["y"] < 735],
                                  "first_row_y": page.evaluate("() => { const r = document.querySelector('.phone-latest .phone-txn, .phone-cat, .phone-hub-bill, .phone-plan-row, .phone-day-rows .phone-txn'); return r ? Math.round(r.getBoundingClientRect().top + scrollY) : null }")}
        # J1: record a payment from Overview: Add, (type the amount), a category chip, Save.
        page.goto(host.origin + "/"); steps = []; taps = []
        page.click(".phone-add"); taps.append("Add"); page.wait_for_timeout(700); steps.append(page.evaluate(SHEET)); shot("t1-1-add")
        page.keyboard.type("120")
        page.locator("#app-popup [data-category]:visible").nth(1).click(); taps.append("a category chip"); page.wait_for_timeout(200)
        steps.append(page.evaluate(SHEET)); shot("t1-2-chip")
        page.screenshot(path=str(OUT / "t1-2-entry-full.png"), full_page=True)
        page.click("#app-popup .phone-save"); taps.append("Save"); page.wait_for_timeout(1500); shot("t1-3-saved")
        steps.append({"toast": page.locator(".phone-flash").inner_text() if page.locator(".phone-flash").count() else None, "url": page.url})
        res["tasks"]["add expense"] = steps; res["taps"]["J1 record a payment"] = {"taps": len(taps), "presses": taps, "typed": "the amount"}

        # Task 2 (J3): pay the next bill from Overview: the bill Needs you names, then Record and mark paid
        page.goto(host.origin + "/"); steps = []
        bill = page.locator(".phone-needs-bill")
        steps.append({"named": bill.inner_text() if bill.count() else None, "y": page.evaluate("() => { const b = document.querySelector('.phone-needs-bill'); return b ? Math.round(b.getBoundingClientRect().top) : null }")})
        if bill.count():
            bill.click(); page.wait_for_timeout(900); steps.append(page.evaluate(SHEET)); shot("t2-pay-sheet")
            pay = page.locator("#app-popup button").filter(has_text="Record and mark")
            steps.append({"mark paid button": pay.count(), "y": pay.first.evaluate("e => Math.round(e.getBoundingClientRect().top)") if pay.count() else None})
        res["tasks"]["J3 pay the next bill"] = {"taps": 2 if bill.count() and pay.count() else None, "steps": steps}
        # Task 3: Needs you open
        page.goto(host.origin + "/")
        nd = page.locator("main details, main summary, main a").filter(has_text="Open").first
        if nd.count(): nd.click(); page.wait_for_timeout(500); shot("t3-needs-you")
        res["tasks"]["needs you"] = page.locator("main").inner_text()[300:1100]
        # Task 4: tap a transaction row: its own sheet, to look at first
        page.goto(host.origin + "/transactions")
        row = page.locator("main a.phone-txn").filter(has_text="ACME Egypt").first
        if row.count(): row.click(); page.wait_for_timeout(800); shot("t4-row-sheet"); res["tasks"]["row tap"] = {"url": page.url, "sheet": page.evaluate(SHEET)}
        # Task 5: search, live, from the app bar: the icon, then the words
        page.goto(host.origin + "/")
        page.locator("header a[href*=search]").first.click(); page.wait_for_timeout(600)
        page.keyboard.type("carrefour"); page.wait_for_timeout(900)
        shot("t5-search"); res["tasks"]["search"] = {"url": page.url, "text": page.locator("body").inner_text()[:700],
                                                     "taps": 1, "payments_first": page.locator("#search-results h2").first.inner_text()}
        res["taps"]["J5 search"] = {"taps": 1, "presses": ["the search icon"], "typed": "the words"}
        # J2: Add, Paste SMS (the card ending was said once before, as it is after the first message)
        page.goto(host.origin + "/sms")
        page.evaluate("""async () => { const t = document.querySelector('meta[name=lightning-session]').content;
            await fetch('/sms/assign', {method: 'POST', body: new URLSearchParams({__session: t, ending: '7351', account_id: '1'})}); }""")
        page.goto(host.origin + "/"); taps = []
        page.evaluate("(text) => navigator.clipboard.writeText(text)", SMS)
        page.click(".phone-add"); taps.append("Add"); page.wait_for_timeout(700)
        page.click("#app-popup [data-sms-paste]"); taps.append("Paste SMS"); page.wait_for_timeout(1200)
        shot("t6-sms-in-add")
        filled = page.evaluate("""() => ({amount: document.querySelector('#app-popup [name=amount]').value, who: document.querySelector('#app-popup [name=counterparty]').value,
            date: document.querySelector('#app-popup [name=date]').value, kind: document.querySelector('#app-popup [name=kind]:checked').value,
            account: document.querySelector('#app-popup [data-account-chip]') && document.querySelector('#app-popup [data-account-chip]').selectedOptions[0].textContent,
            category: document.querySelector('#app-popup [name=category_id]').value})""")
        res["tasks"]["sms in add"] = {"filled": filled, "sheet": page.evaluate(SHEET)}
        res["taps"]["J2 bank SMS to transaction"] = {"taps": len(taps), "presses": taps, "then": "check and Save"}
        page.goto(host.origin + "/sms"); shot("t6-sms-page"); res["tasks"]["sms page"] = page.locator("main").inner_text()[:600]
        # J5: sort a row: To sort, the row, a category chip (the next unsorted row opens by itself)
        page.goto(host.origin + "/__seed-unsorted"); page.goto(host.origin + "/transactions?preset=all_time"); taps = []
        page.locator("a.phone-chip", has_text="To sort").click(); taps.append("To sort"); page.wait_for_timeout(700)
        page.locator("a.phone-txn").first.click(); taps.append("the row"); page.wait_for_timeout(800); shot("t7-sort-sheet")
        before = page.locator("#app-popup .phone-sheet-title").inner_text()
        page.locator("#app-popup .phone-cat-chips button").first.click(); taps.append("a category chip"); page.wait_for_timeout(900)
        after = page.locator("#app-popup .phone-sheet-title").inner_text(); shot("t7-sort-next")
        res["tasks"]["sort"] = {"first": before, "next_opened_by_itself": after}
        res["taps"]["J5 sort a row"] = {"taps": len(taps), "presses": taps, "next_row": after != before}
        # Task 7 (J4): "how much is left for groceries?": the row is in the first screen; one tap opens its sheet
        page.goto(host.origin + "/budget")
        row = page.locator(".phone-cat").filter(has_text="Food & Groceries").first
        y = row.evaluate("e => Math.round(e.getBoundingClientRect().top)")
        row.click(); page.wait_for_timeout(700)
        shot("t7-budget-category")
        res["tasks"]["J4 budget category"] = {"row_y": y, "in_first_screen": y < 735, "taps": 1, "sheet": page.locator(".phone-sheet-row[open] .phone-sheet-panel").inner_text()[:400]}
        # Task 8: 320 wide
        page.set_viewport_size({"width": 320, "height": 700}); page.goto(host.origin + "/"); shot("t9-overview-320")
        page.goto(host.origin + "/transactions"); shot("t9-transactions-320")
        page.click(".phone-add"); page.wait_for_timeout(700); shot("t9-add-320")
        b.close()
    host.stop()
(OUT / "flows.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
print(json.dumps(res, indent=1, ensure_ascii=False)[:12000])

# Arabic and dark: the three daily screens and the entry sheet (run with a second argument "ar").
if len(sys.argv) > 2 and sys.argv[2] == "ar":
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        host = serve(root)
        with sync_playwright() as p:
            exe = "/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else shutil.which("chromium")
            b = p.chromium.launch(executable_path=exe)
            page = b.new_page(viewport={"width": 360, "height": 800}, device_scale_factor=1, is_mobile=True, has_touch=True, color_scheme="dark")
            login(page, host)
            page.evaluate("""async () => { const t = document.querySelector('meta[name=lightning-session]').content;
                await fetch('/settings/locale', {method: 'POST', body: new URLSearchParams({__session: t, locale: 'ar'})}); }""")
            for path, name in (("/", "ar-overview"), ("/budget", "ar-budget"), ("/transactions", "ar-transactions"), ("/more", "ar-more"),
                               ("/search?q=carrefour", "ar-search"), ("/sms", "ar-sms")):
                page.goto(host.origin + path); page.screenshot(path=str(OUT / f"{name}.png"))
            page.goto(host.origin + "/accounts/1"); page.click(".phone-add"); page.wait_for_timeout(900)
            page.screenshot(path=str(OUT / "ar-entry.png"))
            b.close()
        host.stop()
