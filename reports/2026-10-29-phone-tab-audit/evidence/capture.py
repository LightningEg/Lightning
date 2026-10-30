"""Capture each phone tab at 360 x 800 on the sample household and print how long and busy each page is.

    python reports/2026-10-29-phone-tab-audit/evidence/capture.py <out-folder>     # from the repo root; needs Playwright
"""
import json, re, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
PAGES = ["/", "/budget", "/transactions", "/more", "/plan", "/plan/recurring", "/plan/loans", "/plan/reserves",
         "/investments", "/investments/planner", "/investments/prices", "/accounts", "/accounts/1", "/financial-health",
         "/birdview/expenses", "/settings", "/review", "/zakat", "/money-from-others", "/categories", "/sms"]
METRICS = """() => {
 const H = innerHeight, vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
 const all = [...document.querySelectorAll('.phone-content *, main *')].filter(vis);
 const targets = [...document.querySelectorAll('main a, main button, main summary, main input, main select')].filter(vis);
 const fig = /[−+-]?\\d{1,3}(,\\d{3})+(\\.\\d+)?|\\d+(\\.\\d+)?\\s?%/g;
 const main = document.querySelector('main');
 const txt = main ? main.innerText : document.body.innerText;
 const cards = [...document.querySelectorAll('main [class*=card]')].filter(vis).length;
 const small = targets.filter(t => { const r = t.getBoundingClientRect(); return r.height < 40; }).length;
 const fold = targets.filter(t => t.getBoundingClientRect().top < H - 80).map(t => (t.innerText||t.value||t.getAttribute('aria-label')||'').trim().slice(0,30));
 const heads = [...document.querySelectorAll('main h1, main h2, main h3, main summary')].filter(vis).map(h => h.innerText.trim().slice(0,40));
 return {height: document.documentElement.scrollHeight, screens: +(document.documentElement.scrollHeight / H).toFixed(1),
   figures: (txt.match(fig)||[]).length, words: txt.split(/\\s+/).length, targets: targets.length, small_targets: small,
   cards, headings: heads, fold_targets: fold, fold_text: txt.slice(0, 700)};
}"""
from playwright.sync_api import sync_playwright
from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Host
res = {}
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    host = Host(lambda c: profile_app(c, root / "docs", devices=Devices(root / "app", port=0), phone=True)).start()
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else shutil.which("chromium"))
        page = b.new_page(viewport={"width": 360, "height": 800}, device_scale_factor=1, is_mobile=True, has_touch=True)
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
        for path in PAGES:
            r = page.goto(host.origin + path)
            name = path.strip("/").replace("/", "-") or "overview"
            m = page.evaluate(METRICS); m["status"] = r.status if r else None
            res[path] = m
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            page.screenshot(path=str(OUT / f"{name}-fold.png"))
        # Add sheet
        page.goto(host.origin + "/")
        page.click(".phone-add"); page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "add-sheet.png"))
        res["add"] = {"fold_text": page.locator("#app-popup").inner_text()[:900]}
        # pick first option if present
        b.close()
    host.stop()
(OUT / "metrics.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
for k, v in res.items():
    if "screens" in v: print(f"{k:24} screens={v['screens']:>4} figures={v['figures']:>3} targets={v['targets']:>3} small={v['small_targets']:>3} cards={v['cards']:>3} words={v['words']}")
