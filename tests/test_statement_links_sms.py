"""NF-3AZ2: a statement row links to the payment already recorded from an SMS: one posting, provenance kept,
and an ambiguous match is a question, not a guess."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

SAMPLES = json.loads((Path(__file__).parent / "fixtures" / "bank_sms.json").read_text(encoding="utf-8"))
UBER = SAMPLES["samples"][6]


def _post_sms(c, accounts, sample=UBER):
    c.sms_imports.read([(sample["sender"], sample["text"], datetime.fromisoformat(sample["received"]))])
    ending = c.sms_imports.waiting()[0]["ending"]
    batch_id = c.sms_imports.assign(ending, accounts["cib"].id)
    _, rows = c.bank_imports.preview(batch_id)
    cat = rows[0]["_category_id"]
    c.bank_imports.confirm(batch_id, {rows[0]["_import_row_id"]: {"match": "new", "category_id": cat or ""}})
    return rows[0]


def test_a_statement_after_a_captured_sms_offers_the_link_once(c, setup):
    accounts, cats = setup
    sms = _post_sms(c, accounts)
    cib = accounts["cib"].id
    count = c.db.scalar("SELECT count(*) FROM transactions")
    day, amount = sms["Date"], sms["Amount"]
    batch_id, _ = c.bank_imports.stage(cib, "statement.csv", f"Date,Counterparty,Amount\n{day},UBER *TRIP,{amount}\n".encode())
    _, rows = c.bank_imports.preview(batch_id)
    row = rows[0]
    assert len(row["_link_candidates"]) == 1
    cand = row["_link_candidates"][0]
    assert cand["from_sms"] and "SMS" in cand["source_files"]
    assert row["_default_match"] == f"link:{cand['id']}" and row["_link_question"] is None
    result = c.bank_imports.confirm(batch_id, {row["_import_row_id"]: {"match": row["_default_match"]}})
    assert result["linked"] == 1 and result["posted"] == 0
    assert c.db.scalar("SELECT count(*) FROM transactions") == count
    # The SMS row and the statement row both stay as sources of the one payment.
    assert c.db.scalar("SELECT count(*) FROM bank_import_rows WHERE transaction_id=?", (cand["id"],)) == 2


def test_two_sms_payments_that_fit_one_statement_row_are_a_question(c, setup):
    accounts, cats = setup
    cib = accounts["cib"].id
    sms = _post_sms(c, accounts)
    day, amount = sms["Date"], sms["Amount"]
    c.transactions.record_outflow(day, cib, amount.lstrip("-"), cats["EXP.PERSONAL.FOOD"].id, counterparty="Other")
    batch_id, _ = c.bank_imports.stage(cib, "statement.csv", f"Date,Counterparty,Amount\n{day},UBER,{amount}\n".encode())
    row = c.bank_imports.preview(batch_id)[1][0]
    assert len(row["_link_candidates"]) == 2
    assert row["_default_match"] == "skip" and row["_link_question"]


def test_the_review_page_says_the_payment_came_from_an_sms(c, setup):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, _ = setup
    sms = _post_sms(c, accounts)
    batch_id, _ = c.bank_imports.stage(accounts["cib"].id, "statement.csv",
                                       f"Date,Counterparty,Amount\n{sms['Date']},UBER,{sms['Amount']}\n".encode())
    page = TestClient(create_app(c)).get(f"/accounts/{accounts['cib'].id}/import/{batch_id}?rows=all")
    assert page.status_code == 200 and "recorded from your SMS" in page.text
