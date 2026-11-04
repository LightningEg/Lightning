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


@pytest.mark.parametrize("width", [320, 360])
def test_phone_picker_fits_and_choices_are_touchable(width):
    chromium = Path("/opt/pw-browsers/chromium")
    executable = str(chromium) if chromium.exists() else shutil.which("chromium")
    if not executable:
        pytest.skip("Chromium is not installed")
    root = Path(__file__).resolve().parents[1]
    static = root / "lightning/ui/static"
    source = (static / "app.js").read_text()
    picker = source.split("/* Our dropdown list.", 1)[1].split("// Privacy mode", 1)[0]
    picker = picker[picker.index("(() => {"):]
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable)
        page = browser.new_page(viewport={"width": width, "height": 800})
        page.set_content('<html class="phone"><body><main class="main"><select>' +
                         ''.join(f'<option value="{n}">Choice {n}</option>' for n in range(12)) +
                         '</select></main></body></html>')
        page.add_style_tag(content=(static / "style.css").read_text())
        page.add_style_tag(content=(static / "phone.css").read_text())
        page.add_script_tag(content="const t = s => s;\n" + picker)
        # A wide control must not force its fixed popup wider than the viewport.
        page.locator("select").evaluate("el => { el.style.setProperty('width', '500px', 'important'); el.style.setProperty('max-width', 'none', 'important'); }")
        page.locator("select").dispatch_event("mousedown")
        box = page.locator(".pick-panel").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width
        assert page.locator(".pick-option").first.bounding_box()["height"] >= 48
        page.locator(".pick-search").fill("Choice 11")
        assert page.locator(".pick-option:visible").count() == 1
        browser.close()


def test_phone_period_arrows_have_touch_targets():
    chromium = Path("/opt/pw-browsers/chromium")
    executable = str(chromium) if chromium.exists() else shutil.which("chromium")
    if not executable:
        pytest.skip("Chromium is not installed")
    static = Path(__file__).resolve().parents[1] / "lightning/ui/static"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable)
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.set_content('<html class="phone"><body><div class="phone-period-row">'
                         '<button class="period-step">‹</button><span>November</span>'
                         '<button class="period-step">›</button></div>'
                         '<a class="phone-reg-step">‹</a></body></html>')
        page.add_style_tag(content=(static / "style.css").read_text())
        page.add_style_tag(content=(static / "phone.css").read_text())
        for arrow in page.locator(".period-step, .phone-reg-step").all():
            box = arrow.bounding_box()
            assert box["width"] >= 48 and box["height"] >= 48
        browser.close()
