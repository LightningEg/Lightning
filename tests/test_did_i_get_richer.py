"""NF-7BF (r41 phase 3): the phone's Report says whether the period left you richer, by how much in grams of 21K
gold, and why, with the PC Overview's net worth bridge: Net flow + Market moves + Other changes = Change in net worth."""
from __future__ import annotations

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.samples import load_mohab_2026
from lightning.ui.i18n import translate
from lightning.ui.phone.router import mount_phone
from lightning.ui.phone.screens import report
from lightning.ui.web import create_app

DAY = date(2026, 10, 2)


@pytest.fixture
def mohab(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", DAY.isoformat())
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    c = build(tmp_path / "t.db")
    load_mohab_2026(c)
    yield c
    c.db.close()


def _phone(c):
    app = create_app(c)
    mount_phone(app)

    async def as_phone(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)
    return TestClient(as_phone)


def _text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_the_parts_add_up_to_the_change_and_gold_can_disagree_with_pounds(mohab):
    s = report.build(mohab, DAY, "last")   # September 2026
    b = s.bridge
    assert b and b["change"] > 0 and b["change"] == s.change and s.since == "2026-08-31"
    assert b["net_flow"] + b["market_moves"] + b["other_changes"] == b["change"] and b["net_flow"] == s.net
    # Gold rose faster than Mohab saved: richer in pounds, fewer grams of 21K gold. The app says both.
    assert s.gold_change is not None and s.gold_change < 0


def test_no_gold_price_at_the_start_leaves_the_gold_line_out(mohab):
    s = report.build(mohab, DAY, "ytd")
    assert s.bridge and s.gold_change is None
    page = _phone(mohab).get("/money/report?period=ytd").text
    assert "Richer than on" in page and "In gold:" not in page


def test_the_report_page_leads_with_the_verdict_gold_and_why(mohab):
    page = _phone(mohab).get("/money/report?period=last").text
    hero = _text(page.split('class="phone-hero"', 1)[1].split("</section>", 1)[0])
    assert "Richer than on 31 Aug" in hero and "grams of 21K fewer." in hero, hero
    why = _text(page.split('id="why-changed"', 1)[1].split("</div>\n</div>", 1)[0])
    assert why.index("Net flow") < why.index("Market moves") < why.index("Other changes"), why
    lead = _text(page.split('class="phone-lead', 1)[1].split("</div>", 1)[0]).lstrip('">')
    assert "Change in net worth" in hero and lead.startswith("+"), (hero, lead)   # owner, 2026-11-28: one figure leads


def test_every_new_sentence_has_an_arabic_form():
    for key in ("Richer than on {sa}.", "Poorer than on {sa}.", "The same as on {sa}.",
                "In gold: {g} grams of 21K more.", "In gold: {g} grams of 21K fewer.", "Why it changed", "Other changes",
                "Prices, gold, currencies and loans"):
        assert translate(key, "ar") != key, key
