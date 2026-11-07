"""NF-7AC1: the starter workbook opens through the safe reader and holds what people need to fill it in."""
from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import load_workbook

from lightning.bootstrap import build
from lightning.workflows import starter_workbook as sw
from lightning.workflows.workbook_import import read_workbook


@pytest.fixture(scope="module")
def ledger(tmp_path_factory):
    c = build(tmp_path_factory.mktemp("starter") / "t.db")
    yield c
    c.db.close()


@pytest.fixture(scope="module")
def data(ledger):
    return sw.starter_workbook(ledger)


def test_the_safe_reader_finds_every_sheet_heading_and_example(data):
    sheets = read_workbook(data)  # no macros, formulas or links: the same reader as every workbook import
    assert list(sheets)[:4] == list(sw.SHEETS)
    for name in ("Accounts", "Categories", "Entries"):
        assert sheets[name][0] == sw.HEADERS[name]
        examples = sheets[name][1:]
        assert 2 <= len(examples) <= 3 and all(row[0] == sw.EXAMPLE for row in examples)
        assert all(row[-1] is None for row in examples)  # the Code / Reference column is Lightning's to fill
    assert "ورقة البداية" in " ".join(str(r[0]) for r in sheets["Read me"])  # Arabic guidance beside the English


def test_examples_use_names_that_exist_or_are_made_by_the_sheet(ledger, data):
    sheets = read_workbook(data)
    built_in = {r["name"] for r in ledger.db.all("SELECT name FROM categories")}
    new = {row[2] for row in sheets["Categories"][1:]}
    accounts = {row[1] for row in sheets["Accounts"][1:]}
    for row in sheets["Entries"][1:]:
        assert row[3] in built_in | new and row[2] in accounts
        assert row[1][:4].isdigit() and row[1][4] == "-"  # dates are text yyyy-mm-dd, never an Excel serial
        assert float(row[5]) != 0 and row[6] in sw.COMMON_CURRENCIES


def test_dropdowns_are_ready_for_type_currency_group_money_and_the_entry_columns(data):
    workbook = load_workbook(BytesIO(data))
    assert workbook["Lists"].sheet_state == "hidden"
    lists = {c.column_letter: [x.value for x in workbook["Lists"][c.column_letter] if x.value] for c in workbook["Lists"][1]}
    assert "Bank account" in lists["A"] and lists["B"][0] == "EGP" and lists["C"] == sw.MONEY and lists["D"] == sw.GROUPS
    assert "Food & Groceries" in lists["E"] and "Salary" in lists["E"]
    found = {}
    for name in ("Accounts", "Categories", "Entries"):
        for check in workbook[name].data_validations.dataValidation:
            found[(name, str(check.sqref).split(":")[0][0])] = (check.formula1, check.errorStyle)
    assert {k: v[0].split("!")[0] for k, v in found.items()} == {
        ("Accounts", "C"): "Lists", ("Accounts", "D"): "Lists", ("Categories", "B"): "Lists", ("Categories", "D"): "Lists",
        ("Entries", "C"): "Accounts", ("Entries", "D"): "Lists", ("Entries", "G"): "Lists"}
    assert found[("Entries", "C")][1] == found[("Entries", "D")][1] == "information"  # new names stay allowed
    assert found[("Accounts", "C")][1] == "stop"


def test_the_profile_s_own_currencies_come_first_and_no_cell_is_a_formula(ledger):
    ledger.currencies.register("OMR", "Omani Rial")
    sheets = read_workbook(sw.starter_workbook(ledger))
    assert sheets["Lists"][0][1] == "EGP" and "OMR" in [r[1] for r in sheets["Lists"] if len(r) > 1]
    assert not any(str(v).startswith("=") for rows in sheets.values() for row in rows for v in row if v)


def test_a_builder_without_a_profile_still_works():
    sheets = read_workbook(sw.starter_workbook_bytes())
    assert [r[1] for r in sheets["Lists"] if len(r) > 1][:3] == ["EGP", "USD", "EUR"]
