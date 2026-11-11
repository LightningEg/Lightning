"""3AY8 (owner pick 2026-11-11): To review is one row per card; each card's Primary is its kind's own verb. A row nobody
sorted, from a payee usually filed somewhere, *Looks right* files it there in one tap; with no history it asks to
choose; Skip moves on; the grouped "N payments have no category" item is not a second card for the same rows."""
from __future__ import annotations

import re
from html import escape

import pytest
from fastapi.testclient import TestClient

from lightning.ui.phone.router import mount_phone
from lightning.ui.web import create_app


def _phone(c) -> TestClient:
    app = create_app(c)
    mount_phone(app)

    @app.middleware("http")
    async def use_phone(request, call_next):
        request.state.phone = True
        return await call_next(request)
    return TestClient(app)


@pytest.fixture
def unsorted(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-12")
    accounts, cats = setup
    cib = accounts["cib"]
    t = c.transactions
    for day in ("2026-09-01", "2026-09-03", "2026-09-05"):   # usually Food: 3 of its last 5
        t.record_in_account(cib.id, day, "-250", cats["EXP.PERSONAL.FOOD"].id, None, "Seoudi", "")
    t.record_outflow("2026-09-08", cib.id, "90", c.categories.get_by_code("EXP.UNACCOUNTED").id, counterparty="Seoudi",
                     allow_system_category=True)
    t.record_outflow("2026-09-10", cib.id, "40", c.categories.get_by_code("EXP.UNACCOUNTED").id, counterparty="Stall",
                     allow_system_category=True)
    return c, cats


def test_each_row_is_a_card_with_its_kind_s_verb_and_looks_right_files_it(unsorted):
    c, cats = unsorted
    phone = _phone(c)
    first = phone.get("/activity?tab=review").text
    assert "1 of 2" in first and ">Stall<" in first and "Choose a category" in first   # newest first; no history: choose
    assert "have no category" not in first                                              # the grouped item is not a card
    second = phone.get("/activity?tab=review&i=1").text
    assert ">Seoudi<" in second and "Looks right" in second and escape(cats["EXP.PERSONAL.FOOD"].name) in second
    assert 'href="/activity?tab=review&amp;i=0">Skip<' in second                        # Skip moves on (it wraps)
    form = re.search(r'(?s)<form method="post" action="(/transactions/(\d+)/category)".*?</form>', second)
    fields = dict(re.findall(r'name="([^"]+)" value="([^"]*)"', form.group(0)))
    done = phone.post(form.group(1), data=fields)
    assert done.status_code == 200 and done.url.path == "/activity"
    assert c.transactions.get(int(form.group(2))).lines[0].category_id == cats["EXP.PERSONAL.FOOD"].id
    assert "1 of 1" in phone.get("/activity?tab=review").text                           # one card left: Stall
