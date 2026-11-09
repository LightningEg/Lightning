import os
import sys, json
from pathlib import Path
from playwright.sync_api import sync_playwright
HERE = Path.cwd()  # the scratch folder serve.py wrote state.json in (r29 evidence)
origin = (HERE / "state.json.origin").read_text()
TABS = [("home", "/home"), ("budget", "/budget"), ("add", "/accounts/add-transaction"), ("activity", "/activity"), ("money", "/money")]
def post(page, path, **data):
    page.evaluate("""async ([p, d]) => { const t = document.querySelector('meta[name=lightning-session]').content;
        await fetch(p, {method: 'POST', body: new URLSearchParams({__session: t, ...d})}); }""", [path, data])
mode = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
    ctx = b.new_context(storage_state=str(HERE / "state.json"), viewport={"width": 412, "height": 892}, device_scale_factor=2, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.goto(origin + "/home")
    out = HERE / "shots"; out.mkdir(exist_ok=True)
    if mode == "tabs":
        for loc in ("en", "ar"):
            post(page, "/settings/theme", theme="lightning-default")
            post(page, "/settings/locale", locale=loc)
            for name, path in TABS:
                page.goto(origin + path); page.wait_for_timeout(600)
                page.screenshot(path=str(out / f"{loc}-{name}.png"))
                page.screenshot(path=str(out / f"{loc}-{name}-full.png"), full_page=True)
                txt = page.evaluate("() => document.querySelector('main')?.innerText || document.body.innerText")
                (out / f"{loc}-{name}.txt").write_text(txt)
        post(page, "/settings/locale", locale="en")
    elif mode == "themes":
        for th in ["lightning-default","royal-obsidian-gold","cotton","nile","papyrus","dendera","dendera-night"]:
            post(page, "/settings/theme", theme=th)
            for name, path in [("home","/home"),("money","/money")]:
                page.goto(origin + path); page.wait_for_timeout(1500)
                worn = page.evaluate("() => document.documentElement.dataset.theme")
                print(th, name, worn)
                page.screenshot(path=str(out / f"theme-{th}-{name}.png"))
        post(page, "/settings/theme", theme="lightning-default")
    b.close()
