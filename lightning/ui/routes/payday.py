from fastapi import APIRouter, Request

from lightning.core.errors import LightningError
from .. import kpis, status
from ..web import container, redirect, render, settled_save

router = APIRouter(prefix="/payday")


@router.get("")
async def payday(request: Request):
    c = container(request)
    return _page(request, c)


def _page(request, c, **extra):
    """IV-12Q1: one short step. The Lead is the cash to share out; the proposal, its bar and Confirm sit beside it."""
    allocation = c.funding.preview()
    lead, split = kpis.payday(allocation)
    pr = allocation["proposal"]
    return render(request, "planning/payday.html", enabled=c.funding.enabled, allocation=allocation,
                  forecast=c.forecaster.forecast(), lead=lead, split=split,
                  status=status.payday(pr["available_before"], pr["unassigned"], c.funding.enabled), **extra)


@router.post("/enable")
async def enable(request: Request):
    c = container(request)
    form = await request.form()
    with settled_save(request, c, undo_label='Cash funding preference'):
        c.settings.set("cash_funding_enabled", "1" if form.get("enabled") == "1" else "0")
    return redirect("/payday", "Cash funding preference saved.")


@router.post("/apply")
async def apply(request: Request):
    c = container(request)
    form = await request.form()
    amounts = {key.removeprefix("category_"): str(value) for key, value in form.items() if key.startswith("category_")}
    reserves = {key.removeprefix("reserve_"): str(value) for key, value in form.items() if key.startswith("reserve_")}
    try:
        with settled_save(request, c):
            c.funding.apply(str(form.get("fingerprint", "")), amounts, reserves)
    except LightningError as exc:
        return _page(request, c, status_code=400, error=exc.message)
    return redirect("/payday", "Cash assigned. No money moved between accounts.")
