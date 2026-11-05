import json,tempfile
from pathlib import Path
from capture import login,METRICS
from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Host
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as td:
    root=Path(td);host=Host(lambda cfg:profile_app(cfg,root/'docs',devices=Devices(root/'app',port=0))).start()
    try:
        with sync_playwright() as pw:
            b=pw.chromium.launch(executable_path='/usr/bin/chromium');p=b.new_page(viewport={'width':1366,'height':768});login(p,host)
            p.goto(host.origin+'/plan/reserves');p.locator('.refill-prompt button').click();p.wait_for_load_state('networkidle')
            p.goto(host.origin+'/plan');p.screenshot(path=str(Path(__file__).resolve().parent / 'details/pc-refill-baseline.png'),full_page=True)
            Path(str(Path(__file__).resolve().parent / 'details/refill-baseline.json')).write_text(json.dumps(p.evaluate(METRICS),indent=2));b.close()
    finally:host.stop()
