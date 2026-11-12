from __future__ import annotations

from fastapi import APIRouter, Request

from lightning.core.dates import fmt_date, month_of, parse_date, parse_month, today
from lightning.core.errors import ValidationError

from ..web import container, redirect, render

router = APIRouter(prefix="/checks")


@router.get("")
async def integrity_page(request: Request):
    raw_date = str(request.query_params.get("date", "")).strip()
    try:
        parsed = parse_date(raw_date) if raw_date else today()
        parse_month(month_of(parsed))
        as_of = fmt_date(parsed)
    except ValidationError as exc:
        return redirect("/checks", exc.message)
    checks = container(request).integrity.checks(as_of)
    counts = {status: sum(check.status == status for check in checks)  # not money: counts
              for status in ("PASS", "ISSUE", "INCOMPLETE")}
    return render(request, "integrity.html", checks=checks, as_of=as_of, counts=counts)
