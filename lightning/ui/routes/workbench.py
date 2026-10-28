"""PC big actions (owner, 2026-10-28): one Import page for every statement (P8) and Find and replace on the
transaction list (P7). Both reuse the services the per-account pages already use; deletes stay restorable."""
from __future__ import annotations

import re

from fastapi import APIRouter, Request

from lightning.core.errors import LightningError
from lightning.transactions.domain import TxnFilter

from ..web import container, redirect, render

router = APIRouter()

IMPORTABLE = ("BANK", "CASH", "CREDIT_CARD")
REPLACE_LIMIT = 2000
FIELDS = ("counterparty", "notes")


def guess_account(file_name: str, accounts) -> int | None:
    """The account a statement file belongs to: its last four digits in the name first, then its name."""
    text = file_name.casefold()
    digits = set(re.findall(r"\d{4}", text))
    for account in accounts:
        if account.last4 and account.last4 in digits:
            return account.id
    for account in accounts:
        words = [w for w in re.split(r"\W+", f"{account.institution} {account.name}".casefold()) if len(w) > 2]
        if words and any(w in text for w in words):
            return account.id
    return None


@router.get("/import")
async def import_page(request: Request):
    c = container(request)
    accounts = [a for a in c.accounts.list(active_only=True) if getattr(a.account_type, "value", a.account_type) in IMPORTABLE]
    waiting = c.bank_imports.waiting_all()
    return render(request, "import.html", accounts=accounts, batches=c.bank_imports.history(), waiting=waiting)


@router.post("/import/{batch_id:int}/undo")
async def undo_batch(request: Request, batch_id: int):
    c = container(request)
    ids = c.bank_imports.created_transactions(batch_id)
    if not ids:
        return redirect("/import", "Nothing from this file is left to undo.")
    try:
        count = c.transactions.delete_many(ids)
    except LightningError as exc:
        return redirect("/import", exc.message)
    return redirect("/import", f"Undid the import: deleted {count} entr{'ies' if count != 1 else 'y'}. You can restore them from history.")


def matches(c, field: str, find: str, search: str = "") -> list:
    rows, _ = c.transactions.find(TxnFilter(search=search or find, limit=REPLACE_LIMIT))
    needle = find.casefold()
    return [r for r in rows if needle in str(getattr(r, field, "") or "").casefold()]


def _replace(text: str, find: str, new: str) -> str:
    return re.sub(re.escape(find), lambda _: new, text, flags=re.I)


@router.post("/transactions/find-replace")
async def find_replace(request: Request):
    """Find text in payees or notes and replace it on every match (up to 2,000), as one bulk edit."""
    c = container(request)
    form = await request.form()
    field = str(form.get("field", "counterparty"))
    find, new = str(form.get("find", "")).strip(), str(form.get("replace", "")).strip()
    back = str(form.get("back", ""))
    destination = back if back.startswith("/") and not back.startswith("//") else "/transactions"
    if field not in FIELDS or not find:
        return redirect(destination, "Type the text to find.")
    rows = matches(c, field, find)
    if not rows:
        return redirect(destination, f"No counterparty or note contains “{find}”.")
    groups: dict[str, list[int]] = {}
    for row in rows:
        groups.setdefault(_replace(str(getattr(row, field) or ""), find, new), []).append(row.id)
    changed = skipped = 0
    try:
        with c.db.transaction():
            for value, ids in groups.items():
                if field == "counterparty" and value and not c.counterparties.resolve(value):
                    c.counterparties.create(value)   # the user typed it on purpose: a new saved payee
                done, left = c.transactions.bulk_update(ids, {field: value})
                changed, skipped = changed + len(done), skipped + len(left)
    except LightningError as exc:
        return redirect(destination, exc.message)
    message = f"Replaced “{find}” on {changed} row{'s' if changed != 1 else ''}."
    if skipped:
        message += f" {skipped} left as they were (transfers and investment rows)."
    return redirect(destination, message)
