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
    from lightning.ui.phone.screens.review_cards import review_cards
    cards = review_cards(c, date(2026, 10, 4), before)   # 3AY8: one row per card; inbox items keep Not now
    assert f"1 of {len(cards)}" in page and page.count('id="card-heading"') == 1
    at = next(n for n, card in enumerate(cards) if card.review_id)
    assert "Not now" in http.get(f"/activity?tab=review&i={at}").text
    first = next(i for i in before if i["review_id"] == cards[at].review_id)
    done = http.post("/activity/not-now", data={"identity": first["review_id"]}, follow_redirects=False)
    assert done.status_code in (302, 303)
    after = screen.review_items(c, date(2026, 10, 4))
    assert first["review_id"] not in {i["review_id"] for i in after} and len(after) == len(before) - 1
    assert first["review_id"] in {i["review_id"] for i in screen.review_items(c, date(2026, 10, 6))}


def test_activity_bars_are_proportional_to_in_and_out(client):
    """IV-11D3: two bars on one scale; the larger of In and Out is full and the other is its share."""
    from datetime import date
    from lightning.ui.phone.screens import activity as screen
    http, c = client
    s = screen.build(c, date(2026, 10, 4))
    top = max(s.money_in, s.money_out)
    assert top > 0 and max(s.in_share, s.out_share) == 100
    assert abs(s.in_share - round(s.money_in / top * 100)) <= 1 and abs(s.out_share - round(s.money_out / top * 100)) <= 1
    page = http.get("/activity").text
    assert f'style="width: {s.in_share}%"' in page and f'style="width: {s.out_share}%"' in page


def test_a_transfer_reads_the_same_on_home_and_activity_and_typed_names_stay_in_arabic(client):
    """BV-11G: one transfer, one form (from → to) on both pages; an account name is never translated; no space before the comma."""
    import re
    http, c = client
    names = {a.name for a in c.accounts.list()}
    for path in ("/", "/activity"):
        page = http.get(path).text
        assert "<bdi translate=\"no\">" in page
        assert not re.search(r"\bTo <", page)
    http.cookies.set("lightning_locale", "ar")
    ar = http.get("/activity", headers={"Accept-Language": "ar"}).text
    home = http.get("/", headers={"Accept-Language": "ar"}).text
    typed_names = re.findall(r'<bdi translate="no">([^<]+)</bdi>', ar + home)
    assert typed_names and all(t in names for t in typed_names)
    assert "محفظة نقدية" not in "".join(re.findall(r'<bdi translate="no">([^<]+)</bdi>', home + ar))


def test_an_empty_ledger_offers_add_and_import_instead_of_zeros(tmp_path):
    from lightning.ui.phone.router import mount_phone
    from conftest import build
    app = create_app(build(tmp_path / "e.db"))
    mount_phone(app)
    page = TestClient(app).get("/activity").text
    assert "No transactions yet." in page and 'href="/add-transaction"' in page and 'href="/import"' in page
    assert "phone-money-line" not in page
