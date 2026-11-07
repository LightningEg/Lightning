"""NF-7AC3: the result file holds every code, lists what was not imported, and imports nothing twice."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_starter_import import acct, entry, workbook  # noqa: E402

from lightning.bootstrap import build  # noqa: E402
from lightning.workflows import starter_import as si  # noqa: E402
from lightning.workflows import starter_result as sr  # noqa: E402
from lightning.workflows.workbook_import import read_workbook  # noqa: E402


@pytest.fixture
def c(tmp_path):
    ledger = build(tmp_path / "t.db")
    yield ledger
    ledger.db.close()


@pytest.fixture
def imported(c):
    data = workbook([acct("Salary account", bal=5000), acct("Wallet", "Cash", bal=200)],
                    [(None, "Personal", "Pets", "Spending", None)],
                    [entry("2026-01-05", "Salary account", "Food & Groceries", "Corner shop", -185.5),
                     entry("2026-01-06", "Salary account", "Pets", "Vet", -420, note="Checkup"),
                     entry("2026-01-07", "Wallet", "Mystery", "Client", 900)])  # one row cannot be placed
    result = si.confirm(c, data)
    return result, sr.result_for(c, result)


def test_every_row_gets_its_code_and_the_sheets_list_them(c, imported):
    result, data = imported
    sheets = read_workbook(data)
    at = lambda row, i: row[i] if len(row) > i else None  # noqa: E731 - the reader trims trailing empty cells
    accounts = {row[1]: at(row, 6) for row in sheets["Accounts"][1:]}
    assert accounts == {a.name: a.code for a in c.accounts.list() if a.name in ("Salary account", "Wallet")}
    assert at(sheets["Categories"][1], 4) == "EXP.PERSONAL.PETS"
    refs = [at(row, 8) for row in sheets["Entries"][1:]]
    assert refs[0] and refs[1] and refs[2] is None  # the unplaceable row has none
    assert refs[:2] == [r.ref for r in result.entries[:2]]
    codes = {(r[0], r[1]): (r[2], r[3]) for r in sheets["Codes"][1:]}
    assert codes[("Account", "Wallet")] == (accounts["Wallet"], "New") and codes[("Category", "Pets")][0] == "EXP.PERSONAL.PETS"
    assert sum(1 for r in sheets["Codes"][1:] if r[0] == "Entry") == 2
    assert sheets["Not imported"][1][0] == "Entries" and "category is not on the Categories sheet" in sheets["Not imported"][1][3]
    assert "Your import result" in str(sheets["Read me"][0][0])


def test_uploading_the_result_again_adds_nothing_twice(c, imported):
    _, data = imported
    count = c.db.scalar("SELECT COUNT(*) FROM transactions")
    preview = si.prepare(c, data)
    assert [r.status for r in preview.accounts] == [si.EXISTS] * 2 and [r.status for r in preview.categories] == [si.EXISTS]
    assert [r.status for r in preview.entries] == [si.EXISTS, si.EXISTS, si.ERROR]  # the bad row is still bad
    si.confirm(c, data)
    assert c.db.scalar("SELECT COUNT(*) FROM transactions") == count


def test_a_later_row_may_name_the_account_and_category_by_code(c, imported):
    result, _ = imported
    salary = next(a for a in result.accounts if a.name == "Salary account").code
    later = workbook([], [], [entry("2026-02-01", salary, "EXP.PERSONAL.PETS", "Vet", -100)])
    [row] = si.prepare(c, later).entries
    assert row.status == si.NEW
    made = si.confirm(c, later)
    assert made.entries[0].ref
    assert c.db.scalar("SELECT COUNT(*) FROM transactions WHERE counterparty = 'Vet'") == 2


def test_the_result_keeps_the_dropdowns_and_numbers_stay_numbers(c, imported):
    from io import BytesIO
    from openpyxl import load_workbook
    book = load_workbook(BytesIO(imported[1]))
    assert len(book["Entries"].data_validations.dataValidation) >= 3 and book["Lists"].sheet_state == "hidden"
    assert book["Entries"]["F2"].value == __import__("decimal").Decimal("-185.5") == -185.5 and book["Accounts"]["E2"].value == 5000
