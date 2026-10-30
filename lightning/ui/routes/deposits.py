from __future__ import annotations


from fastapi import APIRouter, Request

from lightning.accounts.domain import AccountType
from lightning.core.dates import fmt_date, today
from lightning.core.errors import LightningError, NotFoundError, ValidationError

from ..web import container, redirect, render

router = APIRouter(prefix="/deposits")
METHODS = {"SIMPLE": "Simple", "COMPOUND": "Compound"}
COMPOUNDING_FREQUENCIES = {"MONTHLY": "Monthly", "QUARTERLY": "Quarterly", "YEARLY": "Yearly"}
FREQUENCIES = {"MONTHLY": "Monthly", "QUARTERLY": "Quarterly", "YEARLY": "Yearly",
               "AT_MATURITY": "At maturity"}
TERM_FIELDS = ("name", "lockup_end_date", "maturity_date", "annual_rate", "interest_method",
               "compounding_frequency", "payout_frequency", "destination_account_id")


def _account(c, account_id: int):
    account = c.accounts.get(account_id)
    if account.account_type != AccountType.DEPOSIT:
        raise NotFoundError("CD portfolio not found.")
    return account


def _values():
    return {"name": "", "start_date": fmt_date(today()), "lockup_end_date": "", "maturity_date": "",
            "term_years": "",
            "principal": "", "annual_rate": "", "interest_method": "SIMPLE",
            "compounding_frequency": "MONTHLY", "payout_frequency": "AT_MATURITY",
            "destination_account_id": "", "funding_account_id": ""}


def _page(request: Request, account_id: int, values=None, error="", status_code=200):
    c = container(request)
    account = _account(c, account_id)
    certificates = c.deposits.list_certificates(account_id)
    liquid = [a for a in c.accounts.list(active_only=True)
              if a.id != account_id and a.account_type in {AccountType.CASH, AccountType.BANK}
              and a.currency == account.currency]
    liquid.sort(key=lambda a: (a.institution.casefold() != account.institution.casefold(),
                               a.institution.casefold(), a.name.casefold()))
    liquid_by_id = {a.id: a for a in liquid}
    factor = c.investments.liquidation_factors()[c.assets.get_class_by_code("DEPOSIT.CD").id]
    try:
        legacy = c.deposits.get(account_id)
    except NotFoundError:
        legacy = None
    interest_receipts = c.deposit_receipts.match_plan(account_id)
    suggestions = sum(1 for item in interest_receipts if item["suggested"])
    return render(request, "deposits/detail.html", status_code=status_code, account=account,
                  certificates=certificates, values=values or _values(), error=error,
                  liquid_accounts=liquid, liquid_by_id=liquid_by_id, sale_factor=factor, legacy=legacy,
                  legacy_cash=c.deposits.legacy_cash_balance(account_id), today_iso=fmt_date(today()),
                  interest_receipts=interest_receipts, suggestions=suggestions)


@router.get("/{account_id:int}")
async def detail(request: Request, account_id: int):
    return _page(request, account_id)


