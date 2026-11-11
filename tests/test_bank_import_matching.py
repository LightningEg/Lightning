"""A statement row can be linked to a transaction you already recorded.

A link moves no money and changes nothing on the existing transaction. Two equal
purchases stay distinct, a repeated import links once, a voided earlier import is
never quietly brought back, and a transfer can be backed by each bank's statement.
"""
from __future__ import annotations

import asyncio
import shutil

import pytest

from lightning.database import migrator
from lightning.database.connection import Database
from lightning.database.seed import seed
from tests.screens import said


def _stage(c, account_id, csv_text, name="statement.csv"):
    batch_id, _ = c.bank_imports.stage(account_id, name, csv_text.encode())
    return batch_id, c.bank_imports.preview(batch_id)[1]


def _by_line(rows):
    return {int(row["_line"]): row for row in rows}


def test_a_statement_row_links_to_the_purchase_you_already_recorded(c, setup):
    accounts, cats = setup
    cib = accounts["cib"].id
    manual = c.transactions.record_outflow("2026-10-01", cib, "450", cats["EXP.PERSONAL.FOOD"].id,
                                           counterparty="Carrefour", notes="weekly shop")
    before = c.reporting.account_balance(cib)

    batch_id, rows = _stage(c, cib, "Date,Counterparty,Amount\n2026-10-01,CARREFOUR MAADI,-450\n")
    row = rows[0]
    assert [candidate["id"] for candidate in row["_link_candidates"]] == [manual.id]
    assert row["_possible_duplicate"] and not row["_ready"]
    assert row["_default_match"] == f"link:{manual.id}"

    result = c.bank_imports.confirm(batch_id, {row["_import_row_id"]: {"match": f"link:{manual.id}"}})
    assert result["linked"] == 1 and result["posted"] == 0 and not result["errors"]
    assert c.reporting.account_balance(cib) == before
    kept = c.db.one("SELECT date,counterparty,notes FROM transactions WHERE id=?", (manual.id,))
    assert dict(kept) == {"date": "2026-10-01", "counterparty": "Carrefour", "notes": "weekly shop"}
    linked = c.db.one("SELECT status,transaction_id FROM bank_import_rows WHERE id=?", (row["_import_row_id"],))
    assert (linked["status"], linked["transaction_id"]) == ("LINKED", manual.id)


def test_two_equal_purchases_on_one_day_stay_distinct(c, setup):
    accounts, cats = setup
    cib = accounts["cib"].id
    manual = c.transactions.record_outflow("2026-10-02", cib, "60", cats["EXP.PERSONAL.FOOD"].id,
                                           counterparty="Kiosk")
    before = c.reporting.account_balance(cib)
    batch_id, rows = _stage(c, cib, "Date,Counterparty,Amount\n2026-10-02,Kiosk,-60\n2026-10-02,Kiosk,-60\n")
    first, second = _by_line(rows)[2], _by_line(rows)[3]
    # Only one row may default to the one recorded entry; the other is never silently dropped.
    assert first["_default_match"] == f"link:{manual.id}"
    assert second["_default_match"] == "skip" and second["_possible_duplicate"]

    result = c.bank_imports.confirm(batch_id, {first["_import_row_id"]: {"match": f"link:{manual.id}"},
                                               second["_import_row_id"]: {"match": "new"}})
    assert (result["linked"], result["posted"]) == (1, 1) and not result["errors"]
    assert c.reporting.account_balance(cib) == before - 60


def test_two_rows_cannot_both_link_to_one_entry(c, setup):
    accounts, cats = setup
    cib = accounts["cib"].id
    manual = c.transactions.record_outflow("2026-10-02", cib, "60", cats["EXP.PERSONAL.FOOD"].id)
    before = c.reporting.account_balance(cib)
    batch_id, rows = _stage(c, cib, "Date,Counterparty,Amount\n2026-10-02,Kiosk,-60\n2026-10-02,Kiosk,-60\n")
    decisions = {row["_import_row_id"]: {"match": f"link:{manual.id}"} for row in rows}
    result = c.bank_imports.confirm(batch_id, decisions)
    assert len(result["errors"]) == 1
    assert "already linked" in next(iter(result["errors"].values()))
    # As with any row error, nothing from the statement is kept until it is fixed.
    assert result["linked"] == 0 and c.reporting.account_balance(cib) == before
    assert c.db.scalar("SELECT COUNT(*) FROM bank_import_rows WHERE batch_id=? AND status='REVIEW'",
                       (batch_id,)) == 2


