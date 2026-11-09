"""IV-11I: the full Add page behind the sheet (/accounts/add-transaction) is titled Add, lights the Add tab, puts the
form before the section switch and draws no emoji."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app

EMOJI = re.compile("[\U0001F300-\U0001FAFF]")


@pytest.fixture
def page(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-12")
    load_mohab_2026(c)
    app = create_app(c)

    @app.middleware("http")
    async def use_phone(request, call_next):
        request.state.phone = True
        return await call_next(request)

    return TestClient(app).get("/accounts/add-transaction").text


def test_the_add_page_is_titled_add_and_lights_the_add_tab(page):
    assert "<title>Add" in page
    tabbar = page.split('class="phone-tabbar"')[1].split("</nav>")[0]
    assert re.search(r'phone-add is-chosen"[^>]*aria-current="page"', tabbar)
    assert tabbar.count('aria-current="page"') == 1          # Money is not lit


def test_the_form_comes_before_the_section_switch(page):
    assert "section-tabs" not in page.split("data-transaction-form")[0]


def test_no_emoji_is_drawn_on_the_phone(page):
    assert not EMOJI.search(page)
    css = (Path(__file__).parents[1] / "lightning/ui/static/phone.css").read_text(encoding="utf8")
    assert not EMOJI.search(css)
