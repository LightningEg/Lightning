"""The Zakat tab: an estimate by the common rule, worked out by `lightning/zakat.py`. Routes only parse the form
and draw what the service returns."""
from __future__ import annotations

from fastapi import APIRouter, Request

from lightning.core.dates import fmt_date, today
from lightning.core.errors import LightningError
from lightning.zakat import ZAKAT_CATEGORY

from .. import charts
from ..web import container, redirect, render

router = APIRouter()


def _payment_link(c) -> str:
    """Where recording zakat paid starts: the entry sheet of the first bank or wallet, in the Zakat category."""
    account = next((a for a in c.accounts.list(active_only=True) if a.account_type.value in ("BANK", "CASH")), None)
    if account is None:
        return ""
    category = c.categories.get_by_code(ZAKAT_CATEGORY)
    return f"/accounts/{account.id}/transaction/new?category_id={category.id}&return_to=/zakat"


@router.post("/zakat/enabled")
async def switch_zakat(request: Request):
    """Settings › Zakat: show or hide zakat everywhere. Turning it off keeps its settings."""
    form = await request.form()
    on = form.get("on") == "1"
    container(request).zakat.set_enabled(on)
    return redirect("/zakat" if on else "/settings", "Zakat is on." if on else "Zakat is off.")


@router.get("/zakat")
async def zakat_page(request: Request):
    c = container(request)
    if not c.zakat.enabled():
        return redirect("/settings", "Zakat is off. Turn it on in Settings.")
    a = c.zakat.assess(today())
    paid_meter = (charts.meter(a.paid, a.zakat_due) if a.zakat_due and a.zakat_day and a.paid is not None else None)
    return render(request, "zakat.html", a=a, paid_meter=paid_meter, payment_link=_payment_link(c),
                  today_iso=fmt_date(today()))


@router.post("/zakat/settings")
async def save_zakat_settings(request: Request):
    c = container(request)
    if not c.zakat.enabled():
        return redirect("/settings", "Zakat is off. Turn it on in Settings.")
    form = await request.form()
    old = c.zakat.settings()
    try:
        if form.get("only_day") == "1":  # the first-time form on the page: only the zakat day changes
            c.zakat.save_settings(str(form.get("zakat_day", "")), old.typed_nisab, old.count_worn_gold,
                                  old.deduct_debts_due)
            return redirect("/zakat", "Zakat day saved.")
        c.zakat.save_settings(str(form.get("zakat_day", "")), str(form.get("typed_nisab", "")),
                              form.get("count_worn_gold") == "1", form.get("deduct_debts_due") == "1")
    except LightningError as exc:
        return redirect("/settings?section=zakat", exc.message)
    return redirect("/settings?section=zakat", "Zakat settings saved.")