@pytest.mark.parametrize("reference", ["REF-77", ""])
def test_importing_the_same_statement_again_links_once(c, setup, reference):
    accounts, cats = setup
    cib = accounts["cib"].id
    manual = c.transactions.record_outflow("2026-10-03", cib, "200", cats["EXP.PERSONAL.FOOD"].id)
    text = f"Date,Counterparty,Amount,Reference\n2026-10-03,Shop,-200,{reference}\n"
    batch_id, rows = _stage(c, cib, text, "one.csv")
    c.bank_imports.confirm(batch_id, {rows[0]["_import_row_id"]: {"match": f"link:{manual.id}"}})
    before = c.reporting.account_balance(cib)

    again_id, again = _stage(c, cib, text, "one-again.csv")
    row = again[0]
    assert row["_possible_duplicate"] and row["_link_candidates"] == []
    assert row["_default_match"] == "skip"
    result = c.bank_imports.confirm(again_id, {row["_import_row_id"]: {"match": "skip"}})
    assert result["duplicates"] == 1 and c.reporting.account_balance(cib) == before


def test_a_late_bank_posting_still_finds_the_entry_within_three_days(c, setup):
    accounts, cats = setup
    cib = accounts["cib"].id
    manual = c.transactions.record_outflow("2026-10-01", cib, "75", cats["EXP.PERSONAL.FOOD"].id)
    near_id, near = _stage(c, cib, "Date,Counterparty,Amount\n2026-10-04,Cafe,-75\n", "near.csv")
    assert [candidate["id"] for candidate in near[0]["_link_candidates"]] == [manual.id]
    c.bank_imports.discard(near_id)
    _, far = _stage(c, cib, "Date,Counterparty,Amount\n2026-10-05,Cafe,-75\n", "far.csv")
    assert far[0]["_link_candidates"] == [] and far[0]["_default_match"] == "new"


def test_a_refund_never_links_to_a_purchase_of_the_same_size(c, setup):
    accounts, cats = setup
    cib = accounts["cib"].id
    c.transactions.record_outflow("2026-10-01", cib, "120", cats["EXP.PERSONAL.FOOD"].id)
    _, rows = _stage(c, cib, "Date,Counterparty,Amount\n2026-10-01,Shop,120\n")
    assert rows[0]["_link_candidates"] == []


def test_a_voided_earlier_import_is_informational_and_can_be_posted_again(c, setup):
    accounts, _ = setup
    cib = accounts["cib"].id
    text = "Date,Counterparty,Amount,Reference\n2026-10-06,Shop,-30,REF-VOIDED\n"
    first_id, first = _stage(c, cib, text, "first.csv")
    c.bank_imports.confirm(first_id, {first[0]["_import_row_id"]: {}})
    txn_id = c.db.scalar("SELECT transaction_id FROM bank_import_rows WHERE batch_id=?", (first_id,))
    c.transactions.void(txn_id, "entered by mistake")

    _, again = _stage(c, cib, text, "again.csv")
    row = again[0]
    assert row["_voided_earlier"] and not row["_possible_duplicate"]
    assert row["_default_match"] == "new"


def test_each_bank_statement_can_back_the_same_transfer_once(c):
    nbe = c.account_flows.open_account("NBE", "BANK", "2026-09-01", "50000")
    cib = c.account_flows.open_account("CIB", "BANK", "2026-09-01", "50000")
    first_id, first = _stage(c, nbe.id, "Date,Counterparty,Amount\n2026-09-02,CIB,-100\n", "nbe.csv")
    c.bank_imports.confirm(first_id, {first[0]["_import_row_id"]: {}})
    transfer_id = c.db.scalar("SELECT transaction_id FROM bank_import_rows WHERE batch_id=?", (first_id,))
    cib_before = c.reporting.account_balance(cib.id)

    second_id, second = _stage(c, cib.id, "Date,Counterparty,Amount\n2026-09-02,NBE,100\n", "cib.csv")
    assert [candidate["id"] for candidate in second[0]["_link_candidates"]] == [transfer_id]
    result = c.bank_imports.confirm(second_id, {second[0]["_import_row_id"]: {"match": f"link:{transfer_id}"}})
    assert result["linked"] == 1 and c.reporting.account_balance(cib.id) == cib_before


