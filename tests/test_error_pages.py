"""IV-3BD: every error is the branded page, never raw text or JSON (3BD1), and the validation page names the problem (3BD5)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_TODAY", "2026-10-02")
        patch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
        c = build(tmp_path_factory.mktemp("err") / "t.db")
        load_mohab_2026(c)
        yield TestClient(create_app(c))
        c.db.close()


def test_foreign_origin_post_gets_the_branded_403(client):
    r = client.post("/settings/locale", data={"locale": "ar"}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    assert "text/html" in r.headers["content-type"]
    assert "<title>" in r.text and "Something went wrong" in r.text
    assert "came from outside Lightning" in r.text


def test_wrong_method_and_empty_export_are_branded_pages(client):
    r = client.post("/", data={})
    assert r.status_code == 405 and "text/html" in r.headers["content-type"] and "That page cannot do this." in r.text
    r = client.post("/exports/reevaluations", data={})
    assert r.status_code == 422 and "text/html" in r.headers["content-type"]
    assert "Select between 1 and 10,000 records" in r.text


def test_pc_sorted_sheet_redirects_to_transactions(client):
    r = client.get("/transactions/sorted", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/transactions"


def test_validation_page_names_the_problem_and_goes_back(client):
    r = client.post("/exports/reevaluations", data={}, headers={"Referer": "http://testserver/investments?x=1"})
    assert r.status_code == 422
    assert "That did not save" in r.text and "Check your setup" not in r.text
    assert "Select between 1 and 10,000 records" in r.text
    assert 'href="/investments?x=1"' in r.text
    r = client.post("/exports/reevaluations", data={})  # no Referer: Home
    assert 'class="btn primary" href="/"' in r.text
