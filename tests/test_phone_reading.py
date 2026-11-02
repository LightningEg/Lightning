"""The phone's reading screens (IV-3AN: 3AN7 Budget, 3AN9 no wall of zeros, 3AN12 the rest, 3AN10 Arabic): what each
screen leads with, what opens a sheet, and that Arabic has no English word.

Figures come from the services; these tests read what the pages say, as the phone shows them. Digits become
Arabic-Indic in the browser (arabic-numbers.js), so the one-digit-system check is tools/phone_check.py's."""
import re

import pytest
from fastapi.testclient import TestClient

from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Credentials

from test_profile_app import create, token

NAMES = ("Lightning", "EGP", "Microbus", "Carrefour", "ACME")  # the brand, the currency and names the sample typed


@pytest.fixture(scope="module")
def phone(tmp_path_factory):
    folder = tmp_path_factory.mktemp("phone-reading")
    cfg = Credentials("http://127.0.0.1:9866")
    app = profile_app(cfg, folder / "docs", devices=Devices(folder / "app", port=0), phone=True)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        page = browser.get("/")
        browser.post("/demo", data={"__session": token(page.text, "__session")})
        yield browser


def _text(html: str) -> str:
    return re.sub(r"(?s)<(script|style)\b.*?</\1>|<[^>]+>", " ", html)


def _english(html: str) -> list[str]:
    """Latin words of three letters or more in what a page shows, less the brand, the currency and typed names."""
    text = _text(html)
    for name in NAMES:
        text = text.replace(name, "")
    return re.findall(r"[A-Za-z]{3,}", text)


def _in_arabic(browser, *paths):
    session = token(browser.get("/budget").text, "__session")
    browser.post("/settings/locale", data={"locale": "ar", "__session": session})
    try:
        return [browser.get(path).text for path in paths]
    finally:
        browser.post("/settings/locale", data={"locale": "en", "__session": session})


def test_the_category_sheet_and_its_payments_are_arabic(phone):
    """3AN7 + 3AN10: a category sheet and its payments fragment have no English word."""
    html = phone.get("/budget").text
    src = re.search(r'data-fold-src="(/budget/category/\d+/payments\?month=[\d-]+)"', html).group(1)
    page, filled, empty = _in_arabic(phone, "/budget", src, src.split("?")[0] + "?month=2020-01")
    assert _english(page) == [] and _english(filled) == [] and _english(empty) == []
    sheet = page[page.index('class="phone-sheet-panel"'):]
    assert any(word in sheet[:sheet.index("</details>")] for word in ("المعدل", "عدّيت الحد"))  # the pace or over sentence
    assert "آخر المدفوعات" in filled and "لسه ماصرفتش" in empty
