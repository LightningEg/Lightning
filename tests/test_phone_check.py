"""The phone audit must see clipped content while ignoring intentionally concealed controls."""
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright
from tools.phone_check import CLIPPED
from tests.browser_support import require_chromium


def test_clipped_content_and_concealed_controls():
    executable = require_chromium()
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
    executable = require_chromium()
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
    executable = require_chromium()
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


def test_phone_chart_time_axes_show_at_most_three_labels():
    executable = require_chromium()
    css = Path(__file__).resolve().parents[1] / "lightning/ui/static/phone.css"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable)
        page = browser.new_page(viewport={"width": 320, "height": 800})
        labels = ''.join(f'<span>{n}</span>' for n in range(7))
        page.set_content(f'<html class="phone"><body><div class="chart-x">{labels}</div>'
                         f'<div class="phone-invest-card has-7"><div class="chart-x">{labels}</div></div></body></html>')
        page.add_style_tag(content=css.read_text())
        charts = page.locator('.chart-x')
        assert charts.nth(0).locator('span:visible').count() == 2
        assert charts.nth(1).locator('span:visible').count() == 3
        browser.close()


def test_phone_fields_stay_readable_with_desktop_overrides():
    executable = require_chromium()
    static = Path(__file__).resolve().parents[1] / "lightning/ui/static"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable)
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.set_content('<html class="phone"><body><main class="main"><div class="cp-table">'
                         '<form class="counterparty-name-edit"><input name="name"></form></div>'
                         '<div class="phone-amount"><input name="amount"></div></main></body></html>')
        page.add_style_tag(content=(static / "style.css").read_text())
        page.add_style_tag(content=(static / "phone.css").read_text())
        assert page.locator('[name=name]').evaluate('e => getComputedStyle(e).fontSize') == '16px'
        assert page.locator('[name=amount]').evaluate('e => getComputedStyle(e).fontSize') == '24px'
        page.set_content('<html class="phone"><body><form class="gate-language"><select><option>English</option></select></form></body></html>')
        page.add_style_tag(content=(static / "profiles.css").read_text())
        assert page.locator('select').evaluate('e => getComputedStyle(e).fontSize') == '16px'
        browser.close()


def test_phone_focused_field_deepens_its_well():
    executable = require_chromium()
    static = Path(__file__).resolve().parents[1] / "lightning/ui/static"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable)
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.set_content('<html class="phone"><body><main class="main"><input></main></body></html>')
        page.add_style_tag(content=(static / "style.css").read_text())
        page.add_style_tag(content=(static / "phone.css").read_text())
        field = page.locator('input')
        before = field.evaluate('e => getComputedStyle(e).backgroundColor')
        field.focus()
        after = field.evaluate('e => getComputedStyle(e).backgroundColor')
        assert before != after and after != 'rgb(245, 239, 207)'
        assert field.evaluate('e => getComputedStyle(e).borderColor') == 'rgb(11, 138, 95)'
        browser.close()


def test_phone_loan_and_reserve_actions_have_touch_targets():
    executable = require_chromium()
    static = Path(__file__).resolve().parents[1] / "lightning/ui/static"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable)
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.set_content('<html class="phone"><body><main class="main"><article class="plan-loan">'
                         '<a class="quiet-link">Pay early</a><a class="btn small">1 due</a></article>'
                         '<details class="reserve-create"><summary>Add a reserve</summary></details>'
                         '<details class="chart-table"><summary>Show the numbers</summary></details>'
                         '<span class="phone-recurring-side"><a class="plan-status plan-status-due">1 due</a></span></main></body></html>')
        page.add_style_tag(content=(static / "style.css").read_text())
        page.add_style_tag(content=(static / "phone.css").read_text())
        for selector, minimum in ((".quiet-link", 44), (".btn.small", 48), (".reserve-create summary", 48), (".chart-table summary", 44), (".phone-recurring-side .plan-status-due", 48)):
            assert page.locator(selector).bounding_box()["height"] >= minimum
        assert page.locator(".phone-recurring-side .plan-status-due").bounding_box()["width"] >= 48
        browser.close()


@pytest.mark.parametrize("width", [320, 360])
def test_phone_planner_choices_fit_their_card(width):
    executable = require_chromium()
    static = Path(__file__).resolve().parents[1] / "lightning/ui/static"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable)
        page = browser.new_page(viewport={"width": width, "height": 800})
        page.set_content('<html class="phone"><body><main class="main"><form class="card planner-popup-form">'
                         '<fieldset class="planner-mode"><span class="planner-mode-seg">'
                         '<label><input type="radio" name="mode"><span>Spread across gaps</span></label>'
                         '<label><input type="radio" name="mode"><span>Biggest gaps first</span></label>'
                         '</span></fieldset></form></main></body></html>')
        page.add_style_tag(content=(static / "style.css").read_text())
        page.add_style_tag(content=(static / "phone.css").read_text())
        assert page.locator('.planner-mode-seg').evaluate(
            'e => [...e.querySelectorAll("label span")].every(s => s.scrollWidth <= s.clientWidth && s.getBoundingClientRect().right <= e.getBoundingClientRect().right + 0.5)')
        browser.close()
