"""Capture the website's app screens from Mohab's sample year (skill: site-recapture). Needs Playwright,
Chromium and sqlcipher3 (the paired phone and PC run real encrypted profiles).

    python tools/site_shots.py OUT [--lang en|ar] [--today 2026-10-04] [--only pc|pair] [--expenses-month 2026-08]

pc   starts `python -m lightning --sample` on 8767 (prices offline, the date pinned), then saves the PC set:
     full windows 2000 x 1250 (1440 x 900 at 1.389x), b-* (the window less the sidebar, 1624 x 1250),
     a-* content crops 1800 x 1125 (sidebar hidden), section crops (a section header and its card, 13 px
     around), the rate crops a-kpis and a-sankey, the register with its picker open, and last the import review
     (it leaves a pending import). The Get set up card is dismissed first and the pointer parked, so no screen
     shows the card or a hover ring.
pair two real profiles in this process, a phone (360 x 760 at 2x) holding Mohab's year and a PC borrowing it:
     phone-overview, phone-plan, phone-account (scrolled so the + button sits between rows), then sync-pc and
     sync-phone. Arabic: both profiles in Arabic.
Files are WebP at quality 78, named as the website uses them; compare a new set with the old by eye first.
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ARGS = sys.argv[1:]
OUT = Path(ARGS[0]) if ARGS and not ARGS[0].startswith("--") else None
LANG = ARGS[ARGS.index("--lang") + 1] if "--lang" in ARGS else "en"
TODAY = ARGS[ARGS.index("--today") + 1] if "--today" in ARGS else "2026-10-04"
ONLY = ARGS[ARGS.index("--only") + 1] if "--only" in ARGS else ""
# Expense analysis shows the month that lights up its features in Mohab's year: August, with a 14,200 holiday payment
# (9.5 times the average), Entertainment far above its range and spending up 21%; September is flat.
EXPENSES_MONTH = ARGS[ARGS.index("--expenses-month") + 1] if "--expenses-month" in ARGS else "2026-08"
os.environ.update(LIGHTNING_TODAY=TODAY, LIGHTNING_PRICES_OFFLINE="1")  # before lightning reads them

BASE, SCALE = "http://127.0.0.1:8767", 2000 / 1440
HIDE = "#page-jump{display:none!important}"
NOSIDE = HIDE + ".side{display:none!important}.shell{grid-template-columns:1fr!important}"
CHROMIUM = "/opt/pw-browsers/chromium"


EXPENSES = f"/birdview/expenses?period=month&month={EXPENSES_MONTH}"
BUDGET = f"/budget?period=month&month={TODAY[:7]}"  # the month in progress: the pace chart tells the story, a year to date does not
FULL = {"overview": "/?period=ytd", "budget": BUDGET, "investments": "/investments?period=ytd", "expenses": EXPENSES,
        "plan": "/plan", "currencies": "/accounts/currencies?period=ytd", "import-upload": "/accounts/1/import",
        "account-usd": "/accounts/7"}  # the dollar brokerage: its balance by asset class
SIDELESS = ("overview", "budget", "investments", "expenses", "plan", "currencies")  # also saved as b-*
CROPS = {"a-overview": "/?period=ytd", "a-budget": BUDGET, "a-investments": "/investments?period=ytd",
         "a-expenses": EXPENSES, "a-plan": "/plan", "a-currencies": "/accounts/currencies?period=ytd"}
SECTIONS = {"a-kpis": ("/?period=ytd", "section.stat-tiles"),  # the rates are below the fold since 3W
            "a-sankey": ("/?period=ytd", "article.overview-sankey-card"),
            "a-forecast-ahead": ("/plan", "#plan-forecast"), "a-suggested": ("/plan/recurring", "#recurring-suggest"),
            "a-usd": ("/accounts/currencies?period=ytd", "#currency-USD")}
STATEMENT = "Date,Counterparty,Amount,Notes\n2026-10-02,Talabat Egypt,-385,Friday dinner\n2026-10-03,Uber,-142,\n" \
            "2026-10-03,Carrefour,-1860,\n2026-10-04,Vodafone,-350,\n2026-10-04,Seoudi,-640,\n"


def save(png: bytes, name: str, trim: int = 0) -> None:
    """WebP, encoded once from the PNG; trim > 0 cuts that many pixels from the left, < 0 from the right."""
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGB")
    if trim:
        im = im.crop((trim, 0, im.width, im.height)) if trim > 0 else im.crop((0, 0, im.width + trim, im.height))
    im.save(OUT / f"{name}.webp", "WEBP", quality=78, method=6)
    print(f"{name}.webp {im.width} x {im.height}")


def browser(p):
    args = ["--lang=ar"] if LANG == "ar" else []
    return p.chromium.launch(executable_path=CHROMIUM if Path(CHROMIUM).exists() else None, args=args)


def page(b, width, height, scale, **extra):
    return b.new_page(viewport={"width": width, "height": height}, device_scale_factor=scale,
                      **({"locale": "ar-EG"} if LANG == "ar" else {}), **extra)


def show(pg, url, css=HIDE, wait=500):
    pg.goto(url, wait_until="networkidle")
    pg.add_style_tag(content=css)
    pg.evaluate("() => document.querySelectorAll('.flash:not(.device-line)').forEach(f => f.remove())")  # toasts leave by themselves
    pg.wait_for_timeout(wait)


def section_crop(pg, selector, name):
    """A section: its header (when the selector names one) and the card under it, 13 px around."""
    box = pg.evaluate("""(sel) => { const el = document.querySelector(sel);
        const head = el.matches('header') ? el : el.closest('header');
        let card = head ? head.nextElementSibling : el;
        el.scrollIntoView({block: 'start'}); window.scrollBy(0, -40);
        const a = (head || card).getBoundingClientRect(), b = card.getBoundingClientRect();
        return {x: Math.min(a.left, b.left), y: a.top, w: Math.max(a.right, b.right) - Math.min(a.left, b.left), h: b.bottom - a.top}; }""",
                      selector)
    pg.wait_for_timeout(300)
    save(pg.screenshot(clip={"x": box["x"] - 13, "y": box["y"] - 13, "width": box["w"] + 26, "height": box["h"] + 26}), name)


def pc_set() -> None:
    from playwright.sync_api import sync_playwright
    server = subprocess.Popen([sys.executable, "-m", "lightning", "--sample", "--no-browser"], cwd=ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                if urlopen(BASE + "/__health", timeout=1).read(32) == b"lightning-ok":
                    break
            except OSError:
                time.sleep(1)
        else:
            raise SystemExit("the sample app did not start on 8767 (is another Lightning using it?)")
        if LANG == "ar":
            urlopen(BASE + "/settings/locale", data=b"locale=ar", timeout=10).read()
        with sync_playwright() as p:
            b = browser(p)
            full = page(b, 1440, 900, SCALE)
            full.goto(BASE + "/?period=ytd")  # the sample opens with Get set up above Net worth: dismiss it once
            dismiss = full.locator('form[action="/setup/guide"] button')
            if dismiss.count():
                dismiss.first.click()
                full.wait_for_load_state("networkidle")
            full.mouse.move(0, 0)  # a parked pointer leaves a hover ring on the next screen
            for name, url in FULL.items():
                show(full, BASE + url)
                png = full.screenshot()
                save(png, name)
                if name in SIDELESS:
                    save(png, "b-" + name, 376 if LANG == "en" else -376)  # the sidebar is on the right in Arabic
            crop = page(b, 1296, 810, SCALE)
            for name, url in CROPS.items():
                show(crop, BASE + url, NOSIDE)
                save(crop.screenshot(), name)
            show(crop, BASE + "/plan", NOSIDE)
            crop.evaluate("() => { document.getElementById('plan-build').scrollIntoView({block: 'start'}); window.scrollBy(0, -66); }")
            crop.wait_for_timeout(400)
            save(crop.screenshot(), "a-plan-working")
            show(full, BASE + "/investments?period=ytd", NOSIDE)  # the dollar fund's row, its gain split into price and FX parts;
            full.evaluate("() => document.querySelector('a.holding-link[href*=\"/holding/15?\"]').scrollIntoView({block: 'center'})")
            full.wait_for_timeout(400)  # the whole window, so the table's last columns fit (2000 x 1250)
            save(full.screenshot(), "a-holdings-usd")
            tall = page(b, 1296, 1100, SCALE)
            for name, (url, selector) in SECTIONS.items():
                show(tall, BASE + url, NOSIDE)
                section_crop(tall, selector, name)
            show(full, BASE + "/accounts/1")
            full.fill("input[form=f-new][name=counterparty]", "Tal")
            full.wait_for_timeout(900)
            save(full.screenshot(), "register")
            with tempfile.TemporaryDirectory() as folder:  # last: the review leaves a pending import behind
                csv = Path(folder) / "stmt.csv"
                csv.write_text(STATEMENT, encoding="utf-8")
                show(full, BASE + "/accounts/1/import")
                full.set_input_files("input[type=file][name=file]", str(csv))
                full.locator("form[action='/accounts/1/import'] button.primary").first.click()
                full.wait_for_load_state("networkidle")
                show(full, full.url)
                save(full.screenshot(), "import-review")
            b.close()
    finally:
        server.terminate()
        server.wait(10)


def create_profile(pg, origin: str, password: str) -> None:
    pg.goto(origin + "/profiles/new")
    pg.fill("input[name=name]", "Mohab")
    for field in ("password", "confirm"):
        pg.fill(f"input[name={field}]", password)
    pg.fill("input[name=question]", "Dummy question?")
    pg.fill("input[name=answer]", "Dummy")
    pg.click("form[action='/profiles/new'] button[type=submit]")
    pg.click("form[action='/profiles/confirm'] button[type=submit]")
    if "Welcome" not in pg.title() and pg.url.endswith("/profiles/confirm"):
        raise SystemExit("profile not created: is sqlcipher3 installed?")


def post(pg, path: str, **fields) -> None:
    pg.evaluate("""async ([path, fields]) => { const t = document.querySelector('meta[name=lightning-session]').content;
        await fetch(path, {method: 'POST', body: new URLSearchParams({__session: t, ...fields})}); }""", [path, fields])


def pair_set() -> None:
    from playwright.sync_api import sync_playwright
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Host
    password = "a dummy phone password"
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        phone_devices = Devices(root / "phone-app", port=0, host="127.0.0.1")
        pc_devices = Devices(root / "pc-app", port=0, host="127.0.0.1")
        phone = Host(lambda c: profile_app(c, root / "phone-docs", devices=phone_devices, phone=True)).start()
        pc = Host(lambda c: profile_app(c, root / "pc-docs", devices=pc_devices)).start()
        try:
            with sync_playwright() as p:
                b = browser(p)
                ph = page(b, 360, 760, 2, is_mobile=True, has_touch=True)
                ph.goto(phone.launch_url)
                create_profile(ph, phone.origin, password)
                ph.goto(phone.origin + "/")
                post(ph, "/sample/mohab-2026")
                ph.goto(phone.origin + "/")
                post(ph, "/setup/guide", action="dismiss")
                if LANG == "ar":
                    ph.goto(phone.origin + "/")
                    post(ph, "/settings/locale", locale="ar")
                for name, path in (("phone-overview", "/?period=ytd"), ("phone-plan", "/plan"), ("phone-account", "/accounts/1")):
                    show(ph, phone.origin + path, wait=700)
                    lift = {"phone-plan": 200, "phone-account": 88 if LANG == "ar" else 60}.get(name)
                    if lift:  # the + button would cover a figure (3Z)
                        ph.evaluate("(y) => window.scrollBy(0, y)", lift)
                        ph.wait_for_timeout(400)
                    save(ph.screenshot(), name)
                ph.goto(phone.origin + "/profiles/devices")
                ph.fill("input[name=phone_name]", "Mohab’s phone")
                ph.locator("form[action='/profiles/devices/pair'] button[type=submit]").click()
                ph.goto(phone.origin + "/profiles/devices")
                code = re.search(r"([A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4})", ph.content()).group(1)
                pcp = page(b, 1440, 900, SCALE)
                pcp.goto(pc.launch_url)
                pcp.goto(pc.origin + "/profiles/connect")
                pcp.fill("input[name=address]", f"127.0.0.1:{phone_devices.server.port}")
                pcp.fill("input[name=code]", code)
                pcp.fill("input[name=pc_name]", "Office PC")
                pcp.locator("form[action='/profiles/connect'] button[type=submit]").click()
                pcp.goto(pc.origin + "/profiles")
                profile_id = re.search(r"/profiles/borrowed\?id=([0-9a-f-]{36})", pcp.content()).group(1)
                pcp.goto(pc.origin + f"/profiles/borrowed?id={profile_id}")
                pcp.fill("input[name=password]", password)
                pcp.locator("form[action='/profiles/borrowed'] button[type=submit]").click()
                show(pcp, pc.origin + "/?period=ytd", wait=800)  # within 5 s: the device line is a toast today
                save(pcp.screenshot(), "sync-pc")
                show(ph, phone.origin + "/?period=ytd", wait=800)
                save(ph.screenshot(), "sync-phone")
                b.close()
        finally:
            pc.stop()
            phone.stop()


if __name__ == "__main__":
    if OUT is None:
        raise SystemExit(__doc__)
    OUT.mkdir(parents=True, exist_ok=True)
    if ONLY in ("", "pc"):
        pc_set()
    if ONLY in ("", "pair"):
        pair_set()
