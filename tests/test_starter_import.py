"""NF-7AC2: a filled starter workbook is previewed against the open profile, then created all or nothing."""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook

from lightning.bootstrap import build
from lightning.categories.domain import Movement
from lightning.workflows import starter_import as si
from lightning.workflows import starter_workbook as sw

D = Decimal


def workbook(accounts=(), categories=(), entries=(), skip_sheet=None) -> bytes:
    book = Workbook()
    book.active.title = "Read me"
    for name, rows in (("Accounts", accounts), ("Categories", categories), ("Entries", entries)):
        if name == skip_sheet:
            continue
        sheet = book.create_sheet(name)
        sheet.append(sw.HEADERS[name])
        for row in rows:
            sheet.append(list(row))
    out = BytesIO()
    book.save(out)
    return out.getvalue()


@pytest.fixture
def c(tmp_path):
    ledger = build(tmp_path / "t.db")
    yield ledger
    ledger.db.close()


def acct(name, kind="Bank account", cur="EGP", bal=1000, day="2026-01-01"):
    return (None, name, kind, cur, bal, day, None)


def entry(day, account, category, who, amount, cur="EGP", note=None, ref=None):
    return (None, day, account, category, who, amount, cur, note, ref)


def txn_count(c):
    return c.db.scalar("SELECT COUNT(*) FROM transactions")


def test_a_clean_file_is_previewed_then_created_with_codes(c):
    data = workbook([acct("Salary account", bal=5000), acct("Wallet", "Cash", bal=200)],
                    [(None, "Personal", "Pets", "Spending", None), (None, "Work", "Side projects", "Income", None)],
                    [entry("2026-01-05", "Salary account", "Food & Groceries", "Corner shop", -185.5),
                     entry("2026-01-06", "Salary account", "Pets", "Vet", -420, note="Checkup"),
                     entry("2026-01-07", "Wallet", "Side projects", "Client", 900)])
    before = txn_count(c)
    preview = si.prepare(c, data)
    assert txn_count(c) == before and not preview.problems  # the preview changes nothing
    assert [r.status for r in preview.accounts] == [si.NEW] * 2 and preview.count("categories", si.NEW) == 2
    result = si.confirm(c, data)
    assert [a.code for a in result.accounts] and all(r.ref for r in result.entries)
    salary = next(a for a in c.accounts.list() if a.name == "Salary account")
    assert salary.code == result.accounts[0].code and c.transactions.opening_balance(salary.id) == D("5000")
    pets = c.categories.get_by_code(result.categories[0].code)
    assert pets.name == "Pets" and pets.movement == Movement.OUTFLOW
    assert c.categories.get_by_code(result.categories[1].code).movement == Movement.INFLOW
    assert txn_count(c) == before + 3 + 2  # three entries and two opening balances


def test_examples_and_blank_rows_are_ignored(c):
    data = workbook([("Example", "Salary account", "Bank account", "EGP", 12500, "2026-01-01", None), (None,) * 7], [], [])
    preview = si.prepare(c, data)
    assert preview.accounts == [] and preview.nothing_to_do


def test_names_that_exist_are_used_not_duplicated(c):
    first = workbook([acct("Salary account")])
    si.confirm(c, first)
    again = workbook([acct("salary ACCOUNT"), acct("Wallet", "Cash")],
                     [(None, "Personal", "Pets", "Spending", None)],
                     [entry("2026-01-05", "Salary account", "Food & Groceries", "Shop", -50)])
    preview = si.prepare(c, again)
    assert [r.status for r in preview.accounts] == [si.EXISTS, si.NEW] and preview.accounts[0].code
    accounts_before = len(c.accounts.list())
    si.confirm(c, again)
    assert len(c.accounts.list()) == accounts_before + 1


@pytest.mark.parametrize("entries, message", [
    ([entry("2026-01-05", "Nowhere", "Food & Groceries", "x", -5)], "account is not on the Accounts sheet"),
    ([entry("2026-02-31", "Salary account", "Food & Groceries", "x", -5)], "date"),
    ([entry("2026-01-05", "Salary account", "Food & Groceries", "x", "abc")], "number"),
    ([entry("2026-01-05", "Salary account", "Food & Groceries", "x", 0)], "cannot be zero"),
    ([entry("2026-01-05", "Salary account", "Food & Groceries", "x", -5.1234567)], "decimal"),
    ([entry("2026-01-05", "Salary account", "Mystery", "x", -5)], "category is not on the Categories sheet"),
    ([entry("2026-01-05", "Salary account", "Transportation", "x", -5)], "more than one group"),
    ([entry("2026-01-05", "Salary account", "Salary", "x", -5)], "income category"),
    ([entry("2026-01-05", "Salary account", "Adjustment", "x", -5)], "System categories"),
    ([entry("2026-01-05", "Salary account", "Food & Groceries", "x", -5, cur="USD")], "holds EGP"),
    ([entry("2026-01-05", "Salary account", "Food & Groceries", "x", -5, ref="NOPE-1")], "not in this profile"),
])
def test_rows_that_cannot_be_placed_are_listed_with_a_reason_and_never_guessed(c, entries, message):
    data = workbook([acct("Salary account")], [], entries)
    preview = si.prepare(c, data)
    [bad] = preview.entries
    assert bad.status == si.ERROR and message in bad.error, bad.error
    before = txn_count(c)
    result = si.confirm(c, data)
    assert result.skipped == [bad] and txn_count(c) == before + 1  # only the opening balance was made


