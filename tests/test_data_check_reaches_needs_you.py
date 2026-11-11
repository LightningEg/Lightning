"""NF-2AJ: a data check that reads ISSUE reaches Needs you and the Overview and opens Data checks; a clean profile
shows nothing new."""
from __future__ import annotations

from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.samples import SAMPLE_TODAY, load_mohab_2026
from lightning.ui.web import create_app

LABEL = "A data check does not add up"
FREE_CASH = "Free cash matches the ledger"


@pytest.fixture
def sample(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", SAMPLE_TODAY.isoformat())
    load_mohab_2026(c)
    return c


def _labels(c):
    return [item["label"] for item in c.review.items(SAMPLE_TODAY)] if hasattr(c, "review") else None


def test_a_clean_year_shows_no_data_check_row(sample):
    with TestClient(create_app(sample)) as client:
        for url in ("/", "/needs-you"):
            assert LABEL not in client.get(url).text


def test_a_failing_check_is_one_tap_from_home(sample, monkeypatch):
    real = sample.reporting.owned_liquid_cash
    monkeypatch.setattr(sample.reporting, "owned_liquid_cash", lambda as_of: real(as_of) + D("100"))
    with TestClient(create_app(sample)) as client:
        inbox = client.get("/needs-you").text
        assert LABEL in inbox and FREE_CASH in inbox and 'href="/checks"' in inbox
        home = client.get("/").text
        assert LABEL in home and 'href="/checks"' in home
        assert client.get("/checks").status_code == 200


def test_the_phone_home_to_do_leads_with_it(sample, monkeypatch):
    from lightning.ui.phone.router import mount_phone
    real = sample.reporting.owned_liquid_cash
    monkeypatch.setattr(sample.reporting, "owned_liquid_cash", lambda as_of: real(as_of) + D("100"))
    app = create_app(sample)
    mount_phone(app)
    html = TestClient(app).get("/home").text
    todo = html.split('id="todo-heading"', 1)[1]
    assert "Data checks" in todo and 'href="/checks"' in todo
