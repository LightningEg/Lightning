"""Prove a theme moves nothing and costs no frames, against Lightning default (guideline/themes.md sections 5 and 6).
Needs Playwright and Chromium. Uses Mohab's sample year on the PC layout.

    python tools/theme_check.py --themes id[,id]

Geometry: every visible element's box on the six roster screens, theme against default; any difference fails.
Frames: 240 animation frames with motion on (Overview and Budget); mean, 95th percentile and frames over 34 ms.
Motion: each motion the theme declares must change pixels (thread, hero sheen, ambient glow, card hover, press sheen):
a motion whose paint the browser drops looks fine in every other check (Dendera audit, 2026-11-02).
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
# The Night version row in Settings is shown only for a theme that has one: content, not the theme's geometry.
BOXES = """() => { document.querySelectorAll('[data-theme-night]').forEach(row => { row.hidden = true; });
  return [...document.querySelectorAll('body *')].filter(e => e.getClientRects().length).map(e => {
  const r = e.getBoundingClientRect();
  return [e.tagName, typeof e.className === 'string' ? e.className : '', ...[r.x, r.y, r.width, r.height].map(Math.round)].join(' ');
}); }"""
FRAMES = """() => new Promise(done => { const t = []; let last = performance.now();
  function frame(now) { t.push(now - last); last = now;
    if (t.length < 240) return requestAnimationFrame(frame);
    t.sort((a, b) => a - b);
    done([t.reduce((a, b) => a + b) / t.length, t[Math.floor(t.length * .95)], t.filter(x => x > 34).length]); }
  requestAnimationFrame(frame); })"""


NIGHT = """async on => { const t = document.querySelector('meta[name=lightning-session]');
    const body = new URLSearchParams({on}); if (t) body.set('__session', t.content);
    await fetch('/settings/theme/night', {method: 'POST', body}); }"""


def wear(page, origin, theme):
    """Wear a theme the way Settings does and wait until a fresh page paints it. Setting it and navigating at once
    lost the save, so every page measured Lightning default (audit 2026-11-02). A night version is its day theme with
    Night chosen."""
    night = theme.endswith("-night")
    page.goto(origin + "/settings")
    page.evaluate("id => window.LightningTheme.set(id)", theme.removesuffix("-night") if night else theme)
    page.evaluate(NIGHT, "night" if night else "0")
    for _ in range(20):
        page.wait_for_timeout(250)
        page.reload()
        if page.evaluate("document.documentElement.dataset.theme") == theme:
            return
    raise SystemExit(f"{theme} did not take")


def motion_checks(page, origin, theme):
    """Each declared motion, and whether it painted: [(name, moved)]."""
    import hashlib
    shot = lambda box: hashlib.md5(page.screenshot(clip=box)).hexdigest()
    m = page.evaluate("id => (window.LIGHTNING_THEMES.find(t => t.id === id) || {}).materials || {}", theme)
    page.mouse.move(1, 1)
    page.goto(origin + SCREENS["overview"])
    page.wait_for_timeout(800)
    found = []
    def over_time(selector, name, pad=0, seconds=(1.6, 1.6, 1.6)):
        r = page.evaluate("s => { const b = document.querySelector(s).getBoundingClientRect(); return [b.x, b.y, b.width, b.height]; }", selector)
        box = dict(x=max(r[0] - pad, 0), y=max(r[1] - pad, 0), width=r[2] + 2 * pad, height=r[3] + 2 * pad)
        seen = {shot(box)}
        for wait in seconds:
            page.wait_for_timeout(int(wait * 1000))
            seen.add(shot(box))
        found.append((name, len(seen) > 1))
    if m.get("header-thread", "none") != "none":
        top = page.evaluate("(() => { const b = document.querySelector('.main > .topbar').getBoundingClientRect(); return [b.x, b.bottom, b.width]; })()")
        box = dict(x=top[0], y=top[1] - 3, width=top[2], height=6)
        seen = {shot(box)}
        for _ in range(4):
            page.wait_for_timeout(1500)
            seen.add(shot(box))
        found.append(("header thread", len(seen) > 1))
    if m.get("hero-sheen", "none") != "none":
        over_time(".main .lead-card", "hero sheen", pad=2)
    if m.get("ground-ambient", "none") != "none":
        found.append(("ambient", page.evaluate("getComputedStyle(document.documentElement, '::before').animationName") != "none"))
    if m.get("cards-hover", "none") != "none":
        card = page.locator(".main .kpi-card").first
        box = card.bounding_box()
        before = shot(box)
        page.mouse.move(box["x"] + 60, box["y"] + 50)
        page.wait_for_timeout(400)
        found.append(("card hover", shot(box) != before))
        page.mouse.move(1, 1)
    if m.get("controls-press", "none") != "none":
        page.goto(origin + "/transactions")
        page.wait_for_timeout(500)
        button = page.locator(".btn.primary:visible").first
        start = button.evaluate("e => getComputedStyle(e).backgroundPosition")
        button.evaluate("e => e.focus({focusVisible: true})")
        page.keyboard.press("Shift")
        page.wait_for_timeout(350)
        found.append(("press sheen", button.evaluate("e => getComputedStyle(e).backgroundPosition") != start))
        button.evaluate("e => e.blur()")
    return found


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
                wear(still, origin, theme)
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
                wear(moving, origin, theme)
                for name in ("overview", "budget"):
                    moving.goto(origin + SCREENS[name])
                    moving.wait_for_timeout(1200)
                    mean, p95, long = moving.evaluate(FRAMES)
                    failed += long > 2
                    print(f"{theme} {name} frames: mean {mean:.1f} ms, p95 {p95:.1f} ms, {long} over 34 ms")
                for name, moved in motion_checks(moving, origin, theme):
                    failed += not moved
                    print(f"{theme} motion {name}: {'paints' if moved else 'DOES NOT PAINT'}")
            browser.close()
    finally:
        server.terminate()
    print("passed" if not failed else f"{failed} problem(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
