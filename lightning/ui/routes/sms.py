"""From SMS (milestone 3): paste bank messages, say once which account an ending is, then review them on the
bank import's review screen. The phone app will also send new messages here by itself."""
from __future__ import annotations

import re
from decimal import Decimal
from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from lightning.core.errors import LightningError
from lightning.sms_imports import (MAX_TEXT, SALARY_ENDING, WALLET_PREFIX, _IGNORE as _IGNORE_RE, fingerprint, parse_sms,
                                    prefill, wallet_name)

from ..web import container, redirect, render, settled_save

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


def _enter_url(message: dict) -> str:
    """Add, filled from a kept message as far as it can be read: the amount, its day and which way it went, with the
    message itself in Notes. Saving it takes the message off From SMS."""
    found = prefill(message.get("text", ""))
    values = {"kind": found["kind"], "amount": found["amount"], "date": found["date"] or str(message.get("received", ""))[:10],
              "counterparty": found["counterparty"],
              "notes": str(message.get("text", ""))[:200], "sms_fp": str(message.get("id", "")).split("@")[0],
              "return_to": "/sms"}
    return "/accounts/add-transaction?" + urlencode({k: v for k, v in values.items() if v})


def _page(request, c, **context):
    source = phone_source(request)
    try:
        permission = source.permission() if source is not None else "unavailable"
    except Exception:  # noqa: BLE001
        permission = "unavailable"
    accounts = c.sms_imports.choices()
    names = {a.id: a.name for a in c.accounts.list()}
    batches = [b | {"account": names.get(b["account_id"], "")} for b in c.bank_imports.waiting_all()
               if str(b["file_name"]).startswith("SMS ")]
    # Every ending not known yet is asked in one form, each with the account it most likely is already chosen.
    waiting = [g | {"guess": c.sms_imports.guess(g["ending"], g.get("banks", []))} for g in c.sms_imports.waiting()]
    unread = [m | {"enter": _enter_url(m)} for m in c.sms_imports.unread()]
    codes = {a.code: a.name for a in c.accounts.list()}
    saved = [m | {"amount": Decimal(m["amount"]), "account": codes.get(m.get("account"), "")} for m in c.sms_imports.saved()]
    return render(request, "sms.html", waiting=waiting, accounts=accounts, batches=batches, saved=saved,
                  unread=unread, permission=permission, last_read=c.sms_imports.last_read(),
                  salary=SALARY_ENDING, wallet_prefix=WALLET_PREFIX, wallet_name=wallet_name, **context)


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
    text = str(form.get("messages", ""))[:MAX_TEXT * MAX_PASTE]  # not money: text length
    messages = [m.strip() for m in re.split(r"\n\s*\n", text) if m.strip()][:MAX_PASTE]
    if not messages:
        return _page(request, c, error="Paste one or more bank messages, a blank line between each.")
    now = datetime.now()
    with settled_save(request, container(request)):
        result = c.sms_imports.read([("", m, now) for m in messages])
    found = sum(row["_status"] == "REVIEW" for batch in result["staged"].values()  # not money: counts
                for row in c.bank_imports.preview(batch)[1])
    parts = []
    if result.get("saved"):
        parts.append(f"{result['saved']} saved for you")
    if found:
        parts.append(f"{found} ready to check")
    if result["waiting"]:
        parts.append(f"{result['waiting']} need their account")
    if result.get("unread"):
        parts.append(f"{result['unread']} kept for you")
    if result["skipped"]:
        parts.append(f"{result['skipped']} skipped")
    if len(result["staged"]) == 1 and not result["waiting"] and found:  # one account's rows and nothing to ask: check them now
        account_id, batch = next(iter(result["staged"].items()))
        return redirect(f"/accounts/{account_id}/import/{batch}", " · ".join(parts))
    return redirect("/sms", " · ".join(parts) or "Nothing new in these messages.")


@router.post("/dismiss")
async def dismiss(request: Request):
    c = container(request)
    form = await request.form()
    with settled_save(request, container(request)):
        c.sms_imports.dismiss(str(form.get("id", "")))
    return redirect("/sms")


@router.post("/undo")
async def undo_saved(request: Request):
    """NF-7AO2: take back a message that saved itself; it waits on its review like any other."""
    c = container(request)
    form = await request.form()
    try:
        with settled_save(request, container(request)):
            account_id, batch_id = c.sms_imports.undo_saved(str(form.get("ref", ""))[:40])
    except LightningError as exc:
        return redirect("/sms", exc.message)
    return redirect(f"/accounts/{account_id}/import/{batch_id}", "Undone. It waits for your check.")


@router.post("/assign")
async def assign(request: Request):
    """Which account each card ending is, answered together (``account_<ending>`` per ending, or the older single
    ``ending`` and ``account_id``). An ending left on Choose waits for next time."""
    c = container(request)
    form = await request.form()
    answers: dict[str, int] = {}
    if form.get("ending"):
        answers[str(form.get("ending"))] = str(form.get("account_id", ""))
    for key, value in form.multi_items():
        if key.startswith("account_") and key != "account_id":
            answers[key.removeprefix("account_")] = str(value)
    try:
        chosen = {ending: int(value) for ending, value in answers.items() if str(value).strip()}
        if not chosen:
            raise ValueError
        with settled_save(request, container(request)):
            if len(chosen) == 1:  # one ending: the single command (synced profiles have both)
                (ending, account_id), = chosen.items()
                batch = c.sms_imports.assign(ending, account_id)
                batches = {ending: batch} if batch is not None else {}
            else:
                batches = c.sms_imports.assign_many(chosen)
    except (LightningError, ValueError) as exc:
        return _page(request, c, error=getattr(exc, "message", "") or "Choose the account for these messages.")
    distinct = sorted(set(batches.values()))
    if len(distinct) == 1 and not c.sms_imports.waiting():
        account_id = c.bank_imports.preview(distinct[0])[0]["account_id"]
        return redirect(f"/accounts/{account_id}/import/{distinct[0]}", "Check each row, then post them.")
    return redirect("/sms", "Saved." if not distinct else "Check each account's messages below.")


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
    c = container(request)
    if found is None:
        # No bank pattern read it: fill what the words still say (amount, day, shop) and ask the person to check
        # the account and who, instead of an error. Only a message with no amount at all is refused.
        loose = prefill(text)
        if not loose["amount"] or _IGNORE_RE.search(text):
            return JSONResponse({"error": "No amount found in this message."}, status_code=422)
        return JSONResponse({"amount": f"{Decimal(loose['amount']):.2f}", "counterparty": loose["counterparty"],
                             "date": loose["date"], "kind": loose["kind"], "bank": "", "sure": False,
                             "ending": "", "account_id": None, "currency": loose["currency"],
                             "note": "Check the account and who.", "fingerprint": fingerprint(text)})
    # No account is asked (3AN5): the card or account ending in the message is the account, once it has been said. An
    # ending not seen before comes back with no account; the sheet asks once, and saving remembers the answer.
    return JSONResponse({"amount": f"{found.amount:.2f}", "counterparty": found.place, "date": found.when[:10],
                         "kind": "in" if found.inflow else "out", "bank": found.bank, "sure": found.sure,
                         "ending": found.ending, "account_id": c.sms_imports.account_for(found.ending),
                         "fingerprint": fingerprint(text)})
