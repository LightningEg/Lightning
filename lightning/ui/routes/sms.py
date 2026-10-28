"""From SMS (milestone 3): paste bank messages, say once which account an ending is, then review them on the
bank import's review screen. The phone app will also send new messages here by itself."""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from lightning.core.errors import LightningError
from lightning.sms_imports import MAX_TEXT, SALARY_ENDING, parse_sms

from ..web import container, redirect, render

router = APIRouter(prefix="/sms")
MAX_PASTE = 50  # messages in one paste


def phone_source(request):
    """The phone's SMS source, when this is the phone app and the ledger is writable here."""
    source = getattr(request.app.state, "sms_source", None)
    if source is None or getattr(request.state, "read_only", False):
        return None
    return source


def read_phone_sms(request, c) -> dict | None:
    """Read what arrived since last time (and what was shared in). Never breaks the page that asked."""
    source = phone_source(request)
    if source is None:
        return None
    try:
        return c.sms_imports.read_source(source)
    except Exception:  # noqa: BLE001 - the phone's inbox is a convenience: the page still opens
        return None


def _page(request, c, **context):
    source = phone_source(request)
    try:
        permission = source.permission() if source is not None else "unavailable"
    except Exception:  # noqa: BLE001
        permission = "unavailable"
    accounts = [a for a in c.accounts.list(active_only=True)
                if a.account_type.value in ("BANK", "CASH") and a.currency == "EGP"]
    names = {a.id: a.name for a in c.accounts.list()}
    batches = [b | {"account": names.get(b["account_id"], "")} for b in c.bank_imports.waiting_all()
               if str(b["file_name"]).startswith("SMS ")]
    return render(request, "sms.html", waiting=c.sms_imports.waiting(), accounts=accounts, batches=batches,
                  unread=c.sms_imports.unread(), permission=permission, last_read=c.sms_imports.last_read(),
                  salary=SALARY_ENDING, **context)


@router.get("")
async def sms_page(request: Request):
    c = container(request)
    read_phone_sms(request, c)
    return _page(request, c)


@router.post("/allow")
async def allow(request: Request):
    """After the owner read what is read and why: the phone's own permission question."""
    source = phone_source(request)
    if source is not None:
        source.request()
    return redirect("/sms", "Answer the phone's question, then come back here.")


@router.post("/paste")
async def paste(request: Request):
    c = container(request)
    form = await request.form()
    text = str(form.get("messages", ""))[:MAX_TEXT * MAX_PASTE]
    messages = [m.strip() for m in re.split(r"\n\s*\n", text) if m.strip()][:MAX_PASTE]
    if not messages:
        return _page(request, c, error="Paste one or more bank messages, a blank line between each.")
    now = datetime.now()
    result = c.sms_imports.read([("", m, now) for m in messages])
    found = sum(len(c.bank_imports.preview(batch)[1]) for batch in result["staged"].values())
    parts = []
    if found:
        parts.append(f"{found} ready to review")
    if result["waiting"]:
        parts.append(f"{result['waiting']} waiting for their account")
    if result.get("unread"):
        parts.append(f"{result['unread']} to read yourself")
    if result["skipped"]:
        parts.append(f"{result['skipped']} skipped (read before, or not a payment)")
    return redirect("/sms", "; ".join(parts).capitalize() + ".")


@router.post("/dismiss")
async def dismiss(request: Request):
    c = container(request)
    form = await request.form()
    c.sms_imports.dismiss(str(form.get("id", "")))
    return redirect("/sms")


@router.post("/assign")
async def assign(request: Request):
    c = container(request)
    form = await request.form()
    try:
        batch = c.sms_imports.assign(str(form.get("ending", "")), int(str(form.get("account_id", "0")) or 0))
    except (LightningError, ValueError) as exc:
        return _page(request, c, error=getattr(exc, "message", "") or "Choose the account for these messages.")
    if batch is None:
        return redirect("/sms", "Saved.")
    account_id = c.bank_imports.preview(batch)[0]["account_id"]
    return redirect(f"/accounts/{account_id}/import/{batch}", "Check each row, then post them.")


@router.post("/read-one")
async def read_one_message(request: Request):
    """Paste bank SMS on the entry sheet (phone roadmap M3): one message read into the sheet's fields, saved nowhere.
    The sheet fills Amount, Counterparty, Date and Money in or out; the person checks them and taps Save."""
    form = await request.form()
    text = str(form.get("text", ""))[:MAX_TEXT]
    try:
        found = parse_sms(text)
    except ValueError:  # a clock or date the bank wrote wrongly (29:13): nothing to fill in
        found = None
    if found is None:
        return JSONResponse({"error": "No amount found in this message."}, status_code=422)
    return JSONResponse({"amount": f"{found.amount:.2f}", "counterparty": found.place, "date": found.when[:10],
                         "kind": "in" if found.inflow else "out", "bank": found.bank, "sure": found.sure})
