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


@pytest.fixture
def twice(c, setup, monkeypatch):
    """One payment typed by hand on the 10th and imported from the bank on the 11th; groceries of the same amount on
    two days, both typed; and a taxi typed twice in the same minute."""
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-12")
    accounts, cats = setup
    cib, food = accounts["cib"].id, cats["EXP.PERSONAL.FOOD"].id
    t = c.transactions
    typed = t.record_in_account(cib, "2026-09-10", "-1200", food, None, "Carrefour", "")
    imported = t.record_in_account(cib, "2026-09-11", "-1200", food, None, "", "card 1234")
    c.db.execute("UPDATE transactions SET source='IMPORT' WHERE id=?", (imported.id,))
    t.record_in_account(cib, "2026-09-02", "-300", food, None, "Seoudi", "")
    t.record_in_account(cib, "2026-09-04", "-300", food, None, "Seoudi", "")
    taxi = [t.record_in_account(cib, "2026-09-12", "-85", food, None, "Uber", "") for _ in range(2)]
    return c, typed, imported, taxi


def _card_form(html: str, action: str) -> dict:
    form = re.search(r'(?s)<form method="post" action="' + re.escape(action) + r'"[^>]*>.*?</form>', html)
    return dict(re.findall(r'name="([^"]+)" value="([^"]*)"', form.group(0)))


def test_a_payment_recorded_twice_is_a_card_whose_primary_deletes_the_copy(twice):
    """3AY8 (owner pick 2026-11-11): Delete the copy is the merge, checked against its preview and undoable; Compare
    opens that preview; the same groceries bought on two days by hand are not offered."""
    from datetime import date
    from lightning.transactions.duplicates import possible_duplicates
    c, typed, imported, taxi = twice
    pairs = possible_duplicates(c, date(2026, 6, 1), date(2026, 9, 12))
    assert sorted(map(sorted, pairs)) == sorted([sorted((taxi[0].id, taxi[1].id)), sorted((typed.id, imported.id))])
    phone = _phone(c)
    html = phone.get("/activity?tab=review&i=1").text   # newest first: the taxi, then Carrefour
    assert ">Carrefour<" in html and "Delete the copy" in html and ">Keep both<" in html and ">Compare<" in html
    assert re.search(r'href="/transactions/merge\?keep=\d+&amp;drop=\d+"', html)
    fields = _card_form(html, "/transactions/merge")
    done = phone.post("/transactions/merge", data=fields)
    assert done.status_code == 200 and done.url.path == "/activity" and "Copy deleted." in done.text
    gone = c.transactions.get(int(fields["drop_id"]))
    assert gone.is_void and not c.transactions.get(int(fields["keep_id"])).is_void
    assert "1 of 1" in phone.get("/activity?tab=review").text   # the taxi is left


def test_keep_both_leaves_both_and_the_pair_is_not_offered_again(twice):
    c, _, _, taxi = twice
    phone = _phone(c)
    html = phone.get("/activity?tab=review").text
    assert ">Uber<" in html
    fields = _card_form(html, "/activity/keep-both")
    done = phone.post("/activity/keep-both", data=fields)
    assert done.status_code == 200 and "Both kept." in done.text
    assert not any(c.transactions.get(t.id).is_void for t in taxi)
    assert ">Uber<" not in phone.get("/activity?tab=review").text
    again = phone.post("/activity/keep-both", data=fields)   # an answered pair cannot be answered twice
    assert "no longer offered" in again.text
