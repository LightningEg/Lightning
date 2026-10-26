"""Capture real PC and phone screens in each bundled theme, for theme review (theme-kit/README.md).
Needs Playwright, Chromium and sqlcipher3. PC uses Mohab's sample year; the phone uses a dummy profile.

    python tools/theme_shots.py OUT [--themes id,id] [--only pc|phone] [--ar] [--motion]

Writes OUT/<theme>/<device>-<screen>.png. --motion leaves animation running (default: frozen, reduced motion).
"""
from __future__ import annotations

import json
import os
import re
import shutil
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
REGISTRY = json.loads((ROOT / "lightning/ui/static/themes.generated.json").read_text())
THEMES = ARGS[ARGS.index("--themes") + 1].split(",") if "--themes" in ARGS else [t["id"] for t in REGISTRY]
ONLY = ARGS[ARGS.index("--only") + 1] if "--only" in ARGS else ""
os.environ.update(LIGHTNING_TODAY="2026-10-04", LIGHTNING_PRICES_OFFLINE="1", LIGHTNING_THEME_REVIEW="1")  # paid themes too

PC = {"overview": "/?period=ytd", "transactions": "/transactions", "budget": "/budget?period=month&month=2026-10",
      "investments": "/investments?period=ytd", "accounts": "/accounts", "settings": "/settings"}
PHONE = {"overview": "/", "transactions": "/transactions", "budget": "/budget", "investments": "/investments",
         "accounts": "/accounts", "settings": "/settings"}
CHROMIUM = Path("/opt/pw-browsers/chromium")
WEAR = "id => { localStorage.setItem('lightning_theme', id); }"


def browser(p):
    return p.chromium.launch(executable_path=str(CHROMIUM) if CHROMIUM.exists() else shutil.which("chromium"))


def wear(page, theme):
    # The profile meta wins over storage; set it the way Settings does, then reload so it paints before content.
    page.evaluate("id => window.LightningTheme.set(id)", theme)
    page.wait_for_timeout(250)


def arabic(page, origin):
    """--ar: switch the profile to Arabic through Settings, the way a person does, so every screen is right to left."""
    page.goto(origin + "/settings")
    page.evaluate("""async () => { const body = new URLSearchParams({locale: 'ar'});
        const s = document.querySelector('meta[name=lightning-session]'); if (s) body.set('__session', s.content);
        const f = document.querySelector('form[action="/settings/locale"] input[name=__session]'); if (f && f.value) body.set('__session', f.value);
        await fetch('/settings/locale', {method: 'POST', body}); }""")
    assert page.goto(origin + "/settings") and page.evaluate("document.documentElement.dir") == "rtl", "Arabic did not take"


def shoot(page, origin, screens, prefix, theme):
    folder = OUT / theme
    folder.mkdir(parents=True, exist_ok=True)
    wear(page, theme)
    for name, path in screens.items():
        page.goto(origin + path)
        page.wait_for_timeout(300)
        page.screenshot(path=str(folder / f"{prefix}-{name}.png"))


def pc():
    from playwright.sync_api import sync_playwright
    server = subprocess.Popen([sys.executable, "-m", "lightning", "--sample", "--no-browser", "--port", "8768"],
                              cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(240):
            try:
                if urlopen("http://127.0.0.1:8768/__health", timeout=1).read(32) == b"lightning-ok":
                    break
            except OSError:
                time.sleep(.5)
        with sync_playwright() as p:
            b = browser(p)
            page = b.new_page(viewport={"width": 1440, "height": 900}, reduced_motion=None if "--motion" in ARGS else "reduce")
            page.goto("http://127.0.0.1:8768/")
            if "--ar" in ARGS:
                arabic(page, "http://127.0.0.1:8768")
            for theme in THEMES:
                shoot(page, "http://127.0.0.1:8768", PC, "pc", theme)
            b.close()
    finally:
        server.terminate()


def phone():
    from playwright.sync_api import sync_playwright
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Host
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        host = Host(lambda c: profile_app(c, root / "docs", devices=Devices(root / "app", port=0), phone=True)).start()
        try:
            with sync_playwright() as p:
                b = browser(p)
                page = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                                  has_touch=True, reduced_motion=None if "--motion" in ARGS else "reduce")
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
                page.click("button[type=submit]")
                key = re.search(r"\d{4}-\d{4}-\d{4}", page.content()).group(0)
                if page.locator("form[action='/profiles/confirm'] input[name=recovery][type=text]").count():
                    page.fill("input[name=recovery]", key)
                page.click("form[action='/profiles/confirm'] button[type=submit]")
                page.goto(host.origin + "/")
                page.evaluate("""async () => { const t = document.querySelector('meta[name=lightning-session]').content;
                    await fetch('/demo', {method: 'POST', body: new URLSearchParams({__session: t})}); }""")
                if "--ar" in ARGS:
                    arabic(page, host.origin)
                for theme in THEMES:
                    shoot(page, host.origin, PHONE, "phone", theme)
                b.close()
        finally:
            host.stop()


if __name__ == "__main__":
    if OUT is None:
        sys.exit(__doc__)
    if ONLY != "phone":
        pc()
    if ONLY != "pc":
        phone()
