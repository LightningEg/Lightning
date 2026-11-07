"""Read a filled starter workbook into the open profile (NF-7AC2): a preview first, then one all-or-nothing write.

`prepare` reads nothing but the file and the profile and changes nothing: it lists what would be created, what already
exists and which rows could not be placed, each with its reason. `confirm` runs `prepare` again on the same bytes
(the profile may have changed since the preview), then creates the new accounts, the new categories and the entries in
one settled write; any failure rolls all of it back. Nothing is ever overwritten or deleted. Rows marked `Example` and
blank rows are ignored. Names are matched, never guessed: an unknown or ambiguous name is an error row, not a new record,
except for categories, which the Categories sheet creates on purpose. Money goes through the normal services.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from lightning.accounts.domain import OFFERED_TYPES, TYPE_LABELS, TYPE_SHORT, AccountType
from lightning.categories.domain import Direction, Movement
from lightning.core.dates import fmt_date, parse_date, today
from lightning.core.errors import LightningError
from lightning.core.money import ZERO, check_places, to_decimal
from lightning.transactions.domain import TxnSource
from lightning.workflows.save import settled_write
from lightning.workflows.starter_workbook import EXAMPLE, HEADERS
from lightning.workflows.workbook_import import read_workbook

GROUP_PARENT = {"personal": "EXP.PERSONAL", "work": "EXP.WORK", "investment": "EXP.INVEST"}
NEW, EXISTS, DUPLICATE, ERROR = "new", "exists", "duplicate", "error"


@dataclass
class AccountRow:
    line: int
    name: str
    account_type: str = ""
    currency: str = ""
    balance: Decimal = ZERO
    date: str = ""
    status: str = NEW
    error: str = ""
    code: str = ""  # an existing account's code, or the new one after confirm


@dataclass
class CategoryRow:
    line: int
    name: str
    group: str = ""
    money: str = ""
    status: str = NEW
    error: str = ""
    code: str = ""
    parent_code: str = ""


@dataclass
class EntryRow:
    line: int
    date: str = ""
    account: str = ""
    category: str = ""
    counterparty: str = ""
    amount: Decimal = ZERO
    currency: str = ""
    note: str = ""
    status: str = NEW
    error: str = ""
    ref: str = ""  # an existing entry's reference (duplicate / exists), or the new one after confirm
    account_id: int | None = None
    category_key: str = ""


@dataclass
class Preview:
    accounts: list[AccountRow] = field(default_factory=list)
    categories: list[CategoryRow] = field(default_factory=list)
    entries: list[EntryRow] = field(default_factory=list)

    def count(self, rows: str, status: str) -> int:
        return sum(1 for r in getattr(self, rows) if r.status == status)

    @property
    def problems(self) -> list:
        return [r for rows in (self.accounts, self.categories, self.entries) for r in rows if r.status == ERROR]

    @property
    def nothing_to_do(self) -> bool:
        return not any(r.status == NEW for rows in (self.accounts, self.categories, self.entries) for r in rows)


def _type_lookup() -> dict[str, str]:
    found = {}
    for kind in OFFERED_TYPES:
        for text in (kind.value, TYPE_SHORT[kind], TYPE_LABELS[kind]):
            found[text.casefold()] = kind.value
    found["cash"] = AccountType.CASH_AT_HAND.value
    found["cash wallet"] = AccountType.CASH.value
    return found


def _sheet(sheets: dict, name: str) -> list[tuple[int, dict]]:
    """The data rows of a sheet as (line number, {heading: text}), examples and blank rows left out."""
    key = next((k for k in sheets if k.strip().casefold() == name.casefold()), None)
    if key is None:
        raise ValueError(f"The workbook has no {name} sheet. Start from the Lightning starter workbook.")
    rows = sheets[key]
    if not rows:
        raise ValueError(f"The {name} sheet is empty. Start from the Lightning starter workbook.")
    headings = [str(h or "").strip().casefold() for h in rows[0]]
    missing = [h for h in HEADERS[name] if h.casefold() not in headings]
    if missing:
        raise ValueError(f"The {name} sheet has no {missing[0]} column. Start from the Lightning starter workbook.")
    out = []
    for offset, values in enumerate(rows[1:], start=2):
        cells = {headings[i]: ("" if v is None else str(v).strip()) for i, v in enumerate(values) if i < len(headings)}
        if cells.get(HEADERS[name][0].casefold(), "").casefold() == EXAMPLE.casefold():
            continue
        if any(v for k, v in cells.items() if k != HEADERS[name][0].casefold()):
            out.append((offset, {h: cells.get(h.casefold(), "") for h in HEADERS[name]}))
    return out


def prepare(c, data: bytes) -> Preview:
    """The preview. Raises ValueError for a file that is not a starter workbook at all."""
    if getattr(c, "is_journal", False):
        raise ValueError("This profile edits on several devices; the starter workbook cannot be imported into it yet.")
    sheets = read_workbook(data)
    preview = Preview()
    registered = {row["code"] for row in c.currencies.list()}
    types = _type_lookup()
    existing = {a.name.casefold(): a for a in c.accounts.list()} | {a.code.casefold(): a for a in c.accounts.list()}

    seen: set[str] = set()
    sheet_accounts: dict[str, AccountRow] = {}
    for line, row in _sheet(sheets, "Accounts"):
        item = AccountRow(line, row["Name"])
        preview.accounts.append(item)
        try:
            if not item.name:
                raise ValueError("Write the account's name.")
            if item.name.casefold() in seen:
                raise ValueError("This name is listed twice.")
            seen.add(item.name.casefold())
            if item.name.casefold() in existing:
                item.status, item.code = EXISTS, existing[item.name.casefold()].code
                sheet_accounts[item.name.casefold()] = item
                continue
            item.account_type = types.get(row["Type"].casefold(), "")
            if not item.account_type:
                raise ValueError("Pick the account type from the list.")
            item.currency = (row["Currency"] or c.transactions.base_currency).upper()
            if item.currency not in registered:
                raise ValueError(f"Currency {item.currency} is not registered. Add it in Settings first.")
            item.balance = to_decimal(row["Opening balance"] or "0", "opening balance")
            check_places(item.balance, c.assets.cash_asset(item.currency).quantity_decimals, "opening balance")
            if item.balance < ZERO:
                raise ValueError("An opening balance cannot be negative.")
            if item.balance != ZERO and item.account_type in ("DEPOSIT", "GAMEYA"):
                raise ValueError("This kind of account starts empty. Record what it holds as entries.")
            day = parse_date(row["Opening date"], "opening date")
            if day > today():
                raise ValueError("The opening date cannot be in the future.")
            item.date = fmt_date(day)
            sheet_accounts[item.name.casefold()] = item
        except (ValueError, LightningError) as error:
            item.status, item.error = ERROR, str(error)
            if item.name:
                sheet_accounts.setdefault(item.name.casefold(), item)  # its entries wait for it, not "unknown account"

    by_name, by_code, parents = {}, {}, {}
    for cat in c.categories.tree():
        parents[cat.code] = cat
        if cat.depth >= 2:
            by_name.setdefault(cat.name.casefold(), []).append(cat)
            by_name.setdefault(f"{cat.code.split('.')[1].casefold()} / {cat.name.casefold()}", []).append(cat)
            by_code[cat.code.casefold()] = cat
    new_categories: dict[str, CategoryRow] = {}
    for line, row in _sheet(sheets, "Categories"):
        item = CategoryRow(line, row["Name"], row["Group"], row["Money"])
        preview.categories.append(item)
        try:
            parent_code = GROUP_PARENT.get(row["Group"].casefold())
            if parent_code is None:
                raise ValueError("Pick the group from the list: Personal, Work or Investment.")
            if row["Money"].casefold() not in ("spending", "income"):
                raise ValueError("Pick Spending or Income.")
            if not item.name:
                raise ValueError("Write the category's name.")
            item.parent_code = parent_code
            key = f"{row['Group'].casefold()} / {item.name.casefold()}"
            if key in new_categories:
                raise ValueError("This category is listed twice.")
            under = [x for x in c.categories.tree() if x.depth >= 2 and x.code.startswith(parent_code + ".")
                     and x.name.casefold() == item.name.casefold()]
            if under:
                item.status, item.code = EXISTS, under[0].code
            new_categories[key] = item
        except (ValueError, LightningError) as error:
            item.status, item.error = ERROR, str(error)

    taken: dict[tuple, int] = {}
    for line, row in _sheet(sheets, "Entries"):
        item = EntryRow(line, account=row["Account"], category=row["Category"], counterparty=row["Counterparty"],
                        currency=row["Currency"].upper(), note=row["Note"])
        preview.entries.append(item)
        try:
            if row["Reference"]:
                found = c.db.scalar("SELECT ref FROM transactions WHERE lower(ref) = lower(?)", (row["Reference"],))
                if not found:
                    raise ValueError(f"The reference {row['Reference']} is not in this profile. Leave it empty for a new entry.")
                item.status, item.ref = EXISTS, found
                continue
            item.date = fmt_date(parse_date(row["Date"], "date"))
            item.amount = to_decimal(row["Amount"], "amount")
            if item.amount == ZERO:
                raise ValueError("The amount cannot be zero.")
            account = sheet_accounts.get(item.account.casefold())
            if account is not None and account.status == ERROR:
                raise ValueError("Its account row has a problem; fix that row first.")
            if account is None and item.account.casefold() not in existing:
                raise ValueError("The account is not on the Accounts sheet or in Lightning.")
            current = existing.get(item.account.casefold())
            currency = account.currency if account is not None and account.status == NEW else (current.currency if current else "")
            if item.currency and item.currency != currency:
                raise ValueError(f"The account holds {currency}; this entry says {item.currency}. Entries in another currency are not imported here.")
            item.currency = currency
            check_places(item.amount, c.assets.cash_asset(currency).quantity_decimals, "amount")
            item.category_key, movement = _resolve_category(item.category, by_name, by_code, new_categories, parents)
            if movement == Movement.INFLOW and item.amount < ZERO and not _both(item.category_key, by_code):
                raise ValueError("This is an income category, but the amount is money out.")
            if current is not None:
                item.account_id = current.id
                key = (item.date, current.id, _e6(item.amount), item.counterparty.casefold())
                taken.setdefault(key, _matches(c, key))
                if taken[key] > 0:
                    taken[key] -= 1
                    item.status = DUPLICATE
                    item.ref = _ref_of(c, key)
        except (ValueError, LightningError) as error:
            item.status, item.error = ERROR, str(error)
    return preview


def _both(category_key: str, by_code) -> bool:
    cat = by_code.get(category_key.casefold())
    return cat is not None and cat.direction == Direction.BOTH


def _resolve_category(text, by_name, by_code, new_categories, parents):
    """(a key: an existing category's code or "new:<group> / <name>", its movement)."""
    key = text.casefold()
    if not key:
        raise ValueError("Write the category.")
    if key in by_code:
        found = [by_code[key]]
    else:
        found = by_name.get(key, [])
    if len(found) > 1:
        groups = ", ".join(sorted({x.code.split(".")[1].title() for x in found}))
        raise ValueError(f"The category name is in more than one group ({groups}). Write it as Group / Name.")
    if found:
        if found[0].is_system or found[0].code.startswith("EXP.SYSTEM"):
            raise ValueError("System categories cannot be used here; pick another.")
        return found[0].code, found[0].movement
    for new_key, item in new_categories.items():
        if item.status == NEW and key in (item.name.casefold(), new_key):
            return f"new:{new_key}", Movement.INFLOW if item.money.casefold() == "income" else Movement.OUTFLOW
    raise ValueError("The category is not on the Categories sheet or in Lightning.")


def _e6(amount: Decimal) -> int:
    return int(amount * 1_000_000)


def _rows(c, key):
    date, account_id, amount_e6, counterparty = key
    return c.db.all(
        "SELECT t.ref FROM transactions t JOIN ledger_entries l ON l.transaction_id = t.id "
        "WHERE t.date = ? AND l.account_id = ? AND l.amount_e6 = ? AND lower(t.counterparty) = ? "
        "AND t.status = 'POSTED' AND t.type IN ('IN', 'OUT') ORDER BY t.id", (date, account_id, amount_e6, counterparty))


def _matches(c, key) -> int:
    return len(_rows(c, key))


def _ref_of(c, key) -> str:
    rows = _rows(c, key)
    return rows[0]["ref"] if rows else ""


@dataclass
class Result:
    accounts: list[AccountRow]
    categories: list[CategoryRow]
    entries: list[EntryRow]
    skipped: list


def confirm(c, data: bytes) -> Result:
    """Create what the preview showed as new, all or nothing. Rows with problems are returned as `skipped`."""
    preview = prepare(c, data)
    made_categories: dict[str, str] = {}
    with settled_write(c):
        for item in preview.accounts:
            if item.status == NEW:
                account = c.account_flows.open_account(item.name, item.account_type, item.date, item.balance,
                                                       currency=item.currency)
                item.code = account.code
        for item in preview.categories:
            if item.status == NEW:
                parent = c.categories.get_by_code(item.parent_code)
                cat = c.categories.create(parent.id, item.name)
                c.categories.set_direction(cat.id, Direction.IN if item.money.casefold() == "income" else Direction.OUT)
                item.code = cat.code
                made_categories[f"new:{item.group.casefold()} / {item.name.casefold()}"] = cat.code
        accounts = {a.name.casefold(): a for a in c.accounts.list()}
        for item in preview.entries:
            if item.status != NEW:
                continue
            category = c.categories.get_by_code(made_categories.get(item.category_key, item.category_key))
            account = accounts[item.account.casefold()] if item.account.casefold() in accounts else \
                next(a for a in c.accounts.list() if a.code.casefold() == item.account.casefold())
            post = c.transactions.record_inflow if item.amount > ZERO else c.transactions.record_outflow
            txn = post(item.date, account.id, abs(item.amount), category.id, counterparty=item.counterparty,
                       notes=item.note, source=TxnSource.IMPORT)
            item.ref = txn.ref
    return Result(preview.accounts, preview.categories, preview.entries, preview.problems)