def test_a_link_to_an_entry_that_no_longer_matches_is_refused(c, setup):
    accounts, cats = setup
    cib = accounts["cib"].id
    other = c.transactions.record_outflow("2026-10-01", cib, "999", cats["EXP.PERSONAL.FOOD"].id)
    batch_id, rows = _stage(c, cib, "Date,Counterparty,Amount\n2026-10-01,Shop,-10\n")
    result = c.bank_imports.confirm(batch_id, {rows[0]["_import_row_id"]: {"match": f"link:{other.id}"}})
    assert result["errors"] and result["linked"] == 0


def test_upgrading_an_older_profile_keeps_its_import_rows(tmp_path, monkeypatch):
    older = tmp_path / "migrations"
    shutil.copytree(migrator._BUNDLED_MIGRATIONS_DIR, older)
    for later in older.glob("*.sql"):  # an older profile: every migration from 0040 on is still to come
        if int(later.name[:4]) >= 40:
            later.unlink()
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", older)
    db = Database(tmp_path / "old.db")
    migrator.migrate(db)
    seed(db)
    db.execute("INSERT INTO accounts(id,code,name,account_type,currency,cash_class_id,opening_date,"
               "created_at,updated_at) VALUES (7,'A-7','Old bank','BANK','EGP',"
               "(SELECT id FROM asset_classes WHERE code='CASH.BANK'),'2026-01-01','2026-01-01','2026-01-01')")
    db.execute("INSERT INTO bank_import_batches(id,account_id,file_hash,file_name,status,created_at) "
               "VALUES (3,7,'h','old.csv','REVIEW','2026-01-01')")
    db.execute("INSERT INTO bank_import_rows(id,batch_id,row_number,raw_json,bank_reference,status) "
               "VALUES (11,3,2,'{}','R-1','REVIEW')")
    db.conn.commit()

    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", migrator._BUNDLED_MIGRATIONS_DIR)
    applied = migrator.migrate(db)
    assert applied[0] == "0040_import_links (APPLIED)"
    assert "0043_other_asset_valuations (APPLIED)" in applied
    row = db.one("SELECT batch_id,account_id,bank_reference,status FROM bank_import_rows WHERE id=11")
    assert dict(row) == {"batch_id": 3, "account_id": 7, "bank_reference": "R-1", "status": "REVIEW"}
    db.close()


def test_review_screen_offers_link_post_as_new_and_skip(c, setup):
    from fastapi.testclient import TestClient

    from lightning.ui.web import create_app

    accounts, cats = setup
    cib = accounts["cib"].id
    manual = c.transactions.record_outflow("2026-10-01", cib, "450", cats["EXP.PERSONAL.FOOD"].id,
                                           counterparty="Carrefour")
    client = TestClient(create_app(c))
    batch_id, rows = _stage(c, cib, "Date,Counterparty,Amount\n2026-10-01,CARREFOUR MAADI,-450\n")
    row_id = rows[0]["_import_row_id"]

    page = client.get(f"/accounts/{cib}/import/{batch_id}")
    assert page.status_code == 200
    assert f'<select name="match_{row_id}"' in page.text and f'<option value="link:{manual.id}" selected>' in page.text
    assert said("Link to Carrefour · 2026-10-01") in page.text
    assert '<option value="new"' in page.text and "Not a duplicate — post as new" in page.text
    assert f'name="skip_{row_id}"' not in page.text  # one choice, not a second Skip box

    before = c.reporting.account_balance(cib)
    posted = client.post(f"/accounts/{cib}/import/{batch_id}/confirm",
                         data={f"match_{row_id}": f"link:{manual.id}"}, follow_redirects=False)
    assert posted.status_code == 200
    assert "0 posted, 1 linked to entries you already had" in posted.text
    assert c.reporting.account_balance(cib) == before


def test_upload_accepts_several_lightning_csv_files(c, setup):
    import httpx

    from lightning.ui.web import create_app

    accounts, _ = setup
    cib = accounts["cib"].id
    app = create_app(c)
    files = [
        ("file", ("first.csv", b"Date,Amount,Counterparty\n2026-10-02,-50,Shop\n", "text/csv")),
        ("file", ("second.csv", b"Date,Amount,Counterparty\n2026-10-03,-25,Cafe\n", "text/csv")),
    ]
    async def upload_files():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            return await client.post(f"/accounts/{cib}/import", files=files, follow_redirects=False)

    response = asyncio.run(upload_files())
    assert response.status_code == 303 and f"/accounts/{cib}/import/" in response.headers["location"]
    assert {row["file_name"] for row in c.bank_imports.waiting(cib)} == {"first.csv", "second.csv"}
