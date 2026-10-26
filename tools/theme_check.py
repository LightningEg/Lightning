"""Prove a theme moves nothing and costs no frames, against Lightning default (guideline/themes.md sections 5 and 6).
Needs Playwright and Chromium. Uses Mohab's sample year on the PC layout.

    python tools/theme_check.py --themes id[,id]

Geometry: every visible element's box on the six roster screens, theme against default; any difference fails.
Frames: 240 animation frames with motion on (Overview and Budget); mean, 95th percentile and frames over 34 ms.
Headless desktop Chromium is a floor, not a phone: native devices still need their own look.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
ARGS = sys.argv[1:]
if "--themes" not in ARGS:
    sys.exit(__doc__)
THEMES = ARGS[ARGS.index("--themes") + 1].split(",")
os.environ.update(LIGHTNING_TODAY="2026-10-04", LIGHTNING_PRICES_OFFLINE="1", LIGHTNING_THEME_REVIEW="1")
PORT = 8772
SCREENS = {"overview": "/?period=ytd", "transactions": "/transactions", "budget": "/budget?period=month&month=2026-10",
           "investments": "/investments?period=ytd", "accounts": "/accounts", "settings": "/settings"}
BOXES = """() => [...document.querySelectorAll('body *')].filter(e => e.getClientRects().length).map(e => {
  const r = e.getBoundingClientRect();
  return [e.tagName, typeof e.className === 'string' ? e.className : '', ...[r.x, r.y, r.width, r.height].map(Math.round)].join(' ');
})"""
FRAMES = """() => new Promise(done => { const t = []; let last = performance.now();
  function frame(now) { t.push(now - last); last = now;
    if (t.length < 240) return requestAnimationFrame(frame);
    t.sort((a, b) => a - b);
    done([t.reduce((a, b) => a + b) / t.length, t[Math.floor(t.length * .95)], t.filter(x => x > 34).length]); }
  requestAnimationFrame(frame); })"""


def main() -> int:
    from playwright.sync_api import sync_playwright
    server = subprocess.Popen([sys.executable, "-m", "lightning", "--sample", "--no-browser", "--port", str(PORT)],
                              cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    origin, failed = f"http://127.0.0.1:{PORT}", 0
    try:
        for _ in range(240):
            try:
                if urlopen(origin + "/__health", timeout=1).read(32) == b"lightning-ok":
                    break
            except OSError:
                time.sleep(.5)
        chromium = Path("/opt/pw-browsers/chromium")
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(chromium) if chromium.exists() else shutil.which("chromium"))
            still = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
            moving = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="no-preference")
            for page in (still, moving):
                page.goto(origin + "/")

            def boxes(theme):
                still.evaluate("id => window.LightningTheme.set(id)", theme)
                result = {}
                for name, path in SCREENS.items():
                    still.goto(origin + path)
                    still.wait_for_timeout(300)
                    result[name] = still.evaluate(BOXES)
                return result
            default = boxes("lightning-default")
            for theme in THEMES:
                for name, mine in boxes(theme).items():
                    moved = [pair for pair in zip(default[name], mine) if pair[0] != pair[1]]
                    moved += [None] * abs(len(default[name]) - len(mine))
                    failed += bool(moved)
                    print(f"{theme} {name}: {len(mine)} elements, {len(moved)} moved" + (f" (first: {moved[0]})" if moved else ""))
                moving.evaluate("id => window.LightningTheme.set(id)", theme)
                for name in ("overview", "budget"):
                    moving.goto(origin + SCREENS[name])
                    moving.wait_for_timeout(1200)
                    mean, p95, long = moving.evaluate(FRAMES)
                    failed += long > 2
                    print(f"{theme} {name} frames: mean {mean:.1f} ms, p95 {p95:.1f} ms, {long} over 34 ms")
            browser.close()
    finally:
        server.terminate()
    print("passed" if not failed else f"{failed} problem(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
