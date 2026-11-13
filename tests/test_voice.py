"""IV-3BH1: keep retired wording out of the rendered PC and phone UI in both languages."""
from __future__ import annotations

import re

import pytest

from tests.browser_support import require_chromium
from tests.test_arabic_no_english import PC_PAGES
from tools.phone_check import PAGES as PHONE_PAGES

# Add a term here when its replacement ships; keep the reason beside it.
BANNED_WORDS = {
    "Successfully": "Say what happened without a redundant success announcement.",
    "Please": "Give the next action directly, without a polite preamble.",
    "Submit": "Name the action, such as Save or Import.",
    "Error:": "Explain the problem and what to do instead of adding a technical prefix.",
    "Invalid": "Say what the person needs to enter or choose.",
}


def _retired_words(text: str) -> list[str]:
    return [word for word in BANNED_WORDS if re.search(
        r"(?<!\w)" + re.escape(word) + (r"(?!\w)" if word[-1].isalnum() else ""), text, re.IGNORECASE
    )]


# Read actual text nodes after layout, excluding scripts, hidden fields, closed details and concealed panels.
# Include placeholders and submit-button values: neither is a DOM text node, but both can be on screen.
VISIBLE_TEXT = """() => {
  const text = [], walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const visible = el => {
    const closed = el.closest('details:not([open])');
    return (!closed || closed.querySelector(':scope > summary')?.contains(el)) &&
      el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
  };
  while (walker.nextNode()) {
    const node = walker.currentNode, el = node.parentElement;
    if (el && !el.closest('script, style, noscript, template') && visible(el) && node.textContent.trim()) {
      text.push(node.textContent.trim());
    }
  }
  for (const el of document.querySelectorAll('input, textarea')) {
    if (!visible(el)) continue;
    if (el.matches('input[type=submit], input[type=button]')) text.push(el.value);
    else if (!el.value && el.placeholder) text.push(el.placeholder);
  }
  return text.join('\\n');
}"""


@pytest.fixture(scope="module", params=[False, True], ids=["pc", "phone"])
def voice_page(request, tmp_path_factory):
    """A real profile and the sample household, on the same two shells that ship."""
    chromium = require_chromium()
    from playwright.sync_api import sync_playwright
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Host

    phone = request.param
    root = tmp_path_factory.mktemp("voice-phone" if phone else "voice-pc")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_TODAY", "2026-10-02")
        patch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
        host = Host(lambda cfg: profile_app(cfg, root / "docs", devices=Devices(root / "app", port=0), phone=phone)).start()
        try:
            with sync_playwright() as pw:
                with pw.chromium.launch(executable_path=chromium, args=["--no-sandbox"]) as browser:
                    context = browser.new_context(viewport={"width": 360 if phone else 1366, "height": 800},
                                                  is_mobile=phone, has_touch=phone)
                    page = context.new_page()
                    page.set_default_timeout(5000)
                    page.goto(host.launch_url)
                    page.goto(host.origin + "/profiles/new")
                    for name, value in {"name": "Voice sample", "password": "a dummy voice password",
                                        "confirm": "a dummy voice password", "answer": "Dummy"}.items():
                        page.locator(f"input[name={name}]").fill(value)
                    if page.locator("select[name=question]").count():
                        page.select_option("select[name=question]", index=1)
                    else:
                        page.fill("input[name=question]", "Dummy question?")
                    page.click("form[action='/profiles/new'] button[type=submit]")
                    key = re.search(r"\d{4}-\d{4}-\d{4}", page.content()).group(0)
                    if page.locator("input[name=recovery][type=text]").count():
                        page.fill("input[name=recovery]", key)
                    page.click("form[action='/profiles/confirm'] button[type=submit]")
                    page.goto(host.origin + "/")
                    response = page.evaluate("""async () => {
                      const token = document.querySelector('meta[name=lightning-session]').content;
                      const response = await fetch('/sample/mohab-2026', {
                        method: 'POST', body: new URLSearchParams({__session: token})
                      });
                      return response.status;
                    }""")
                    assert response == 200, "The voice audit needs the sample household."
                    yield page, host.origin, phone
        finally:
            host.stop()


@pytest.mark.parametrize("locale", ["en", "ar"])
def test_main_pages_keep_retired_words_off_screen(voice_page, locale):
    page, origin, phone = voice_page
    page.goto(origin + "/")
    page.evaluate("""async locale => {
      const token = document.querySelector('meta[name=lightning-session]').content;
      const response = await fetch('/settings/locale', {
        method: 'POST', body: new URLSearchParams({__session: token, locale})
      });
      if (!response.ok) throw new Error('Could not select the audit language');
    }""", locale)
    # Reuse the phone audit's catalogue and the main PC catalogue from the Arabic audit.
    paths = tuple(dict.fromkeys(PHONE_PAGES if phone else (*PC_PAGES, "/profiles", "/profiles/devices", "/accounts/1/transaction/new")))
    problems = {}
    for path in paths:
        response = page.goto(origin + path)
        assert response is not None and response.status == 200, (path, response and response.status)
        assert page.locator("html").get_attribute("lang").split("-")[0] == locale, path
        text = page.evaluate(VISIBLE_TEXT)
        assert text.strip(), f"{path}: the voice audit found no visible text"
        bad = _retired_words(text)
        if bad:
            problems[path] = {word: [line for line in text.splitlines() if word.casefold() in line.casefold()][:3]
                              for word in bad}
    assert not problems, {"shell": "phone" if phone else "pc", "locale": locale, "retired wording": problems}


@pytest.mark.parametrize("text, expected", [
    ("Saved successfully.", ["Successfully"]),
    ("PLEASE choose a category. Submit", ["Please", "Submit"]),
    ("Error:Invalid amount", ["Error:", "Invalid"]),
    ("Resubmit the unsuccessful payment after invalidation.", []),
    ("حفظ المعاملة", []),
])
def test_retired_word_matching_uses_words_and_ignores_case(text, expected):
    assert _retired_words(text) == expected


def test_voice_audit_sees_visible_text_and_ignores_hidden_implementation(voice_page):
    page = voice_page[0].context.new_page()
    try:
        page.set_content('''<style>.concealed { display: none } .faded { opacity: 0 }</style>
          <script>const implementation = "Invalid";</script>
          <p data-label="Error:" class="Invalid">Saved</p>
          <div hidden>Please</div><div class="concealed">Submit</div><div class="faded">Successfully</div>
          <details><summary>More</summary>Invalid</details>
          <input type="hidden" value="Invalid"><input placeholder="Choose a category"><button>Save</button>''')
        assert _retired_words(page.evaluate(VISIBLE_TEXT)) == []
        page.set_content('''<p>Error: <strong>Invalid</strong> amount</p>
          <input placeholder="Submit"><input type="submit" value="Please">''')
        assert _retired_words(page.evaluate(VISIBLE_TEXT)) == ["Please", "Submit", "Error:", "Invalid"]
    finally:
        page.close()
