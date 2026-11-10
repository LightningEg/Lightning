"""Every error is a branded page with a plain sentence: no plain text, no JSON, no framework answer (IV-3BD1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.ui.web import create_app


@pytest.fixture()
def client(tmp_path):
    c = build(tmp_path / "t.db")
    yield TestClient(create_app(c))
    c.db.close()


def test_foreign_origin_post_gets_the_branded_403(client):
    response = client.post("/settings/locale", data={"locale": "ar"}, headers={"Origin": "http://evil.example"})
    assert response.status_code == 403
    assert "text/html" in response.headers["content-type"]
    assert "<title>" in response.text and "came from outside Lightning" in response.text


def test_wrong_method_gets_the_branded_405(client):
    response = client.post("/")
    assert response.status_code == 405
    assert "text/html" in response.headers["content-type"] and "That page cannot do this." in response.text


def test_pc_transactions_sorted_goes_back_to_transactions(client):
    response = client.get("/transactions/sorted", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"].startswith("/transactions")


def test_no_plain_text_or_framework_errors_in_routes():
    """Only fetch answers ("Deleted."), the health probe and file downloads may skip the branded page."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "lightning" / "ui"
    allowed = {"routes/transactions.py", "routes/bank_imports.py", "web.py"}
    hits = [f"{p.relative_to(root).as_posix()}:{n}" for p in list(root.glob("routes/*.py")) + [root / "web.py"]
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if re.search(r"HTTPException\((?!404)", line)
            or (re.search(r"PlainTextResponse\(", line) and p.relative_to(root).as_posix() not in allowed)]
    assert not hits, hits
