"""Does each declared theme motion actually paint? Run from the repo root:

    python reports/r21-dendera-premium-audit/evidence/motion_probe.py [theme,theme]

Starts Mohab's sample year (dummy data), wears each theme with motion on, and prints per theme:
thread_frames (distinct header-seam frames over 8 s; 1 = still), hero_edge_moves, hover_light, press_sheen
(background position of a focused primary button mid-transition; "0px 0px" = no sheen).
Needs Playwright with Chromium and the app's requirements.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[3]
THEMES = sys.argv[1].split(",") if len(sys.argv) > 1 else ["dendera", "papyrus"]
ORIGIN = "http://127.0.0.1:8771"
CHROMIUM = Path("/opt/pw-browsers/chromium")


def digest(data):
    return hashlib.md5(data).hexdigest()[:8]


def main():
    from playwright.sync_api import sync_playwright
    env = {**os.environ, "LIGHTNING_TODAY": "2026-10-04", "LIGHTNING_PRICES_OFFLINE": "1", "LIGHTNING_THEME_REVIEW": "1"}
    server = subprocess.Popen([sys.executable, "-m", "lightning", "--sample", "--no-browser", "--port", "8771"], cwd=ROOT,
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    result = {}
    try:
        for _ in range(240):
            try:
                if urlopen(ORIGIN + "/__health", timeout=1).read(32) == b"lightning-ok":
                    break
            except OSError:
                time.sleep(.5)
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(CHROMIUM) if CHROMIUM.exists() else None)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            for theme in THEMES:
                page.goto(ORIGIN + "/")
                page.evaluate("id => window.LightningTheme.set(id)", theme)
                page.wait_for_timeout(1500)
                page.goto(ORIGIN + "/?period=ytd")
                page.wait_for_timeout(500)
                row = {}
                bar = page.evaluate("(() => { const r = document.querySelector('.main > .topbar').getBoundingClientRect();"
                                    " return [r.x, r.bottom - 3, r.width]; })()")
                frames = set()
                for _ in range(8):
                    frames.add(digest(page.screenshot(clip=dict(x=bar[0], y=bar[1], width=bar[2], height=6))))
                    page.wait_for_timeout(1000)
                row["thread_frames"] = len(frames)
                lead = page.locator(".main .lead-card").first.bounding_box()
                before = page.screenshot(clip=lead)
                page.wait_for_timeout(3000)
                row["hero_edge_moves"] = digest(before) != digest(page.screenshot(clip=lead))
                card = page.locator(".kpi-card").first
                box = card.bounding_box()
                page.mouse.move(5, 5)
                page.wait_for_timeout(300)
                before = page.screenshot(clip=box)
                page.mouse.move(box["x"] + 60, box["y"] + 50)
                page.wait_for_timeout(300)
                row["hover_light"] = digest(before) != digest(page.screenshot(clip=box))
                page.goto(ORIGIN + "/transactions")
                page.wait_for_timeout(500)
                button = page.locator(".btn.primary:visible").first
                button.evaluate("e => e.focus({focusVisible: true})")
                page.keyboard.press("Shift")
                page.wait_for_timeout(350)
                row["press_sheen"] = button.evaluate("e => getComputedStyle(e).backgroundPosition")
                result[theme] = row
            browser.close()
    finally:
        server.terminate()
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
