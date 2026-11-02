"""7A: a bank row that is a transfer plus its fee posts as the transfer and a separate fee expense."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lightning.ui.web import create_app

FEE_CODE = "EXP.PERSONAL.FEES"


def _balance(c, account) -> float:
    return c.db.scalar("SELECT COALESCE(SUM(le.quantity_e6),0) FROM ledger_entries le JOIN transactions t "
                       "ON t.id=le.transaction_id WHERE le.account_id=? AND t.status='POSTED'",
                       (account.id,)) / 1_000_000


def _fee_postings(c) -> int:
    return c.db.scalar("SELECT COUNT(DISTINCT t.id) FROM transactions t JOIN ledger_entries le ON le.transaction_id=t.id "
                       "JOIN categories k ON k.id=le.category_id WHERE k.code=? AND t.status='POSTED'", (FEE_CODE,))


def test_a_transfer_row_splits_into_the_transfer_and_its_fee(c):
    nbe = c.account_flows.open_account("NBE", "BANK", "2026-09-01", "50000")
    cib = c.account_flows.open_account("CIB", "BANK", "2026-09-01", "50000")
    batch_id, _ = c.bank_imports.stage(nbe.id, "nbe.csv", b"Date,Counterparty,Amount\n2026-09-02,CIB,-1005\n")
    _, rows = c.bank_imports.preview(batch_id)
    result = c.bank_imports.confirm(batch_id, {rows[0]["_import_row_id"]: {"fee": "5"}})
    assert result["posted"] == 1 and not result["errors"]
    assert _balance(c, nbe) == 50000 - 1005 and _balance(c, cib) == 50000 + 1000
    assert _fee_postings(c) == 1


def test_no_fee_entered_posts_the_whole_amount_as_the_transfer(c):
    nbe = c.account_flows.open_account("NBE", "BANK", "2026-09-01", "50000")
    cib = c.account_flows.open_account("CIB", "BANK", "2026-09-01", "50000")
    batch_id, _ = c.bank_imports.stage(nbe.id, "nbe.csv", b"Date,Counterparty,Amount\n2026-09-02,CIB,-1005\n")
    _, rows = c.bank_imports.preview(batch_id)
    c.bank_imports.confirm(batch_id, {rows[0]["_import_row_id"]: {}})
    assert _balance(c, cib) == 50000 + 1005 and _fee_postings(c) == 0


def test_a_bad_fee_is_refused_and_posts_nothing(c):
    nbe = c.account_flows.open_account("NBE", "BANK", "2026-09-01", "50000")
    c.account_flows.open_account("CIB", "BANK", "2026-09-01", "50000")
    batch_id, _ = c.bank_imports.stage(nbe.id, "nbe.csv", b"Date,Counterparty,Amount\n2026-09-02,CIB,-100\n")
    _, rows = c.bank_imports.preview(batch_id)
    rid = rows[0]["_import_row_id"]
    for bad in ("100", "250", "-3", "abc"):
        result = c.bank_imports.confirm(batch_id, {rid: {"fee": bad}})
        assert rid in result["errors"] and result["posted"] == 0, bad
    assert _fee_postings(c) == 0
    assert c.bank_imports.confirm(batch_id, {rid: {}})["posted"] == 1


def test_review_shows_the_fee_well_on_transfer_rows_only_and_posts_the_split(c):
    nbe = c.account_flows.open_account("NBE", "BANK", "2026-09-01", "50000")
    c.account_flows.open_account("CIB", "BANK", "2026-09-01", "50000")
    client = TestClient(create_app(c))
    batch_id, _ = c.bank_imports.stage(
        nbe.id, "nbe.csv", b"Date,Counterparty,Amount\n2026-09-02,CIB,-1005\n2026-09-03,Shop,-20\n")
    page = client.get(f"/accounts/{nbe.id}/import/{batch_id}")
    assert page.status_code == 200 and page.text.count('name="fee_') == 1
    _, rows = c.bank_imports.preview(batch_id)
    form = {}
    for r in rows:
        rid = r["_import_row_id"]
        form |= {f"date_{rid}": r["Date"], f"amount_{rid}": r["Amount"], f"counterparty_{rid}": r["Counterparty"],
                 f"notes_{rid}": ""}
    form[f"fee_{rows[0]['_import_row_id']}"] = "5"
    done = client.post(f"/accounts/{nbe.id}/import/{batch_id}/confirm", data=form)
    assert done.status_code == 200 and "Import complete" in done.text
    assert _fee_postings(c) == 1
