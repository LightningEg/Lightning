"""The starter workbook (NF-7AC1): a shell people fill in by hand, writing names; Lightning gives the codes back.

Sheets: Read me, Accounts, Categories, Entries (plus a hidden Lists sheet that feeds the drop-downs). Every data sheet
begins with a "Row" column: rows that say "Example" are examples, ignored on import (so they may be left or deleted),
and the last column of each data sheet (Code, Reference) is left empty for Lightning to fill after import (7AC3).
Amounts are plain numbers (negative = money out), dates are written as text yyyy-mm-dd, nothing is a formula: the file
passes the same safe reader as every workbook import (`workbook_import.read_workbook`).
"""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from lightning.accounts.domain import TYPE_SHORT, AccountType

SHEETS = ("Read me", "Accounts", "Categories", "Entries")
EXAMPLE = "Example"
ACCOUNT_TYPES = [TYPE_SHORT[t] for t in (AccountType.BANK, AccountType.CASH_AT_HAND, AccountType.CASH,
                                         AccountType.DEPOSIT, AccountType.BROKERAGE, AccountType.PHYSICAL_ASSET,
                                         AccountType.OTHER_ASSET)]
ACCOUNT_TYPES = list(dict.fromkeys(ACCOUNT_TYPES))  # "Cash" names two kinds of account; offer it once
GROUPS = ["Personal", "Work", "Investment"]
MONEY = ["Spending", "Income"]
COMMON_CURRENCIES = ["EGP", "USD", "EUR", "GBP", "SAR", "AED", "KWD", "QAR"]
ROWS = 300  # rows with a drop-down ready

HEADERS = {
    "Accounts": ["Row", "Name", "Type", "Currency", "Opening balance", "Opening date", "Code"],
    "Categories": ["Row", "Group", "Name", "Money", "Code"],
    "Entries": ["Row", "Date", "Account", "Category", "Counterparty", "Amount", "Currency", "Note", "Reference"],
}
EXAMPLES = {
    "Accounts": [
        (EXAMPLE, "Salary account", "Bank account", "EGP", 12500, "2026-01-01", None),
        (EXAMPLE, "Wallet", "Cash", "EGP", 800, "2026-01-01", None),
    ],
    "Categories": [
        (EXAMPLE, "Personal", "Pets", "Spending", None),
        (EXAMPLE, "Work", "Side projects", "Income", None),
    ],
    "Entries": [
        (EXAMPLE, "2026-01-28", "Salary account", "Salary", "My employer", 30000, "EGP", "January salary", None),
        (EXAMPLE, "2026-01-30", "Wallet", "Food & Groceries", "Corner shop", -185.5, "EGP", None, None),
        (EXAMPLE, "2026-02-02", "Salary account", "Pets", "Vet", -420, "EGP", "New category from the sheet above", None),
    ],
}
WIDTHS = {"Accounts": [9, 26, 18, 10, 16, 14, 14], "Categories": [9, 14, 26, 12, 22],
          "Entries": [9, 13, 24, 24, 24, 12, 10, 34, 16]}

READ_ME = [
    ("Lightning starter workbook", True),
    ("Fill in the Accounts, Categories and Entries sheets, then upload this file in Lightning (Settings > Move your data). "
     "Lightning shows you a preview first and changes nothing until you confirm.", False),
    ("", False),
    ("1. Write names, not numbers. Lightning gives every account, category and entry a code when you import. "
     "Leave the Code and Reference columns empty: you get them back in a file afterwards, and can then use them in later batches.", False),
    ("2. Rows that say Example are examples. Lightning ignores them, so you can overwrite them, delete them or leave them.", False),
    ("3. Accounts: one row per place your money sits (a bank account, a wallet). Opening balance is what it held on the opening date.", False),
    ("4. Categories: only the ones you want to add. Lightning already has the usual ones (Food & Groceries, Salary, Housing & Rent...): "
     "just use their names in the Entries sheet.", False),
    ("5. Entries: Amount is negative when money went out and positive when it came in. Write dates as yyyy-mm-dd (2026-03-15). "
     "Use an account and a category name from the other sheets, or one you already have in Lightning.", False),
    ("6. No formulas, macros or links: write plain values. Lightning never overwrites or deletes anything you already have.", False),
    ("", False),
    ("ورقة البداية في لايتنينج", True),
    ("املا شيتات الحسابات والتصنيفات والحركات، وبعدين ارفع الملف في لايتنينج (الإعدادات > انقل بياناتك). هتشوف معاينة الأول، "
     "ومفيش حاجة بتتغير غير لما تأكد.", False),
    ("اكتب أسماء، مش أرقام: لايتنينج هو اللي بيدّي كل حساب وتصنيف وحركة كود وقت الاستيراد. سيب خانتي Code و Reference فاضيين، "
     "وهترجعلك في ملف بعد الاستيراد. الصفوف اللي مكتوب فيها Example أمثلة وبتتجاهل. المبلغ بالسالب لو الفلوس خرجت وبالموجب لو دخلت، "
     "والتاريخ yyyy-mm-dd.", False),
]


