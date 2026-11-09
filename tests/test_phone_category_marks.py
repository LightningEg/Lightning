"""IV-11D6 (guideline C08.2): a row's chip holds its category's mark in the in or out colour; a category a person made
keeps the arrow, and transfers keep ⇄."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from lightning.samples import load_mohab_2026
from lightning.ui.category_marks import MARKS
from lightning.ui.phone.router import mount_phone
from lightning.ui.web import create_app

ROW = re.compile(r'<a class="phone-txn" href="[^"]*" data-txn="(\d+)"[^>]*>\s*<span class="phone-txn-av is-(\w+)( has-mark)?"'
                 r'[^>]*><svg viewBox="0 0 24 24"><path d="([^"]+)"/>')


@pytest.fixture
def mohab(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-04")
    load_mohab_2026(c)
    return c


def test_every_built_in_category_has_one_mark(c):
    built_in = {x.code for x in c.categories.tree() if x.depth >= 2 or x.code.endswith("UNACCOUNTED")}
    assert built_in <= set(MARKS), sorted(built_in - set(MARKS))
    assert all(len(path) > 10 for path in MARKS.values())


@pytest.mark.parametrize("path", ["/home", "/activity", "/activity?month=2026-09"])
def test_rows_show_their_category_mark_and_a_made_category_keeps_the_arrow(mohab, path):
    mine = mohab.categories.create(mohab.categories.get_by_code("EXP.PERSONAL").id, "Cat food").id
    account = mohab.accounts.list(active_only=True)[0].id
    made = mohab.transactions.record_outflow("2026-10-04", account, "120", mine).id
    app = create_app(mohab)
    mount_phone(app)
    html = TestClient(app).get(path).text
    rows = ROW.findall(html)
    assert rows, path
    for txn_id, kind, marked, drawn in rows:
        row = mohab.transactions.get(int(txn_id))
        ids = [line.category_id for line in row.lines if line.category_id]
        code = mohab.categories.get(ids[0]).code if ids else ""
        mark = MARKS.get(code, "")
        if kind in ("in", "out") and mark:
            assert marked and drawn == mark, (code, kind)
        else:
            assert not marked, (code, kind)   # a made category, a transfer or an investment: the arrow
    if path != "/activity?month=2026-09":
        assert any(int(t) == made and not m for t, _, m, _ in rows)    # the made category's row keeps its arrow
    assert any(m for _, _, m, _ in rows)                                 # and built-in ones show their marks
