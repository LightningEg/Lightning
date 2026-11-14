"""3AY10 (owner picks 2026-11-11): Money's Net worth sheet holds its parts, then US dollars and
21K gold as two rows (its 12-month line sits under the hero, once); an account's page asks first whether the bank agrees; the older phone Overview is gone."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.samples import load_mohab_2026
from lightning.ui.phone.router import mount_phone
from lightning.ui.web import create_app, templates


@pytest.fixture
def phone(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-11")
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    c = build(tmp_path / "t.db")
    load_mohab_2026(c)
    app = create_app(c)
    mount_phone(app)

    async def as_phone(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)
    yield TestClient(as_phone)
    c.db.close()


def test_the_net_worth_sheet_has_its_parts_then_dollars_and_gold_and_the_line_shows_once(phone):
    html = phone.get("/money").text
    sheet = html[html.index('class="phone-sheet-row'):]
    sheet = sheet[:sheet.index("</details>")]
    assert html.count('class="phone-chart-trend"') == 1 and "phone-chart-trend" in sheet   # IV-11M7 (mockup v2.0): the line lives in Net worth's sheet
    units = re.findall(r'<span>(In [^<]+)<small>', sheet)
    assert units == ["In US dollars", "In grams of 21K gold"]


def test_an_account_asks_the_bank_first_and_yes_closes_the_question(phone):
    html = phone.get("/accounts/1").text
    asked = re.search(r'Does CIB say ([\d,.]+) EGP\?', html)
    balance = re.search(r'name="balance" value="([^"]+)"', html).group(1)
    assert asked and 'href="/accounts/1/reconcile?date=2026-11-11"' in html   # Fix it opens Adjust balance
    done = phone.post("/accounts/1/reconcile/close", data={"date": "2026-11-11", "balance": balance,
                                                             "return_to": "/accounts/1"}, follow_redirects=False)
    assert done.headers["location"].startswith("/accounts/1?")
    assert 'id="bank-check-heading"' not in phone.get("/accounts/1").text


def test_the_older_phone_overview_is_gone():
    names = set(templates.env.list_templates())
    assert "phone/dashboard/fold.html" not in names
    source = (templates.env.loader.get_source(templates.env, "phone/dashboard/index.html")[0])
    assert source.strip().endswith('{% extends "phone/home.html" %}')   # the address is Home
