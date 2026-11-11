"""NF-7AO: bank messages Lightning is sure about save themselves through the review's own post, marked and undoable;
everything else waits for the owner (owner decision 2026-11-09, r31 F3). Each condition that fails sends the
message to review; the same payment typed by hand first is linked, never posted twice."""
from __future__ import annotations

from datetime import date, datetime

import pytest

NBE_UBER = ("NBE", "تم خصم 147.87 EGP من بطاقة الخصم المباشر رقم 2093 عند Uber                  Dow يوم 06/10/26 "
                   "الساعه 11:13 المتاح 3512.40", datetime(2026, 10, 6, 11, 13))
NBE_NEW_SHOP = ("NBE", "تم خصم 88.00 EGP من بطاقة الخصم المباشر رقم 2093 عند ZOOBA                 Dow يوم 06/10/26 "
                       "الساعه 12:00 المتاح 3424.40", datetime(2026, 10, 6, 12, 0))
# A wording no bank pattern knows: read by the general rule, so marked to check.
GENERAL_UBER = ("BankX", "Purchase of EGP 60.00 with card ending 2093 at Uber on 06/10/2026",
                datetime(2026, 10, 6, 13, 0))


@pytest.fixture
def known(c, setup):
    """CIB Current is card …2093, and Uber is a payee filed under Transport by habit."""
    accounts, _ = setup
    transport = c.categories.get_by_code("EXP.PERSONAL.TRANSPORT")
    c.counterparties.create("Uber", transport.id)
    c.sms_imports.assign("2093", accounts["cib"].id)
    return accounts["cib"], transport


def _posted(c, account_id):
    return [t for t in c.transactions.find(__import__("lightning.transactions.domain", fromlist=["TxnFilter"])
                                           .TxnFilter(account_id=account_id, limit=50))[0] if t.amount < 0]


def test_a_sure_message_saves_itself_and_the_rest_wait(c, known):
    cib, transport = known
    result = c.sms_imports.read([NBE_UBER, NBE_NEW_SHOP])
    assert result["saved"] == 1
    saved = c.sms_imports.saved()
    assert [(s["who"], s["amount"], s["linked"]) for s in saved] == [("Uber", "-147.87", False)]
    txn = c.transactions.get_by_ref(saved[0]["ref"])
    assert txn.lines and any(line.category_id == transport.id for line in txn.lines)
    _, rows = c.bank_imports.preview(result["staged"][cib.id])
    waiting = [r for r in rows if r["_status"] == "REVIEW"]
    assert [r["Counterparty"] for r in waiting] == ["ZOOBA"]  # a payee seen for the first time asks


def test_the_general_rule_never_saves_itself(c, known):
    result = c.sms_imports.read([GENERAL_UBER])
    assert result["staged"] and result["saved"] == 0 and c.sms_imports.saved() == []


def test_an_ending_not_assigned_yet_waits(c, setup):
    c.counterparties.create("Uber", c.categories.get_by_code("EXP.PERSONAL.TRANSPORT").id)
    result = c.sms_imports.read([NBE_UBER])
    assert result["saved"] == 0 and result["waiting"] == 1
    c.sms_imports.assign("2093", setup[0]["cib"].id)  # answered now: it goes to review, never posts unseen
    assert c.sms_imports.saved() == []


def test_a_possible_duplicate_waits(c, known):
    """The same date and amount from another message waiting in review: neither posts unnoticed."""
    cib, _ = known
    c.bank_imports.stage(cib.id, "statement.csv", b"Date,Amount,Counterparty\n2026-10-06,-147.87,Uber Egypt\n")
    assert c.sms_imports.read([NBE_UBER])["saved"] == 0


def test_the_same_payment_typed_by_hand_is_linked_not_posted_twice(c, known):
    """7AO3: the entry typed before its message arrived is the message's; the ledger keeps one payment."""
    cib, transport = known
    typed = c.transactions.record_outflow("2026-10-06", cib.id, "147.87", transport.id, counterparty="Uber")
    before = len(_posted(c, cib.id))
    result = c.sms_imports.read([NBE_UBER])
    assert result["saved"] == 1 and len(_posted(c, cib.id)) == before
    saved = c.sms_imports.saved()[0]
    assert saved["linked"] and saved["ref"] == typed.ref
    c.sms_imports.undo_saved(saved["ref"])  # undoing a link keeps the typed entry
    assert not c.transactions.get(typed.id).is_void


def test_undo_deletes_the_entry_and_the_message_waits_on_its_review(c, known):
    cib, _ = known
    c.sms_imports.read([NBE_UBER])
    ref = c.sms_imports.saved()[0]["ref"]
    account_id, batch_id = c.sms_imports.undo_saved(ref)
    assert account_id == cib.id and c.transactions.get_by_ref(ref).is_void
    _, rows = c.bank_imports.preview(batch_id)
    assert [r["_status"] for r in rows] == ["REVIEW"] and c.sms_imports.saved() == []
    assert c.bank_imports.waiting(cib.id)


def test_home_says_what_saved_itself_and_from_sms_lists_it_with_undo(c, known):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    from lightning.workflows.review import ReviewInbox
    c.sms_imports.read([NBE_UBER])
    on = date.fromisoformat(c.sms_imports.saved()[0]["at"])
    items = [i for i in ReviewInbox(c).items(on) if i["label"] == "Saved from SMS"]
    assert len(items) == 1 and items[0]["href"] == "/sms#saved" and items[0]["action"] == "Undo"
    client = TestClient(create_app(c))
    page = client.get("/sms").text
    ref = c.sms_imports.saved()[0]["ref"]
    assert 'id="saved"' in page and f'href="/t/{ref}"' in page and 'action="/sms/undo"' in page
    assert client.get(f"/t/{ref}").status_code == 200
    undone = client.post("/sms/undo", data={"ref": ref})
    assert "/import/" in str(undone.url) and c.sms_imports.saved() == []
    assert not [i for i in ReviewInbox(c).items(on) if i["label"] == "Saved from SMS"]