def test_an_ambiguous_name_can_be_written_with_its_group(c):
    data = workbook([acct("Salary account")], [], [entry("2026-01-05", "Salary account", "Work / Transportation", "Bus", -20)])
    assert si.prepare(c, data).entries[0].status == si.NEW


@pytest.mark.parametrize("account, message", [
    (acct("A", kind="Spaceship"), "account type"),
    (acct("A", cur="ZZZ"), "not registered"),
    (acct("A", bal=-5), "cannot be negative"),
    (acct("A", day="2999-01-01"), "future"),
    (acct("A", day="soon"), "date"),
    (acct("A", kind="Certificates", bal=100), "starts empty"),
    (acct(""), "name"),
])
def test_bad_account_rows(c, account, message):
    [row] = si.prepare(c, workbook([account])).accounts
    assert row.status == si.ERROR and message in row.error, row.error


def test_an_entry_on_a_bad_account_row_waits_for_that_row_to_be_fixed(c):
    data = workbook([acct("A", bal=-5)], [], [entry("2026-01-05", "A", "Food & Groceries", "x", -5)])
    [bad] = si.prepare(c, data).entries
    assert bad.status == si.ERROR and "account row has a problem" in bad.error


def test_bad_category_rows(c):
    rows = [(None, "Hobbies", "Chess", "Spending", None), (None, "Personal", "Chess", "Both", None),
            (None, "Personal", "", "Spending", None), (None, "Personal", "Chess", "Spending", None),
            (None, "Personal", "chess", "Spending", None)]
    result = si.prepare(c, workbook([], rows)).categories
    assert [r.status for r in result] == [si.ERROR, si.ERROR, si.ERROR, si.NEW, si.ERROR] and "listed twice" in result[4].error
    assert si.prepare(c, workbook([], [(None, "Personal", "food & groceries", "Spending", None)])).categories[0].status == si.EXISTS


def test_a_repeated_upload_posts_nothing_twice(c):
    data = workbook([acct("Salary account")], [],
                    [entry("2026-01-05", "Salary account", "Food & Groceries", "Shop", -50),
                     entry("2026-01-05", "Salary account", "Food & Groceries", "Shop", -50)])  # two real coffees
    first = si.confirm(c, data)
    assert [r.status for r in first.entries] == [si.NEW, si.NEW]
    count = txn_count(c)
    again = si.prepare(c, data)
    assert [r.status for r in again.entries] == [si.DUPLICATE, si.DUPLICATE] and again.entries[0].ref
    si.confirm(c, data)
    assert txn_count(c) == count
    third = workbook([acct("Salary account")], [], [entry("2026-01-05", "Salary account", "Food & Groceries", "Shop", -50)] * 3)
    assert [r.status for r in si.prepare(c, third).entries] == [si.DUPLICATE, si.DUPLICATE, si.NEW]


def test_an_entry_with_its_reference_is_known_not_new(c):
    first = si.confirm(c, workbook([acct("Salary account")], [], [entry("2026-01-05", "Salary account", "Food & Groceries", "Shop", -50)]))
    ref = first.entries[0].ref
    row = entry(None, None, None, None, None, ref=ref)
    [known] = si.prepare(c, workbook([], [], [row])).entries
    assert known.status == si.EXISTS and known.ref == ref


def test_a_failure_while_creating_rolls_everything_back(c, monkeypatch):
    data = workbook([acct("Salary account")], [(None, "Personal", "Pets", "Spending", None)],
                    [entry("2026-01-05", "Salary account", "Pets", "Vet", -420)])
    names_before = {a.name for a in c.accounts.list()}

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")
    monkeypatch.setattr(c.transactions, "record_outflow", boom)
    with pytest.raises(RuntimeError):
        si.confirm(c, data)
    assert {a.name for a in c.accounts.list()} == names_before
    assert not [x for x in c.categories.tree() if x.name == "Pets"]


def test_a_file_that_is_not_a_starter_workbook_is_refused_plainly(c):
    with pytest.raises(ValueError, match="no Entries sheet"):
        si.prepare(c, workbook(skip_sheet="Entries"))
    with pytest.raises(ValueError):
        si.prepare(c, b"not a workbook")
    broken = Workbook()
    broken.active.title = "Accounts"
    broken.active.append(["Row", "Name"])
    out = BytesIO()
    broken.save(out)
    with pytest.raises(ValueError, match="no Type column"):
        si.prepare(c, out.getvalue())


def test_the_template_itself_imports_nothing(c):
    preview = si.prepare(c, sw.starter_workbook(c))
    assert preview.nothing_to_do and not preview.problems
    assert si.confirm(c, sw.starter_workbook(c)).entries == []


def test_each_existing_entry_answers_one_duplicate_row_with_its_own_reference(c):
    rows = [entry("2026-01-05", "Salary account", "Food & Groceries", "Shop", -50)] * 2
    made = si.confirm(c, workbook([acct("Salary account")], [], rows))
    again = si.prepare(c, workbook([acct("Salary account")], [], rows))
    assert sorted(r.ref for r in again.entries) == sorted(r.ref for r in made.entries) and len({r.ref for r in again.entries}) == 2
