from __future__ import annotations

import pytest

from lightning.core.errors import ConflictError, ValidationError


def test_alias_resolves_to_one_canonical_counterparty(c):
    cid = c.counterparties.create("Talabat", alias="Talabaat")
    assert c.counterparties.resolve("TALABAT")["id"] == cid
    assert c.counterparties.resolve("talabaat")["id"] == cid
    assert c.counterparties.suggestions("Talabaat") == []


def test_approximate_matches_are_suggestions_not_automatic_merges(c):
    cid = c.counterparties.create("Talabat")
    guesses = c.counterparties.suggestions("Talabaat")
    assert guesses and guesses[0][0] == "Talabat"
    assert c.counterparties.resolve("Talabaat") is None
    c.counterparties.add_alias(cid, "Talabaat")
    assert c.counterparties.resolve("Talabaat")["id"] == cid


def test_same_counterparty_cannot_be_created_twice(c):
    c.counterparties.create("Talabat")
    with pytest.raises(ConflictError):
        c.counterparties.create(" talabat ")


def test_transactions_link_confirmed_alias_to_canonical_record(c, setup):
    accounts, cats = setup
    cid = c.counterparties.create("Talabat", alias="Talabaat")
    txn = c.transactions.record_outflow(
        "2026-09-25", accounts["cib"].id, "125", cats["EXP.PERSONAL.FOOD"].id,
        counterparty="Talabaat",
    )
    row = c.db.one("SELECT counterparty_id FROM transactions WHERE id=?", (txn.id,))
    assert row["counterparty_id"] == cid


def test_rename_updates_linked_transaction_display_and_keeps_aliases(c, setup):
    accounts, cats = setup
    cid = c.counterparties.create("NBE", alias="National Bank")
    txn = c.transactions.record_outflow("2026-09-25", accounts["cib"].id, "10",
                                         cats["EXP.PERSONAL.FOOD"].id, counterparty="NBE")
    c.db.execute("UPDATE transactions SET counterparty_id=? WHERE id=?", (cid, txn.id))
    c.counterparties.rename(cid, "National Bank of Egypt")
    assert c.counterparties.resolve("NBE")["id"] == cid
    assert c.db.scalar("SELECT counterparty FROM transactions WHERE id=?", (txn.id,)) == "National Bank of Egypt"


def test_delete_unused_counterparty_removes_aliases_but_used_one_archives(c, setup):
    accounts, cats = setup
    unused = c.counterparties.create("Temporary", alias="Temp")
    assert c.counterparties.delete_or_archive(unused) is False
    assert c.counterparties.get(unused) is None
    assert c.counterparties.resolve("Temp") is None

    used = c.counterparties.create("Employer", alias="My Employer")
    txn = c.transactions.record_inflow("2026-09-25", accounts["cib"].id, "10",
                                       cats["EXP.WORK.SALARY"].id, counterparty="Employer")
    c.db.execute("UPDATE transactions SET counterparty_id=? WHERE id=?", (used, txn.id))
    assert c.counterparties.delete_or_archive(used) is True
    assert c.counterparties.get(used)["active"] == 0
    assert all(party["id"] != used for party in c.counterparties.list_active())
    assert any(party["id"] == used for party in c.counterparties.list_all())
    c.counterparties.set_active(used, True)
    assert c.counterparties.get(used)["active"] == 1


def test_usual_category_is_a_habit_not_one_odd_filing(c, setup):
    accounts, cats = setup
    cib = accounts["cib"].id
    food, software = cats["EXP.PERSONAL.FOOD"].id, cats["EXP.WORK.SOFTWARE"].id
    c.counterparties.create("Talabat", alias="Talabaat")
    # One filing is not a habit yet; two the same way are, and the alias counts with its counterparty.
    c.transactions.record_outflow("2026-09-01", cib, "10", food, counterparty="Talabat")
    assert "Talabat" not in c.transactions.usual_categories()
    c.transactions.record_outflow("2026-09-02", cib, "10", food, counterparty="Talabaat")
    assert c.transactions.usual_categories()["Talabat"] == {"category_id": food, "count": 2, "total": 2}
    # While it has under five, one odd filing leaves no usual category rather than a wrong one.
    c.transactions.record_outflow("2026-09-03", cib, "10", software, counterparty="Talabat")
    assert "Talabat" not in c.transactions.usual_categories()
    # Three of the last five make the habit, and that odd filing does not change it.
    for day in ("2026-09-04", "2026-09-05"):
        c.transactions.record_outflow(day, cib, "10", food, counterparty="Talabat")
    assert c.transactions.usual_categories()["Talabat"] == {"category_id": food, "count": 4, "total": 5}
    # Only the last five count: three newer filings elsewhere make a new habit.
    for day in ("2026-09-06", "2026-09-07", "2026-09-08"):
        c.transactions.record_outflow(day, cib, "10", software, counterparty="Talabat")
    assert c.transactions.usual_categories()["Talabat"] == {"category_id": software, "count": 3, "total": 5}


def test_usual_category_forgets_filings_older_than_180_days(c, setup):
    accounts, cats = setup
    cib = accounts["cib"].id
    food, software = cats["EXP.PERSONAL.FOOD"].id, cats["EXP.WORK.SOFTWARE"].id
    for day in ("2026-01-05", "2026-01-12", "2026-01-19"):
        c.transactions.record_outflow(day, cib, "10", food, counterparty="Cafe")
    assert c.transactions.usual_categories()["Cafe"]["category_id"] == food
    # Months later, two filings the same new way are the whole recent history.
    for day in ("2026-09-01", "2026-09-08"):
        c.transactions.record_outflow(day, cib, "10", software, counterparty="Cafe")
    assert c.transactions.usual_categories()["Cafe"] == {"category_id": software, "count": 2, "total": 2}


def test_a_counterparty_holds_up_to_20_aliases(c):
    cid = c.counterparties.create("Vodafone")
    for i in range(20):
        c.counterparties.add_alias(cid, f"Vodafone branch {i}")
    with pytest.raises(ValidationError, match="at most 20"):
        c.counterparties.add_alias(cid, "Vodafone branch 99")


def test_a_known_name_remembers_the_account_it_was_last_used_with(c, setup):
    """IV-12C: quick add fills the account a name was most recently paid from."""
    accounts, cats = setup
    food = cats["EXP.PERSONAL.FOOD"].id
    c.transactions.record_outflow("2026-09-01", accounts["cib"].id, "10", food, counterparty="Koshary")
    c.transactions.record_outflow("2026-09-02", accounts["wallet"].id, "10", food, counterparty="Koshary")
    assert c.transactions.last_accounts()["Koshary"] == accounts["wallet"].id
