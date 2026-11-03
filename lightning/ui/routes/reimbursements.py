from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Request

from lightning.core.errors import LightningError, ValidationError
from lightning.core.money import to_decimal

from ..web import container, redirect, render

router = APIRouter(prefix="/reimbursements")


def _context(request: Request, error: str = "", values: dict | None = None):
    c = container(request)
    claims = c.reimbursements.list_claims()
    pairs = c.reimbursements.suggested_pairs(claims=claims)
    category_names = {category_id: c.categories.display_name(category_id)
                      for category_id in {pair["category_id"] for pair in pairs}}
    for pair in pairs:
        pair["category_name"] = category_names[pair["category_id"]]
        pair["review_url"] = "/reimbursements?" + urlencode({
            "expense_id": pair["expense_id"], "expected": pair["amount"],
            "payer_id": pair["payer_id"] or ""}) + "#new-claim-title"
    for claim in claims:
        claim["record_receipt_url"] = _receipt_entry(c, claim)
    return {"claims": claims, "pairs": pairs,
            "expenses": c.reimbursements.eligible_expenses(),
            "receipts": c.reimbursements.available_receipts(),
            "counterparties": c.counterparties.list_active(),
            "base": c.base_currency, "error": error,
            "values": values or {"transaction_id": str(request.query_params.get("expense_id", "")), "expected": str(request.query_params.get("expected", "")),
                                 "payer_id": str(request.query_params.get("payer_id", "")), "due_date": ""}}


def _receipt_entry(c, claim):
    """Reuse Money in with the original expense category; the person records actual cash once."""
    if not claim["expense_id"] or claim["issues"] or claim["outstanding"] <= 0:
        return ""
    txn = c.transactions.get(claim["expense_id"])
    if len(txn.lines) != 1:
        return ""
    line = txn.lines[0]
    account = c.accounts.get(line.account_id)
    category = c.categories.get(line.category_id) if line.category_id else None
    if (not account.active or account.account_type.value not in ("BANK", "CASH", "BROKERAGE")
            or category is None or category.movement.value != "OUTFLOW" or category.is_system):
        return ""
    values = {"kind": "in", "category_id": category.id,
              "amount": str(claim["outstanding"]) if account.currency == c.base_currency else "",
              "counterparty": claim["payer_name"] or "",
              "return_to": f"/reimbursements#claim-{claim['id']}"}
    return f"/accounts/{account.id}/transaction/new?" + urlencode(values)


@router.get("")
async def reimbursements_page(request: Request):
    return render(request, "reimbursements.html", **_context(request))


@router.post("")
async def create_claim(request: Request):
    c = container(request)
    form = await request.form()
    values = {key: str(form.get(key, "")).strip()
              for key in ("transaction_id", "expected", "payer_id", "due_date")}
    try:
        if not values["transaction_id"].isdigit():
            raise ValueError
        transaction_id = int(values["transaction_id"])
        if values["payer_id"] and not values["payer_id"].isdigit():
            raise ValueError
        payer_id = int(values["payer_id"]) if values["payer_id"] else None
        claim = c.reimbursements.create_claim(transaction_id, values["expected"], payer_id,
                                              values["due_date"] or None)
    except (ValueError, LightningError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Choose an expense and enter an amount."
        return render(request, "reimbursements.html", status_code=400, **_context(request, message, values))
    return redirect(f"/reimbursements#claim-{claim['id']}", f"Created reimbursement claim for {claim['expense']['ref']}.")


@router.post("/{claim_id:int}/pair")
async def confirm_pair(request: Request, claim_id: int):
    c = container(request)
    form = await request.form()
    try:
        receipt_id = int(str(form.get("receipt_id", "")))
        amount = str(form.get("amount", ""))
        value = to_decimal(amount, "amount")
        candidate = next((pair for pair in c.reimbursements.suggested_pairs()
                          if pair["claim_id"] == claim_id and pair["receipt_id"] == receipt_id
                          and pair["amount"] == value), None)
        if candidate is None:
            raise ValidationError("This suggested pair changed. Review the receipts again.")
        c.reimbursements.link_receipt(claim_id, receipt_id, amount)
    except (ValueError, LightningError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Choose a receipt and enter an amount."
        return render(request, "reimbursements.html", status_code=400, **_context(request, message))
    return redirect(f"/reimbursements#claim-{claim_id}", "Linked the receipt; no income or cash entry was added.")


@router.post("/{claim_id:int}/receipts")
async def link_receipt(request: Request, claim_id: int):
    c = container(request)
    form = await request.form()
    receipt_id = str(form.get("receipt_id", "")).strip()
    amount = str(form.get("amount", "")).strip()
    try:
        if not receipt_id.isdigit():
            raise ValueError
        c.reimbursements.link_receipt(claim_id, int(receipt_id), amount)
    except (ValueError, LightningError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Choose a receipt and enter an amount."
        return render(request, "reimbursements.html", status_code=400, **_context(request, message))
    return redirect("/reimbursements", "Linked the receipt; no income or cash entry was added.")


@router.post("/{claim_id:int}/receipts/{link_id:int}/unlink")
async def unlink_receipt(request: Request, claim_id: int, link_id: int):
    try:
        container(request).reimbursements.unlink_receipt(claim_id, link_id)
    except LightningError as exc:
        return redirect("/reimbursements", exc.message)
    return redirect("/reimbursements", "Removed the receipt link.")


@router.post("/{claim_id:int}/delete")
async def delete_claim(request: Request, claim_id: int):
    try:
        container(request).reimbursements.delete_claim(claim_id)
    except LightningError as exc:
        return redirect("/reimbursements", exc.message)
    return redirect("/reimbursements", "Deleted the reimbursement claim and its links.")
