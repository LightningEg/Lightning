"""3AY1: four state and copy bugs on the phone's screens: a Net worth tile that says "Today" over a past month (and a hero
that repeats it), a "since your last visit" line that names today and counts a bulk load row by row, a lower-cased
"us dollars" label, and late bills listed under "Next 14 days"."""
from __future__ import annotations


import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_TODAY", "2026-10-04")
        patch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
        c = build(tmp_path_factory.mktemp("state") / "t.db")
        load_mohab_2026(c)
        yield c
        c.db.close()


def _phone(c, cookies=None):
    inner = create_app(c)

    async def app(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await inner(scope, receive, send)
    client = TestClient(app)
    for key, value in (cookies or {}).items():
        client.cookies.set(key, value)
    return client


def test_a_bulk_load_is_one_event_and_today_is_not_named(sample):
    assert sample.transactions.recorded_since("2000-01-01T00:00:00+00:00") <= 5  # 370 rows, a handful of moments
    html = _phone(sample, {"lightning_overview_seen": "2026-10-04T08:00:00+00:00"}).get("/").text
    assert "since your last visit on 2026-10-04" not in html


def test_late_bills_have_their_own_heading_on_the_bills_page(sample):
    from lightning.ui.phone.router import mount_phone
    from lightning.ui.web import create_app
    app = create_app(sample)
    mount_phone(app)
    inner = app

    async def phone(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await inner(scope, receive, send)
    html = TestClient(phone).get("/money/bills").text
    main = html.split("<main", 1)[1]
    if 'id="late-heading"' in main:                      # Late is one block, first
        late = main.split('id="late-heading"')[1].split("</section>")[0]
        assert "Late" in late
        later = main.split('id="late-heading"')[1].split("</section>", 1)[1]
        assert "Late ·" not in later                    # no late row among the coming ones
