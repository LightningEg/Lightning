"""A month checked against the bank cannot change by accident: edit, void, delete, create and import are refused
on or before the lock date, allowed after it and after unlocking."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app

D = Decimal
REFUSED = "checked against the bank"


@pytest.fixture
def locked(c, setup):
    accounts, cats = setup
    cib, food = accounts["cib"].id, cats["EXP.PERSONAL.FOOD"].id
    early = c.transactions.record_outflow("2026-09-10", cib, D("100"), food)
    late = c.transactions.record_outflow("2026-10-05", cib, D("40"), food)
    bank = c.reconciliation.balance(cib, "2026-09-30")
    c.reconciliation.confirm(cib, "2026-09-30", bank)
    return c, cib, food, early, late


def test_lock_follows_a_match_and_never_moves_backwards(locked):
    c, cib, _, _, _ = locked
    assert c.reconciliation.locked_through(cib) == "2026-09-30"
    c.reconciliation.confirm(cib, "2026-09-15", c.reconciliation.balance(cib, "2026-09-15"))
    assert c.reconciliation.locked_through(cib) == "2026-09-30"
    c.reconciliation.confirm(cib, "2026-10-31", c.reconciliation.balance(cib, "2026-10-31"))
    assert c.reconciliation.locked_through(cib) == "2026-10-31"
    with pytest.raises(ValidationError):
        c.reconciliation.confirm(cib, "2026-10-31", D("1"))     # no match, no lock


def test_edit_void_delete_create_are_refused_on_or_before_the_date(locked):
    c, cib, food, early, _ = locked
    with pytest.raises(ValidationError, match=REFUSED):
        c.transactions.update_money(early.id, "2026-09-10", cib, D("90"), food)
    with pytest.raises(ValidationError, match=REFUSED):
        c.transactions.void(early.id)
    with pytest.raises(ValidationError, match=REFUSED):
        c.transactions.delete_many([early.id])
    with pytest.raises(ValidationError, match=REFUSED):
        c.transactions.set_category([early.id], c.categories.get_by_code("EXP.PERSONAL.OTHER").id)
    with pytest.raises(ValidationError, match=REFUSED):
        c.transactions.record_outflow("2026-09-30", cib, D("5"), food)
    assert not c.transactions.get(early.id).is_void and c.reconciliation.balance(cib, "2026-09-30") == D("49900")


def test_a_note_edit_is_not_a_change_to_the_checked_figures(locked):
    c, cib, food, early, _ = locked
    c.transactions.update_metadata(early.id, "2026-09-10", "", "a note")
    assert c.transactions.get(early.id).notes == "a note"


def test_after_the_date_and_into_the_range(locked):
    c, cib, food, _, late = locked
    c.transactions.update_money(late.id, "2026-10-06", cib, D("45"), food)
    c.transactions.record_outflow("2026-10-01", cib, D("5"), food)
    with pytest.raises(ValidationError, match=REFUSED):      # moving a line into the checked range
        c.transactions.update_money(late.id, "2026-09-20", cib, D("45"), food)
    c.transactions.void(late.id)
    c.transactions.restore(late.id)


def test_other_accounts_are_not_locked(locked, setup):
    c, *_ = locked
    wallet = setup[0]["wallet"].id
    c.transactions.record_outflow("2026-09-10", wallet, D("5"), setup[1]["EXP.PERSONAL.FOOD"].id)


def test_unlock_allows_editing_again(locked):
    c, cib, food, early, _ = locked
    c.reconciliation.unlock(cib)
    assert c.reconciliation.locked_through(cib) == ""
    c.transactions.update_money(early.id, "2026-09-10", cib, D("90"), food)
    c.transactions.void(early.id)


def test_adjust_sets_the_lock(c, setup):
    wallet = setup[0]["wallet"].id
    c.reconciliation.adjust(wallet, "2026-09-30", D("1150"))
    assert c.reconciliation.locked_through(wallet) == "2026-09-30"


def test_import_rows_on_or_before_the_date_default_to_skip(locked):
    c, cib, _, _, _ = locked
    data = (b"Date,Counterparty,Amount,Category,Notes,Reference\n"
            b"2026-09-12,Old Shop,-70,,,R1\n2026-10-12,New Shop,-30,,,R2\n")
    batch_id, _ = c.bank_imports.stage(cib, "s.csv", data)
    _, rows = c.bank_imports.preview(batch_id)
    old, new = sorted(rows, key=lambda r: r["Date"])
    assert old["_locked"] and old["_default_match"] == "skip" and not old["_ready"]
    assert not new["_locked"] and new["_default_match"] == "new"
    forced = c.bank_imports.confirm(batch_id, {old["_import_row_id"]: {"match": "new"}})
    assert forced["errors"] and REFUSED in next(iter(forced["errors"].values()))


def test_the_account_page_shows_the_lock_and_unlock_works(locked):
    c, cib, food, early, _ = locked
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    page = client.get(f"/accounts/{cib}").text
    assert "Checked against the bank through" in page and "2026-09-30" in page and "Unlock" in page
    done = client.post(f"/accounts/{cib}/unlock", follow_redirects=False)
    assert done.status_code == 303 and c.reconciliation.locked_through(cib) == ""
    assert "Checked against the bank through" not in client.get(f"/accounts/{cib}").text


def test_the_check_page_offers_the_lock_when_it_matches(c, setup):
    cib = setup[0]["cib"].id
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    page = client.get(f"/accounts/{cib}/reconcile?date=2026-09-30&balance=50000").text
    assert "Lock through this day" in page
    assert client.post(f"/accounts/{cib}/reconcile/lock", data={"date": "2026-09-30", "balance": "50000"},
                       follow_redirects=False).status_code == 303
    assert c.reconciliation.locked_through(cib) == "2026-09-30"
    wrong = client.post(f"/accounts/{cib}/reconcile/lock", data={"date": "2026-10-30", "balance": "1"})
    assert wrong.status_code == 400
