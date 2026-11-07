"""The workbook handed back after a starter import (NF-7AC3): the person's rows with their codes filled in.

The Code and Reference columns hold each account's, category's and entry's code (`confirm` made it, or the profile
already had it), a Codes sheet lists them all, and a Not imported sheet lists every row that could not be placed with its
reason, so nothing is dropped silently. The file is a normal starter workbook: uploading it again adds nothing twice
(known names and references are recognised), and a later row may name an account or category by its code instead of
its name.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill

from lightning.workflows.starter_import import ERROR, EXISTS, NEW, DUPLICATE, Result
from lightning.workflows.starter_workbook import starter_workbook_bytes

LABEL = {NEW: "New", EXISTS: "Already there", DUPLICATE: "Already there", ERROR: "Not imported"}


def _cell(value):
    """A number back as a number (never text with a stray decimal), anything else as the text written."""
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return value
    return int(number) if number == number.to_integral_value() else number  # a Decimal: never a float


def result_workbook(result: Result, *, currencies: list[str] | None = None, category_names: list[str] | None = None) -> bytes:
    """The starter workbook again, holding this import's rows, codes, a Codes sheet and a Not imported sheet."""
    book = load_workbook(BytesIO(starter_workbook_bytes(currencies=currencies, category_names=category_names)))
    readme = book["Read me"]
    readme.insert_rows(1, 3)
    readme["A1"], readme["A2"] = "Your import result", ("Every row below now has its code. Codes sheet: all of them in one list. "
                                                         "Not imported: the rows Lightning could not place, with the reason. "
                                                         "Upload this file again and nothing is added twice.")
    readme["A1"].font = Font(bold=True, size=14, color="0D2233")
    for name, rows, code_of, columns in (
            ("Accounts", result.accounts, lambda r: r.code, ("Name", "Type", "Currency", "Opening balance", "Opening date")),
            ("Categories", result.categories, lambda r: r.code, ("Group", "Name", "Money")),
            ("Entries", result.entries, lambda r: r.ref,
             ("Date", "Account", "Category", "Counterparty", "Amount", "Currency", "Note"))):
        sheet = book[name]
        sheet.delete_rows(2, sheet.max_row)
        for row in rows:
            values = [row.raw.get(h, "") for h in columns]
            sheet.append([None, *[_cell(v) if h in ("Opening balance", "Amount") else (v or None)
                                  for h, v in zip(columns, values)], code_of(row) or None])
    codes = book.create_sheet("Codes")
    codes.append(["Kind", "Name", "Code", "Status"])
    problems = book.create_sheet("Not imported")
    problems.append(["Sheet", "Row", "Name", "Why"])
    for kind, rows, label, code_of in (
            ("Account", result.accounts, lambda r: r.name, lambda r: r.code),
            ("Category", result.categories, lambda r: r.name, lambda r: r.code),
            ("Entry", result.entries, lambda r: f"{r.date} {r.counterparty or r.category} {r.amount}".strip(),
             lambda r: r.ref)):
        for row in rows:
            if row.status == ERROR:
                problems.append([{"Account": "Accounts", "Category": "Categories", "Entry": "Entries"}[kind], row.line,
                                 label(row) or None, row.error])
            elif code_of(row):
                codes.append([kind, label(row), code_of(row), LABEL.get(row.status, "New")])
    for sheet in (codes, problems):
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="0D2233")
            cell.fill = PatternFill("solid", fgColor="E6EEEC")
        sheet.freeze_panes = "A2"
        for letter, width in zip("ABCD", (12, 40, 30, 60 if sheet is problems else 16)):
            sheet.column_dimensions[letter].width = width
    out = BytesIO()
    book.save(out)
    return out.getvalue()


def result_for(c, result: Result) -> bytes:
    """`result_workbook` with this profile's currencies and category names in the drop-downs."""
    registered = [row["code"] for row in c.currencies.list()]
    names = [row["name"] for row in c.db.all(
        "SELECT name FROM categories WHERE active = 1 AND code NOT LIKE 'EXP.SYSTEM%' AND parent_id IS NOT NULL "
        "AND code LIKE 'EXP.%.%' ORDER BY name")]
    return result_workbook(result, currencies=registered, category_names=names)