@router.post("/{account_id:int}/purchase")
async def purchase(request: Request, account_id: int):
    form = await request.form()
    values = _values() | {key: str(form.get(key, "")).strip() for key in _values()}
    c = container(request)
    submission = None if getattr(c, "is_journal", False) else str(form.get("submission", ""))
    payload = values | {"account": account_id}
    try:
        with c.db.transaction():
            earlier = c.transactions.submitted(submission, payload)  # a resent form returns its first purchase
            if earlier is not None:
                return redirect(f"/deposits/{account_id}", f"Saved {earlier.ref}.")
            certificate, txn = c.deposits.purchase(
                account_id, values["name"], values["start_date"], values["lockup_end_date"],
                values["maturity_date"], values["principal"], values["annual_rate"],
                values["interest_method"], values["payout_frequency"], values["compounding_frequency"],
                _int(values["destination_account_id"]), _int(values["funding_account_id"]),
                term_years=values["term_years"],
            )
            c.transactions.remember_submission(submission, payload, txn.id)
    except (LightningError, ValueError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Choose the funding and payout accounts."
        return _page(request, account_id, values, message, 400)
    return redirect(f"/deposits/{account_id}", f"Bought {certificate.terms.name} · {txn.ref}.")


@router.post("/{account_id:int}/certificates/{certificate_id:int}/terms")
async def update_terms(request: Request, account_id: int, certificate_id: int):
    form = await request.form()
    c = container(request)
    try:
        cert = c.deposits.certificate(certificate_id)
        if cert.terms.account_id != account_id:
            raise NotFoundError("Certificate not found in this portfolio.")
        c.deposits.update_certificate(
            certificate_id, name=str(form.get("name", "")).strip(),
            lockup_end_date=str(form.get("lockup_end_date", "")),
            maturity_date=str(form.get("maturity_date", "")),
            annual_rate=str(form.get("annual_rate", "")),
            interest_method=str(form.get("interest_method", "")),
            payout_frequency=str(form.get("payout_frequency", "")),
            compounding_frequency=str(form.get("compounding_frequency", "")),
            destination_account_id=_int(str(form.get("destination_account_id", ""))),
            term_years=str(form.get("term_years", "")),
        )
    except (LightningError, ValueError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Choose a valid payout account."
        return _page(request, account_id, error=message, status_code=400)
    return redirect(f"/deposits/{account_id}", "Certificate terms saved. Interest remains forecast only.")


@router.post("/{account_id:int}/certificates/{certificate_id:int}/redeem")
async def redeem(request: Request, account_id: int, certificate_id: int):
    form = await request.form()
    c = container(request)
    try:
        cert = c.deposits.certificate(certificate_id)
        if cert.terms.account_id != account_id:
            raise NotFoundError("Certificate not found in this portfolio.")
        txn = c.deposits.redeem(certificate_id, str(form.get("date", "")),
                                str(form.get("proceeds", "")),
                                _int(str(form.get("destination_account_id", ""))))
    except (LightningError, ValueError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Choose a valid destination account."
        return _page(request, account_id, error=message, status_code=400)
    return redirect(f"/deposits/{account_id}", f"Recorded actual CD redemption · {txn.ref}.")


@router.post("/{account_id:int}/interest/match-all")
@router.post("/{account_id:int}/certificates/{certificate_id:int}/interest/match-all")
async def match_all_suggested_receipts(request: Request, account_id: int, certificate_id: int | None = None):
    """Confirm every suggested receipt at once (one action, undoable); never posts a ledger entry."""
    c = container(request)
    form = await request.form()
    back = str(form.get("back", ""))
    back = back if back.startswith("/") and not back.startswith("//") else f"/deposits/{account_id}"
    try:
        if certificate_id is not None and c.deposits.certificate(certificate_id).terms.account_id != account_id:
            raise NotFoundError("Certificate not found in this portfolio.")
        result = c.deposit_receipts.confirm_suggested(account_id, certificate_id, today())
    except (LightningError, ValueError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Choose valid bank receipts."
        return _page(request, account_id, error=message, status_code=400)
    return redirect(back, f"Matched {result['matched']} interest payment(s) to bank receipts.")


@router.post("/{account_id:int}/certificates/{certificate_id:int}/interest/{event_date}/confirm")
async def confirm_interest_receipts(request: Request, account_id: int, certificate_id: int, event_date: str):
    c = container(request)
    form = await request.form()
    try:
        cert = c.deposits.certificate(certificate_id)
        if cert.terms.account_id != account_id:
            raise NotFoundError("Certificate not found in this portfolio.")
        result = c.deposit_receipts.confirm(certificate_id, event_date, form.getlist("transaction_ids"), today())
    except (LightningError, ValueError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Choose valid bank receipts."
        return _page(request, account_id, error=message, status_code=400)
    return redirect(f"/deposits/{account_id}",
                    f"Matched {len(result['receipts'])} bank receipt(s); {result['remaining']} remains expected.")


@router.post("/{account_id:int}/certificates/{certificate_id:int}/interest/{event_date}/remove")
async def remove_interest_receipt(request: Request, account_id: int, certificate_id: int, event_date: str):
    c = container(request)
    form = await request.form()
    try:
        cert = c.deposits.certificate(certificate_id)
        if cert.terms.account_id != account_id:
            raise NotFoundError("Certificate not found in this portfolio.")
        c.deposit_receipts.remove(certificate_id, event_date, form.get("transaction_id"))
    except (LightningError, ValueError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Choose a valid bank receipt."
        return _page(request, account_id, error=message, status_code=400)
    return redirect(f"/deposits/{account_id}", "Removed the receipt confirmation.")


@router.post("/{account_id:int}/legacy-cash")
async def move_legacy_cash(request: Request, account_id: int):
    form = await request.form()
    c = container(request)
    try:
        txn = c.deposits.move_legacy_cash(
            account_id, str(form.get("date", "")), str(form.get("amount", "")),
            _int(str(form.get("destination_account_id", ""))),
        )
    except (LightningError, ValueError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Choose a valid destination account."
        return _page(request, account_id, error=message, status_code=400)
    return redirect(f"/deposits/{account_id}", f"Moved legacy cash to a liquid account · {txn.ref}.")


@router.post("/{account_id:int}/legacy")
async def save_legacy(request: Request, account_id: int):
    """Retain an edit path for account-level CD terms created before certificate portfolios."""
    form = await request.form()
    try:
        c = container(request)
        c.deposits.save(
            account_id, str(form.get("start_date", "")), str(form.get("maturity_date", "")),
            str(form.get("principal", "")), str(form.get("annual_rate", "")),
            str(form.get("interest_method", "SIMPLE")), str(form.get("payout_frequency", "AT_MATURITY")),
            _int(str(form.get("destination_account_id", ""))),
            lockup_end_date=str(form.get("lockup_end_date", "")),
            compounding_frequency=str(form.get("compounding_frequency", "MONTHLY")),
        )
    except (LightningError, ValueError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Choose a valid payout account."
        return _page(request, account_id, error=message, status_code=400)
    return redirect(f"/deposits/{account_id}", "Legacy CD terms saved.")


def _int(value: str) -> int:
    if not value.isdigit():
        raise ValidationError("Choose an account.", "destination_account_id")
    return int(value)
