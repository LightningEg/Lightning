"""Integrated review of recent posted activity."""
from __future__ import annotations

from fastapi import APIRouter, Request

from lightning.core.errors import LightningError, ValidationError
from lightning.ui.web import container, redirect, render
from lightning.workflows.activity import ActivityReview

router = APIRouter(prefix="/activity")


def _template(request: Request, view: str) -> str:
    return f"phone/activity/{view}.html" if getattr(request.state, "phone", False) else f"activity/{view}.html"


@router.get("")
async def activity_page(request: Request):
    workflow = ActivityReview(container(request))
    return render(request, _template(request, "index"), rows=workflow.recent())


@router.get("/{transaction_id:int}")
async def activity_detail(request: Request, transaction_id: int, error: str = ""):
    workflow = ActivityReview(container(request))
    try:
        detail = workflow.summary(transaction_id)
    except LightningError as exc:
        return redirect("/activity", str(exc))
    return render(request, _template(request, "detail"), detail=detail, error=error)


@router.post("/{transaction_id:int}/apply")
async def activity_apply(request: Request, transaction_id: int):
    c = container(request)
    form = await request.form()
    try:
        raw_category = str(form.get("category_choice", "")).strip()
        category_id = int(raw_category) if raw_category else None
        raw_reserve = str(form.get("reserve_id", "")).strip()
        reserve_id = int(raw_reserve) if raw_reserve else None
        c.activity_review.apply(transaction_id, str(form.get("fingerprint", "")), category_id,
                                str(form.get("payment", "")).strip(), reserve_id,
                                str(form.get("reserve_amount", "")).strip())
    except (LightningError, ValueError) as exc:
        message = str(exc) if isinstance(exc, LightningError) else str(ValidationError("Choose valid review options."))
        workflow = ActivityReview(c)
        try:
            detail = workflow.summary(transaction_id)
        except LightningError as missing:
            return redirect("/activity", str(missing))
        return render(request, _template(request, "detail"), status_code=400, detail=detail, error=message)
    return redirect(f"/activity/{transaction_id}", "Review changes saved.")
