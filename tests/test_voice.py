"""The words a screen never says (IV-3BH1): each banned word has a one-line reason, and no page shows it.

Renders the main PC and phone pages of the sample household, in English and in Arabic, takes the visible text (and
titles, labels and placeholders) and looks for each word. Each later step of IV-3BH adds the word it retires."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app
from tests.test_arabic_no_english import PC_PAGES, PHONE_PAGES, _Text

# word -> why it is off the screen (guideline brand voice: plain, warm, short; A14)
BANNED = {
    "Successfully": "a message says what happened, not that it went well",
    "Please": "we ask once, plainly; never beg",
    "Submit": "a button names its action (Save, Add, Send)",
    "Error:": "say what to do, not the label of a failure",
    "Invalid": "say what is wrong with the thing, in a sentence",
    "Counterpart": "accounting jargon: the word is Payee (Arabic: الجهة); code and routes keep counterparty",
}


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_TODAY", "2026-10-02")
        patch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
        c = build(tmp_path_factory.mktemp("voice") / "t.db")
        load_mohab_2026(c)
        yield c
        c.db.close()


def _client(c, phone: bool, locale: str):
    app = create_app(c)
    if phone:
        inner = app

        async def phone_app(scope, receive, send):
            if scope["type"] == "http":
                scope.setdefault("state", {})["phone"] = True
            await inner(scope, receive, send)
        app = phone_app
    client = TestClient(app)
    assert client.post("/settings/locale", data={"locale": locale}, follow_redirects=False).status_code == 303
    return client


def _visible(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    return "\n".join(parser.found)


@pytest.mark.parametrize("locale", ["en", "ar"])
@pytest.mark.parametrize("phone", [False, True], ids=["pc", "phone"])
def test_no_page_says_a_banned_word(sample, phone, locale):
    client = _client(sample, phone, locale)
    found = {}
    for path in (PHONE_PAGES if phone else PC_PAGES):
        text = _visible(client.get(path).text)
        for word in BANNED:
            if re.search(r"(?<![A-Za-z])" + re.escape(word), text, re.I):
                found.setdefault(path, []).append(word)
    assert not found, found
