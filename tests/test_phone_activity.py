"""3AY8: Activity. All is the month with one money line; To review is one card at a time with its one action and Not now;
clearing the queue clears Home's To do row for it."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lightning.samples import load_mohab_2026
from lightning.ui.phone.router import mount_phone
from lightning.ui.web import create_app
from conftest import *  # noqa: F401,F403  (fixtures)


@pytest.fixture
def client(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-04")
    load_mohab_2026(c)
    app = create_app(c)
    mount_phone(app)
    return TestClient(app), c


def test_all_shows_the_month_with_one_money_line_and_the_review_count(client):
    http, _ = client
    page = http.get("/activity").text
    assert "phone-money-line" in page and "phone-txn" in page and "To review" in page
    earlier = http.get("/activity?month=2026-09").text
    assert "2026-09" in earlier and "phone-txn" in earlier


def test_a_bad_month_or_tab_falls_back_instead_of_failing(client):
    http, _ = client
    assert http.get("/activity?month=nonsense&tab=zzz&i=-4").status_code == 200


def test_to_review_is_one_card_and_not_now_moves_it_out_until_tomorrow(client):
    from datetime import date
    from lightning.ui.phone.screens import activity as screen
    http, c = client
    before = screen.review_items(c, date(2026, 10, 4))
    page = http.get("/activity?tab=review").text
    if not before:
        assert "All sorted" in page
        return
    assert f"1 of {len(before)}" in page and "Not now" in page and page.count('id="card-heading"') == 1
    first = before[0]
    done = http.post("/activity/not-now", data={"identity": first["review_id"]}, follow_redirects=False)
    assert done.status_code in (302, 303)
    after = screen.review_items(c, date(2026, 10, 4))
    assert first["review_id"] not in {i["review_id"] for i in after} and len(after) == len(before) - 1
    assert first["review_id"] in {i["review_id"] for i in screen.review_items(c, date(2026, 10, 6))}
