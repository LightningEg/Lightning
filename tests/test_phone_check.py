"""The phone audit must see clipped content while ignoring intentionally concealed controls."""
import shutil
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright
from tools.phone_check import CLIPPED


def test_clipped_content_and_concealed_controls():
    chromium = Path("/opt/pw-browsers/chromium")
    executable = str(chromium) if chromium.exists() else shutil.which("chromium")
    if not executable:
        pytest.skip("Chromium is not installed")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable)
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.set_content('''<style>body { margin: 0 } .frame { width: 320px; overflow-x: hidden }
          .beyond { position: relative; left: 300px; width: 80px }
          .off { position: absolute; left: 400px; width: 80px; overflow: hidden }
          .scroll { width: 320px; overflow-x: auto } .wide { width: 500px }</style>
          <div class="frame"><button class="beyond">visible clipping</button>
          <details><summary>closed</summary><button class="beyond">closed detail</button></details>
          <div class="off"><button>off canvas</button></div></div>
          <div class="scroll"><div class="wide"><button class="beyond">scrollable</button></div></div>''')
        assert [entry["text"] for entry in page.evaluate(CLIPPED)] == ["visible clipping"]
        browser.close()
