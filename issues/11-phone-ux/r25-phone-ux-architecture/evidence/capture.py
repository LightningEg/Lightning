"""Capture today's phone tabs on the sample household at 412 x 915 (the owner's phone width) and count, per page, how
long it is, how many figures and targets it holds, and how many times the same bills are counted.

    python issues/11-phone-ux/r25-phone-ux-architecture/evidence/capture.py <out-folder>   # from the repo root; needs Playwright
"""
import json, re, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
PAGES = ["/", "/?month=2026-10", "/budget", "/transactions", "/more", "/needs-you", "/plan", "/accounts", "/investments",
         "/financial-health", "/birdview/expenses", "/review", "/settings", "/plan/recurring", "/accounts/1"]
METRICS = """() => {
 const H = innerHeight, vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
 const targets = [...document.querySelectorAll('main a, main button, main summary, main input, main select')].filter(vis);
 const fig = /[−+-]?\\d{1,3}(,\\d{3})+(\\.\\d+)?|\\d+(\\.\\d+)?\\s?%/g;
 const main = document.querySelector('main'); const txt = main ? main.innerText : document.body.innerText;
 const heads = [...document.querySelectorAll('main h1, main h2, main h3')].filter(vis).map(h => h.innerText.trim().slice(0,40));
 return {screens: +(document.documentElement.scrollHeight / H).toFixed(1), figures: (txt.match(fig)||[]).length,
   targets: targets.length, headings: heads, first_screen: txt.slice(0, 600)};
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
        page = b.new_page(viewport={"width": 412, "height": 915}, device_scale_factor=1, is_mobile=True, has_touch=True)
        page.goto(host.launch_url); page.goto(host.origin + "/profiles/new")
        page.fill("input[name=name]", "Mohab")
        for f in ("password", "confirm"): page.fill(f"input[name={f}]", "a dummy phone password")
        page.fill("input[name=answer]", "Dummy")
        if page.locator("select[name=question]").count(): page.select_option("select[name=question]", index=1)
        elif page.locator("input[name=question]").count(): page.fill("input[name=question]", "Dummy question?")
        page.click("form[action='/profiles/new'] button[type=submit]")
        key = re.search(r"\d{4}-\d{4}-\d{4}", page.content()).group(0)
        if page.locator("form[action='/profiles/confirm'] input[name=recovery][type=text]").count(): page.fill("input[name=recovery]", key)
        page.click("form[action='/profiles/confirm'] button[type=submit]")
        page.goto(host.origin + "/")
        page.evaluate("""async () => { const t = document.querySelector('meta[name=lightning-session]').content;
            await fetch('/demo', {method: 'POST', body: new URLSearchParams({__session: t})}); }""")
        for path in PAGES:
            r = page.goto(host.origin + path)
            name = (path.strip("/").replace("/", "-").replace("?", "-").replace("=", "") or "overview")
            m = page.evaluate(METRICS); m["status"] = r.status if r else None
            res[path] = m
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
        b.close()
    host.stop()
(OUT / "metrics.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
for k, v in res.items():
    print(f"{k:22} screens={v['screens']:>4} figures={v['figures']:>3} targets={v['targets']:>3} heads={v['headings'][:8]}")
