import os
import sys, shutil
from pathlib import Path
from playwright.sync_api import sync_playwright
HERE = Path.cwd()  # the scratch folder serve.py wrote state.json in (r29 evidence)
origin = (HERE / "state.json.origin").read_text()
def post(page, path, **data):
    page.evaluate("""async ([p, d]) => { const t = document.querySelector('meta[name=lightning-session]').content;
        await fetch(p, {method: 'POST', body: new URLSearchParams({__session: t, ...d})}); }""", [path, data])
def touch(cdp, kind, x, y):
    cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [] if kind == "touchEnd" else [{"x": x, "y": y}]})
def swipe(page, cdp, x0, y, x1, steps=12):
    touch(cdp, "touchStart", x0, y)
    for i in range(1, steps + 1):
        touch(cdp, "touchMove", x0 + (x1 - x0) * i / steps, y); page.wait_for_timeout(16)
    touch(cdp, "touchEnd", x1, y)
def tap(page, cdp, sel):
    box = page.locator(sel).first.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    touch(cdp, "touchStart", x, y); page.wait_for_timeout(60); touch(cdp, "touchEnd", x, y)
    page.mouse.click(x, y)
name, theme, loc = sys.argv[1], sys.argv[2], sys.argv[3]
vd = HERE / "video" / name
shutil.rmtree(vd, ignore_errors=True)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
    # set prefs without recording
    c0 = b.new_context(storage_state=str(HERE / "state.json")); pg0 = c0.new_page(); pg0.goto(origin + "/home")
    post(pg0, "/settings/theme", theme=theme); post(pg0, "/settings/locale", locale=loc); c0.close()
    ctx = b.new_context(storage_state=str(HERE / "state.json"), viewport={"width": 412, "height": 892}, device_scale_factor=1,
                        is_mobile=True, has_touch=True)
    page = ctx.new_page(); cdp = ctx.new_cdp_session(page)
    import base64, time
    vd.mkdir(parents=True, exist_ok=True); frames = []
    def on_frame(ev):
        n = len(frames); (vd / f"f{n:05d}.jpg").write_bytes(base64.b64decode(ev["data"]))
        frames.append(ev["metadata"]["timestamp"])
        try: cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        except Exception: pass
    cdp.on("Page.screencastFrame", on_frame)
    cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 85, "everyNthFrame": 1})
    page.goto(origin + "/home"); page.wait_for_timeout(2500)
    if name.startswith("flow"):
        page.click(".phone-home-hero"); page.wait_for_timeout(1500)          # Safe to spend sheet
        page.click("[data-sheet-close]"); page.wait_for_timeout(800)
        for lab in ("/budget", "/activity", "/money", "/"):
            page.click(f".phone-tabbar a[href='{lab}']"); page.wait_for_timeout(1300)
        page.click(".phone-tabbar a[href='/activity']"); page.wait_for_timeout(1200)
        row = page.locator(".phone-txn").nth(0).bounding_box()
        y = row["y"] + row["height"] / 2
        a, z = (380, 120) if loc == "en" else (40, 300)
        swipe(page, cdp, a, y, z); page.wait_for_timeout(1500)   # reveal actions
        page.mouse.click(206, 120); page.wait_for_timeout(800)
        page.click(".phone-tabbar a[href*='add-transaction']"); page.wait_for_timeout(1300)
        page.locator("#popup-amount").first.click()
        page.keyboard.type("250", delay=180); page.wait_for_timeout(800)
        pass
        page.wait_for_timeout(1500)
    else:
        page.wait_for_timeout(4000)
        page.click(".phone-tabbar a[href='/money']"); page.wait_for_timeout(4000)
        page.mouse.wheel(0, 400); page.wait_for_timeout(1500)
    cdp.send("Page.stopScreencast"); page.wait_for_timeout(300)
    lines = []
    for i, t in enumerate(frames):
        d = (frames[i + 1] - t) if i + 1 < len(frames) else 0.5
        lines.append(f"file 'f{i:05d}.jpg'\nduration {max(d, 0.001):.4f}")
    lines.append(f"file 'f{len(frames)-1:05d}.jpg'")
    (vd / "list.txt").write_text("\n".join(lines))
    page.close(); ctx.close()
    c0 = b.new_context(storage_state=str(HERE / "state.json")); pg0 = c0.new_page(); pg0.goto(origin + "/home")
    post(pg0, "/settings/theme", theme="lightning-default"); post(pg0, "/settings/locale", locale="en"); c0.close()
    b.close()
import subprocess
subprocess.run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",str(vd/"list.txt"),"-vf","fps=30,scale=412:-2,format=yuv420p","-c:v","libx264","-crf","26","-movflags","+faststart",str(vd.parent/f"{name}.mp4")],check=True)
shutil.rmtree(vd)
print("ok", name)
