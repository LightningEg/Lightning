"""Explicit, preview-first merge for duplicate posted cash transactions."""
from __future__ import annotations

from fastapi import APIRouter, Request

from lightning.core.errors import LightningError
from ..web import container, redirect, render

router = APIRouter()


@router.get("/transactions/merge-selected")
async def selected_merge(request: Request):
    ids = list(dict.fromkeys(request.query_params.getlist("txn_ids")))
    if len(ids) != 2 or any(not value.isdigit() or len(value) > 19 or not 1 <= int(value) <= 2**63 - 1 for value in ids):
        return redirect("/transactions?select=1", "Select two transactions in the register, then choose Merge selected.")
    return redirect(f"/transactions/merge?keep={ids[0]}&drop={ids[1]}")


def _template(request):
    return "phone/transactions/merge.html" if getattr(request.state, "phone", False) else "transactions/merge.html"


@router.get("/transactions/merge")
async def merge_preview(request: Request):
    keep_id = request.query_params.get("keep", "")
    drop_id = request.query_params.get("drop", "")
    if any(not value.isdigit() or len(value) > 19 for value in (keep_id, drop_id)):
        return render(request, _template(request), keep_id=keep_id if keep_id.isdigit() else "",
                      drop_id="", preview=None, error="Select both transaction entries to compare.")
    c = container(request)
    try:
        preview = c.transactions.merge_preview(int(keep_id), int(drop_id))
    except LightningError as exc:
        return render(request, _template(request), keep_id=keep_id, drop_id=drop_id, preview=None, error=str(exc))
    context = _context(c, preview)
    return render(request, _template(request), keep_id=keep_id, drop_id=drop_id, preview=preview, error="", **context)


@router.post("/transactions/merge")
async def confirm_merge(request: Request):
    form = await request.form()
    keep_id, drop_id = str(form.get("keep_id", "")), str(form.get("drop_id", ""))
    if any(not value.isdigit() or len(value) > 19 for value in (keep_id, drop_id)):
        return render(request, _template(request), keep_id="", drop_id="", preview=None,
                      error="Select both transaction entries to compare.", status_code=400)
    c = container(request)
    try:
        merged = c.transactions.merge(int(keep_id), int(drop_id), str(form.get("fingerprint", "")))
    except LightningError as exc:
        try:
            preview = c.transactions.merge_preview(int(keep_id), int(drop_id))
        except LightningError:
            preview = None
        return render(request, _template(request), keep_id=keep_id, drop_id=drop_id,
                      preview=preview, error=str(exc), **(_context(c, preview) if preview else {}), status_code=400)
    return redirect(f"/transactions/{merged.id}", f"Merged duplicate into {merged.ref}.")


def _context(c, preview):
    if preview is None:
        return {}
    def account_names(txn):
        names = []
        for line in txn.lines:
            name = c.accounts.get(line.account_id).name
            if name not in names:
                names.append(name)
        return names
    return {"keep_accounts": account_names(preview.keep), "drop_accounts": account_names(preview.drop),
            "keep_summary": c.transactions.summarize(preview.keep),
            "drop_summary": c.transactions.summarize(preview.drop)}