def starter_workbook_bytes(*, currencies: list[str] | None = None, category_names: list[str] | None = None) -> bytes:
    """The workbook as .xlsx bytes. `currencies`: the profile's registered codes (the base first), else a common few;
    `category_names`: the names Lightning already has (offered in the Entries drop-down, other names still allowed)."""
    codes = list(dict.fromkeys([*(currencies or []), *COMMON_CURRENCIES]))
    workbook = Workbook()
    readme = workbook.active
    readme.title = SHEETS[0]
    readme.column_dimensions["A"].width = 110
    for index, (text, heading) in enumerate(READ_ME, start=1):
        cell = readme.cell(row=index, column=1, value=text or None)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if heading:
            cell.font = Font(bold=True, size=14, color="0D2233")
    for name in SHEETS[1:]:
        sheet = workbook.create_sheet(name)
        sheet.append(HEADERS[name])
        for row in EXAMPLES[name]:
            sheet.append(list(row))
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="0D2233")
            cell.fill = PatternFill("solid", fgColor="E6EEEC")
        for row in sheet.iter_rows(min_row=2, max_row=1 + len(EXAMPLES[name])):
            for cell in row:
                cell.font = Font(italic=True, color="6B7B86")
        for index, width in enumerate(WIDTHS[name], start=1):
            sheet.column_dimensions[chr(64 + index)].width = width
        sheet.freeze_panes = "A2"
    lists = workbook.create_sheet("Lists")
    columns = {"A": ACCOUNT_TYPES, "B": codes, "C": MONEY, "D": GROUPS, "E": sorted(set(category_names or []))}
    for letter, values in columns.items():
        for row, value in enumerate(values, start=1):
            lists[f"{letter}{row}"] = value
    lists.sheet_state = "hidden"

    def dropdown(sheet, column: str, source: str, *, strict: bool):
        check = DataValidation(type="list", formula1=source, allow_blank=True,
                               errorStyle="stop" if strict else "information", showErrorMessage=True,
                               errorTitle="Not in the list" if strict else "A new name",
                               error="Pick from the list." if strict else "This name is not in the list. Keep it if it is new.")
        sheet.add_data_validation(check)
        check.add(f"{column}2:{column}{ROWS}")

    dropdown(workbook["Accounts"], "C", f"Lists!$A$1:$A${len(ACCOUNT_TYPES)}", strict=True)
    dropdown(workbook["Accounts"], "D", f"Lists!$B$1:$B${len(codes)}", strict=True)
    dropdown(workbook["Categories"], "B", f"Lists!$D$1:$D${len(GROUPS)}", strict=True)
    dropdown(workbook["Categories"], "D", f"Lists!$C$1:$C${len(MONEY)}", strict=True)
    dropdown(workbook["Entries"], "C", f"Accounts!$B$2:$B${ROWS}", strict=False)
    if category_names:
        dropdown(workbook["Entries"], "D", f"Lists!$E$1:$E${len(set(category_names))}", strict=False)
    dropdown(workbook["Entries"], "G", f"Lists!$B$1:$B${len(codes)}", strict=True)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def starter_workbook(c) -> bytes:
    """The workbook for this profile: its currencies (base first) and its category names."""
    registered = [row["code"] for row in c.currencies.list()]
    names = [row["name"] for row in c.db.all(
        "SELECT name FROM categories WHERE active = 1 AND code NOT LIKE 'EXP.SYSTEM%' AND parent_id IS NOT NULL "
        "AND code LIKE 'EXP.%.%' ORDER BY name")]
    return starter_workbook_bytes(currencies=registered, category_names=names)
