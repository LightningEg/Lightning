"""r30 phone capture: the first run (empty slots), then the demo household's text on the key pages, the Add sheet
opened from Home (prints which field has the focus), then the five slots in Arabic. A dummy encrypted profile in a
temporary folder; nothing is kept.

    python issues/12-desktop-ux/r30-ux-against-users-questions/evidence/phone_capture.py OUT
The English slots themselves come from Nothing scrolls sideways or clips past the viewport at 360 or 320.. Needs Playwright, Chromium, sqlcipher3.
"""
import re, sys, json, tempfile
from pathlib import Path
REPO, OUT = Path(__file__).resolve().parents[4], Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True); sys.path.insert(0, str(REPO))
from playwright.sync_api import sync_playwright
from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Host
POST = """async ([path, data]) => { const t = document.querySelector('meta[name=lightning-session]').content;
  const r = await fetch(path, {method: 'POST', body: new URLSearchParams({__session: t, ...data})}); return r.status; }"""
SLOTS = ["/home", "/budget/flexible", "/accounts/add-transaction", "/activity", "/money"]
TEXT = ["/home", "/budget/flexible", "/money", "/money/accounts", "/money/bills", "/plan", "/plan/reserves", "/activity?tab=review", "/search?q=food", "/money/report"]
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    host = Host(lambda c: profile_app(c, root / "docs", devices=Devices(root / "app", port=0), phone=True)).start()
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        pg = b.new_page(viewport={"width": 360, "height": 760}, device_scale_factor=2, is_mobile=True, has_touch=True)
        pg.goto(host.launch_url); pg.screenshot(path=str(OUT / "00-gate.png"))
        pg.goto(host.origin + "/profiles/new"); pg.screenshot(path=str(OUT / "01-new-profile.png"), full_page=True)
        pg.fill("input[name=name]", "Mohab")
        for f in ("password", "confirm"): pg.fill(f"input[name={f}]", "a dummy phone password")
        pg.fill("input[name=answer]", "Dummy")
        if pg.locator("select[name=question]").count(): pg.select_option("select[name=question]", index=1)
        elif pg.locator("input[name=question]").count(): pg.fill("input[name=question]", "Dummy question?")
        pg.click("form[action='/profiles/new'] button[type=submit]")
        pg.screenshot(path=str(OUT / "02-recovery.png"), full_page=True)
        key = re.search(r"\d{4}-\d{4}-\d{4}", pg.content()).group(0)
        if pg.locator("form[action='/profiles/confirm'] input[name=recovery][type=text]").count(): pg.fill("input[name=recovery]", key)
        pg.click("form[action='/profiles/confirm'] button[type=submit]")
        pg.wait_for_timeout(500); pg.screenshot(path=str(OUT / "03-after-create.png"), full_page=True)
        print("after create ->", pg.url.replace(host.origin, ""))
        for s in SLOTS:
            pg.goto(host.origin + s); pg.wait_for_timeout(300)
            pg.screenshot(path=str(OUT / ("empty" + s.replace("/", "-") + ".png")), full_page=True)
        pg.goto(host.origin + "/"); pg.evaluate(POST, ["/demo", {}])
        texts = {}
        for s in TEXT:
            pg.goto(host.origin + s); pg.wait_for_timeout(250)
            texts[s] = pg.evaluate("() => (document.querySelector('main') || document.body).innerText.replace(/\\n+/g, ' | ').slice(0, 2500)")
        (OUT / "texts.json").write_text(json.dumps(texts, indent=1, ensure_ascii=False))
        # the Add sheet opened from Home, as a person does
        pg.goto(host.origin + "/home"); pg.wait_for_timeout(300)
        try:
            pg.locator(".phone-tabbar a, .phone-tabbar button").filter(has_text="Add").first.click(); pg.wait_for_timeout(700)
            pg.screenshot(path=str(OUT / "add-sheet-over-home.png"))
            print("add focus:", pg.evaluate("() => document.activeElement && (document.activeElement.id || document.activeElement.name || document.activeElement.tagName)"))
        except Exception as e: print("add sheet:", e)
        pg.goto(host.origin + "/home"); pg.evaluate(POST, ["/settings/locale", {"locale": "ar"}])
        for s in SLOTS:
            pg.goto(host.origin + s); pg.wait_for_timeout(300)
            pg.screenshot(path=str(OUT / ("ar" + s.replace("/", "-") + ".png")), full_page=True)
        b.close()
    host.stop() if hasattr(host, "stop") else None
