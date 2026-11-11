"""IT-2C2: bring an old plaintext `data/lightning.db` into a new encrypted profile; the old file never changes."""

from __future__ import annotations

import hashlib
import re
import sqlite3

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.runtime import profile_screens
from lightning.runtime.app import profile_app
from lightning.runtime.http import Credentials
from lightning.runtime.session import ProfileError, ProfileSession

PASSWORD = "a correct long passphrase"
QUESTION = "What was the name of your first school?"
ANSWER = "El Orman"
BALANCES = "SELECT account_id, SUM(amount_e6) FROM ledger_entries GROUP BY account_id ORDER BY account_id"


def old_database(tmp_path):
    path = tmp_path / "old" / "data" / "lightning.db"
    path.parent.mkdir(parents=True)
    c = build(path)
    f = c.account_flows
    bank = f.open_account("CIB Current", "BANK", "2026-09-01", "50,000", institution="CIB")
    f.open_account("Wallet", "CASH", "2026-09-01", "1200")
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    c.transactions.record_outflow("2026-09-03", bank.id, "150", food)
    c.transactions.record_outflow("2026-09-04", bank.id, "75", food)
    c.db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    facts = (c.db.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
             [tuple(row) for row in c.db.conn.execute(BALANCES)])
    c.db.close()
    return path, facts


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_old_data_becomes_an_encrypted_profile_and_the_old_file_is_unchanged(tmp_path):
    source, (count, balances) = old_database(tmp_path)
    before = digest(source)
    session = ProfileSession(tmp_path / "profiles")
    session.prepare("Home", PASSWORD, PASSWORD, QUESTION, ANSWER, legacy_source=source)
    session.confirm(session.pending.recovery)
    db_path = session.paths.db_path
    conn = session.container.db.conn
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == count
    assert [tuple(row) for row in conn.execute(BALANCES)] == balances
    session.close()
    assert db_path.read_bytes()[:16] != b"SQLite format 3\x00"
    assert digest(source) == before
    assert not list(db_path.parent.glob("*.partial"))


def test_a_file_that_is_not_lightning_is_refused(tmp_path):
    other = tmp_path / "other.db"
    with sqlite3.connect(other) as connection:
        connection.execute("CREATE TABLE notes (x)")
    text = tmp_path / "notes.txt"
    text.write_text("hello", encoding="utf-8")
    session = ProfileSession(tmp_path / "profiles")
    for path in (other, text, tmp_path / "missing.db"):
        with pytest.raises(ProfileError, match="not an old Lightning database"):
            session.prepare("Home", PASSWORD, PASSWORD, QUESTION, ANSWER, legacy_source=path)
    assert session.pending is None


def test_a_failed_import_publishes_no_profile(tmp_path, monkeypatch):
    source, _facts = old_database(tmp_path)
    before = digest(source)
    session = ProfileSession(tmp_path / "profiles")
    session.prepare("Home", PASSWORD, PASSWORD, QUESTION, ANSWER, legacy_source=source)
    paths = session.pending.paths

    def broken(*_args, **_kwargs):
        raise OSError("disk full")
    monkeypatch.setattr("lightning.database.staging.export_snapshot", broken)
    with pytest.raises(OSError):
        session.confirm(session.pending.recovery)
    assert not paths.db_path.exists() and session.container is None
    assert digest(source) == before


def _token(text):
    return re.search(r'name="csrf" value="([^"]+)"', text).group(1)


def test_the_chooser_offers_the_old_data_by_index_and_refuses_a_bad_index(tmp_path, monkeypatch):
    source, _facts = old_database(tmp_path)
    monkeypatch.setattr(profile_screens, "legacy_databases", lambda: (source,))
    cfg = Credentials("http://127.0.0.1:9876")
    app = profile_app(cfg, tmp_path / "Documents" / "Lightning")
    browser = TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin})
    browser.__enter__()
    assert browser.get("/__launch", params={"code": cfg.launch_code}).status_code == 200
    chooser = browser.get("/profiles")
    assert "Bring in your old Lightning data" in chooser.text and "/profiles/new?legacy=0" in chooser.text
    assert browser.get("/profiles/new?legacy=9").status_code == 400
    assert browser.get("/profiles/new?legacy=..%2Fx").status_code == 400
    page = browser.get("/profiles/new?legacy=0")
    assert 'name="legacy" value="0"' in page.text and 'name="currency"' not in page.text
    refused = browser.post("/profiles/new", data={"csrf": _token(page.text), "name": "Home", "legacy": "9",
                                                  "password": PASSWORD, "confirm": PASSWORD,
                                                  "question": QUESTION, "answer": ANSWER})
    assert refused.status_code == 400
    page = browser.post("/profiles/new", data={"csrf": _token(refused.text), "name": "Home", "legacy": "0",
                                               "password": PASSWORD, "confirm": PASSWORD,
                                               "question": QUESTION, "answer": ANSWER})
    assert page.status_code == 200, page.text
    recovery = re.search(r'aria-label="Recovery key">([0-9-]+)<', page.text).group(1)
    done = browser.post("/profiles/confirm", data={"csrf": _token(page.text), "recovery": recovery})
    assert done.status_code == 200
    assert app.session.container is not None and app.session.paths.db_path.read_bytes()[:16] != b"SQLite format 3\x00"
    browser.__exit__(None, None, None)


def test_opening_the_old_file_directly_points_to_the_import(tmp_path):
    source, _facts = old_database(tmp_path)
    session = ProfileSession(tmp_path / "profiles")
    with pytest.raises(ProfileError, match="Bring in your old Lightning data"):
        session.unlock(str(source), PASSWORD)
