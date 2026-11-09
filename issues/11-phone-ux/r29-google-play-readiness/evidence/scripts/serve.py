"""r29 evidence: start the phone app on a throwaway profile with the demo household and keep it running.

Run from an empty scratch folder (it writes state.json and state.json.origin there), from the repo root path:
    python <repo>/issues/11-phone-ux/r29-google-play-readiness/evidence/scripts/serve.py state.json &
    python <repo>/.../scripts/shots.py tabs      # or: themes
    python <repo>/.../scripts/video.py flow-en lightning-default en   # needs ffmpeg; writes video/<name>.mp4
"""
import os, re, sys, tempfile, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[5]))  # the repository root
os.environ["LIGHTNING_THEME_REVIEW"] = "1"
from playwright.sync_api import sync_playwright
from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Host
root = Path(tempfile.mkdtemp())
host = Host(lambda c: profile_app(c, root / "docs", devices=Devices(root / "app", port=0), phone=True)).start()
state = Path(sys.argv[1])
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
    ctx = b.new_context(viewport={"width": 412, "height": 892}, device_scale_factor=2, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.goto(host.launch_url)
    page.goto(host.origin + "/profiles/new")
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
    ctx.storage_state(path=str(state))
    b.close()
Path(str(state) + ".origin").write_text(host.origin)
print("READY", host.origin, flush=True)
while True: time.sleep(60)
