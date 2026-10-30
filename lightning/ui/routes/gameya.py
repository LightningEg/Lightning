"""The gam'eya (savings circle) page: where the circle stands, what to record next, and its terms.

The money rules live in ``lightning/deposits/gameya.py``; this page only collects the fields and draws the answer."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Request

from lightning.accounts.domain import AccountType
from lightning.core.dates import fmt_date, today
from lightning.core.errors import LightningError, NotFoundError, ValidationError

from ..web import container, redirect, render

router = APIRouter(prefix="/gameya")
TERM_FIELDS = ("organiser", "members", "installment", "first_date", "my_turn", "payout", "interest", "annual_rate",
               "funding_account_id", "payout_account_id")


def _circle(c, account_id: int):
    account = c.accounts.get(account_id)
    if account.account_type != AccountType.GAMEYA:
        raise NotFoundError("Gam'eya not found.")
    return account


def _plain(value: Decimal) -> str:
    """An amount for a form field: two places, no thousands comma."""
    return f"{value.quantize(Decimal('0.01'))}"


def _term_values(terms) -> dict:
    if terms is None:
        return {"organiser": "", "members": "", "installment": "", "first_date": fmt_date(today()), "my_turn": "",
                "payout": "", "interest": "none", "annual_rate": "", "funding_account_id": "",
                "payout_account_id": ""}
    return {"organiser": terms.organiser, "members": str(terms.members), "installment": _plain(terms.installment),
            "first_date": terms.first_date, "my_turn": str(terms.my_turn), "payout": _plain(terms.payout),
            "interest": "rate" if terms.annual_rate > 0 else "none",
            "annual_rate": f"{terms.annual_rate.normalize():f}" if terms.annual_rate > 0 else "",
            "funding_account_id": str(terms.funding_account_id), "payout_account_id": str(terms.payout_account_id)}


def _page(request: Request, account_id: int, *, values=None, record=None, error="", error_form="",
          status_code=200):
    c = container(request)
    account = _circle(c, account_id)
    terms = c.gameya.find(account_id)
    progress = c.gameya.progress(account_id) if terms else None
    cash = [a for a in c.accounts.list(active_only=True)
            if a.account_type in {AccountType.BANK, AccountType.CASH} and a.currency == account.currency]
    cash.sort(key=lambda a: (a.institution.casefold(), a.name.casefold()))
    now = today()
    prefill = {}
    if progress:
        prefill = {
            "instalment_date": fmt_date(min(date.fromisoformat(progress.next_date), now)) if progress.next_date else "",
            "instalment_amount": _plain(terms.installment),
            "instalment_from": str(terms.funding_account_id),
            "payout_date": fmt_date(min(date.fromisoformat(progress.payout_date), now)),
            "payout_amount": _plain(terms.payout), "payout_into": str(terms.payout_account_id)}
    prefill |= record or {}
    return render(request, "gameya/detail.html", status_code=status_code, account=account, terms=terms,
                  progress=progress, cash_accounts=cash, values=values or _term_values(terms), prefill=prefill,
                  counterparties=c.counterparties.list_active(), error=error, error_form=error_form,
                  today_iso=fmt_date(now), pot=(terms.installment * terms.members if terms else None))


@router.get("/{account_id:int}")
async def detail(request: Request, account_id: int):
    return _page(request, account_id)


@router.post("/{account_id:int}/terms")
async def save_terms(request: Request, account_id: int):
    form = await request.form()
    values = {key: str(form.get(key, "")).strip() for key in TERM_FIELDS}
    c = container(request)
    try:
        _circle(c, account_id)
        c.gameya.save_terms(
            account_id, organiser=values["organiser"], members=values["members"], installment=values["installment"],
            first_date=values["first_date"], my_turn=values["my_turn"], payout=values["payout"],
            annual_rate=values["annual_rate"] if values["interest"] == "rate" else "0",
            funding_account_id=_int(values["funding_account_id"], "funding_account_id"),
            payout_account_id=_int(values["payout_account_id"], "payout_account_id"))
    except (LightningError, ValueError) as exc:
        return _page(request, account_id, values=values, error=_message(exc), error_form="terms", status_code=400)
    return redirect(f"/gameya/{account_id}", "Gam'eya terms saved. Nothing was posted.")


@router.post("/{account_id:int}/instalment")
async def record_instalment(request: Request, account_id: int):
    form = await request.form()
    record = {"instalment_date": str(form.get("date", "")).strip(), "instalment_amount": str(form.get("amount", "")).strip(),
              "instalment_from": str(form.get("account_id", "")).strip()}
    c = container(request)
    submission = None if getattr(c, "is_journal", False) else str(form.get("submission", ""))
    payload = record | {"account": account_id}
    try:
        _circle(c, account_id)
        with c.db.transaction():
            # A resent form returns its first save; without this it recorded the next instalment too.
            txn = c.transactions.submitted(submission, payload)
            if txn is None:
                txn = c.gameya.record_instalment(account_id, record["instalment_date"], record["instalment_amount"],
                                                 _int(record["instalment_from"], "funding_account_id"))
                c.transactions.remember_submission(submission, payload, txn.id)
    except (LightningError, ValueError) as exc:
        return _page(request, account_id, record=record, error=_message(exc), error_form="instalment",
                     status_code=400)
    return redirect(f"/gameya/{account_id}", f"Recorded instalment · {txn.ref}.")


@router.post("/{account_id:int}/past-instalments")
async def record_past_instalments(request: Request, account_id: int):
    form = await request.form()
    c = container(request)
    try:
        _circle(c, account_id)
        expected = str(form.get("expected_paid", ""))
        if not expected.isdigit():
            raise ValidationError("Review the circle before recording past instalments.", "instalment")
        txns = c.gameya.record_past_instalments(account_id, expected_paid=int(expected))
    except LightningError as exc:
        return _page(request, account_id, error=exc.message, error_form="instalment", status_code=400)
    return redirect(f"/gameya/{account_id}", f"Recorded {len(txns)} past instalments.")


@router.post("/{account_id:int}/payout")
async def record_payout(request: Request, account_id: int):
    form = await request.form()
    record = {"payout_date": str(form.get("date", "")).strip(), "payout_amount": str(form.get("amount", "")).strip(),
              "payout_into": str(form.get("account_id", "")).strip()}
    c = container(request)
    try:
        _circle(c, account_id)
        txn = c.gameya.record_payout(account_id, record["payout_date"], record["payout_amount"],
                                     _int(record["payout_into"], "payout_account_id"))
    except (LightningError, ValueError) as exc:
        return _page(request, account_id, record=record, error=_message(exc), error_form="payout", status_code=400)
    return redirect(f"/gameya/{account_id}", f"Recorded payout · {txn.ref}.")


def _message(exc: Exception) -> str:
    return exc.message if isinstance(exc, LightningError) else "Choose an active bank or cash account."


def _int(value: str, field: str) -> int:
    if not str(value).isdigit():
        raise ValidationError("Choose an active bank or cash account.", field)
    return int(value)
