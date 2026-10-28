"""PC analysis pages (owner, 2026-10-28): Compare periods (P2), Item analysis (P10), Reports (P11).

They read the same spending lines as the Spending tab (``reporting.spending_lines``), so a category or
payee here always adds up to the figure shown there. Nothing on these pages writes."""
from __future__ import annotations

import calendar
import csv
import re
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response

from lightning.core.dates import fmt_date, parse_date, today
from lightning.core.errors import LightningError
from lightning.core.money import ZERO, fmt

from ..web import container, render

router = APIRouter()

TREND_MONTHS = 12
TOP_SHOWN = 10


# ---- periods ---------------------------------------------------------------------------------------------

def _month_bounds(day: date) -> tuple[date, date]:
    return day.replace(day=1), day.replace(day=calendar.monthrange(day.year, day.month)[1])


def _shift_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def preset_periods(kind: str, now: date | None = None) -> tuple[tuple[date, date], tuple[date, date]]:
    """This period (to date) against the same days of the one before: month, quarter or year."""
    now = now or parse_date(today())
    if kind == "quarter":
        first = date(now.year, (now.month - 1) // 3 * 3 + 1, 1)
        back = _shift_months(first, -3)
        span = (now - first).days
        return (first, now), (back, min(back + timedelta(days=span), first - timedelta(days=1)))
    if kind == "year":
        first = date(now.year, 1, 1)
        back = date(now.year - 1, 1, 1)
        return (first, now), (back, _shift_months(now, -12))
    first, _ = _month_bounds(now)
    back = _shift_months(first, -1)
    return (first, now), (back, min(_shift_months(now, -1), first - timedelta(days=1)))


def _periods(request: Request) -> tuple[str, tuple[date, date], tuple[date, date]]:
    qp = request.query_params
    kind = str(qp.get("preset", "") or "month")
    a, b = preset_periods(kind if kind in ("month", "quarter", "year") else "month")
    try:
        if qp.get("a_from") and qp.get("a_to") and qp.get("b_from") and qp.get("b_to"):
            a = (parse_date(qp["a_from"]), parse_date(qp["a_to"]))
            b = (parse_date(qp["b_from"]), parse_date(qp["b_to"]))
            kind = "custom"
    except (LightningError, ValueError):
        pass
    a = (min(a), max(a))
    b = (min(b), max(b))
    return kind, a, b


# ---- figures ---------------------------------------------------------------------------------------------

def _lines(c, start: date, end: date) -> list[dict]:
    return c.reporting.spending_lines(fmt_date(start), fmt_date(end))


def _payee(row) -> str:
    return (row.get("counterparty") or row.get("description") or "No counterparty").strip()


def compare(c, a: tuple[date, date], b: tuple[date, date], by: str = "category") -> list[dict]:
    """One row per category (top two levels) or payee: this period, the other, and the difference."""
    def key_of(row):
        if by == "payee":
            name = _payee(row)
            return name, name, None
        cat = c.categories.get(row["category_id"])
        code = ".".join(cat.code.split(".")[:3])
        top = c.categories.get_by_code(code) or cat
        return top.code, top.name, top.id  # its own name: never "L1 › L2" (A16)

    rows: dict[str, dict] = {}
    for which, (start, end) in (("a", a), ("b", b)):
        for line in _lines(c, start, end):
            key, name, item_id = key_of(line)
            row = rows.setdefault(key, {"key": key, "name": name, "id": item_id, "a": ZERO, "b": ZERO})
            row[which] += line["value"]
    out = []
    for row in rows.values():
        if row["a"] == ZERO and row["b"] == ZERO:
            continue
        row["diff"] = row["a"] - row["b"]
        row["pct"] = (row["diff"] / row["b"] * 100).quantize(Decimal("1")) if row["b"] > ZERO else None
        out.append(row)
    return sorted(out, key=lambda r: -abs(r["diff"]))


def item_lines(c, kind: str, item, start: date, end: date) -> list[dict]:
    lines = _lines(c, start, end)
    if kind == "category":
        prefix = item.code
        return [r for r in lines if (code := c.categories.get(r["category_id"]).code) == prefix
                or code.startswith(prefix + ".")]
    if kind == "account":
        return [r for r in lines if r["account_id"] == item.id]
    return [r for r in lines if _payee(r).casefold() == str(item).casefold()]


def analyse(c, kind: str, item, now: date | None = None) -> dict:
    """Trend over the last twelve months, total, monthly average, this month against last, top payments."""
    now = now or parse_date(today())
    first = _shift_months(now.replace(day=1), -(TREND_MONTHS - 1))
    lines = item_lines(c, kind, item, first, now)
    months: dict[str, Decimal] = {}
    cursor = first
    while cursor <= now:
        months[cursor.strftime("%Y-%m")] = ZERO
        cursor = _shift_months(cursor, 1)
    by_txn: dict[int, dict] = {}
    for row in lines:
        months[row["date"][:7]] = months.get(row["date"][:7], ZERO) + row["value"]
        entry = by_txn.setdefault(row["transaction_id"], {"id": row["transaction_id"], "date": row["date"],
                                                          "ref": row["ref"], "payee": _payee(row), "value": ZERO})
        entry["value"] += row["value"]
    total = sum(months.values(), ZERO)
    this_key, last_key = now.strftime("%Y-%m"), _shift_months(now.replace(day=1), -1).strftime("%Y-%m")
    peak = max(months.values(), default=ZERO)
    trend = [{"month": k, "value": v, "pct": int(v / peak * 100) if peak > ZERO else 0} for k, v in months.items()]
    return {"trend": trend, "total": total, "average": (total / len(months)).quantize(Decimal("0.01")) if months else ZERO,
            "this_month": months.get(this_key, ZERO), "last_month": months.get(last_key, ZERO),
            "count": len(by_txn), "date_from": fmt_date(first), "date_to": fmt_date(now),
            "top": sorted((e for e in by_txn.values() if e["value"] > ZERO), key=lambda e: -e["value"])[:TOP_SHOWN]}


NUMBER = re.compile(r"-?\d+(\.\d+)?")


def _csv(filename: str, headings: tuple, rows: list[tuple]) -> Response:
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(headings)
    for row in rows:
        # a name that starts like a formula is written as text; a number such as -200.00 stays a number
        writer.writerow(["'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@"))
                         and not NUMBER.fullmatch(v.strip()) else v for v in row])
    return Response("\ufeff" + buffer.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


# ---- pages -----------------------------------------------------------------------------------------------

@router.get("/spending/compare")
async def compare_page(request: Request):
    c = container(request)
    kind, a, b = _periods(request)
    by = "payee" if request.query_params.get("by") == "payee" else "category"
    rows = compare(c, a, b, by)
    total_a, total_b = sum((r["a"] for r in rows), ZERO), sum((r["b"] for r in rows), ZERO)
    if request.query_params.get("format") == "csv":
        return _csv(f"lightning-compare-{fmt_date(a[0])}-{fmt_date(b[0])}.csv",
                    ("item", f"{fmt_date(a[0])} to {fmt_date(a[1])}", f"{fmt_date(b[0])} to {fmt_date(b[1])}", "difference"),
                    [(r["name"], str(r["a"]), str(r["b"]), str(r["diff"])) for r in rows])
    keep = {"a_from": fmt_date(a[0]), "a_to": fmt_date(a[1]), "b_from": fmt_date(b[0]), "b_to": fmt_date(b[1]), "by": by}
    diff, against = total_a - total_b, {"sa": fmt_date(b[0]), "sb": fmt_date(b[1])}
    # the page's answer in words, under its title (A05)
    status = (f"Money out is the same as {against['sa']} to {against['sb']}." if diff == ZERO else
              f"Money out is {fmt(abs(diff), 0)} {'lower' if diff < 0 else 'higher'} than {against['sa']} to {against['sb']}.")
    return render(request, "analysis/compare.html", rows=rows, kind=kind, by=by, a=a, b=b, status=status,
                  total_a=total_a, total_b=total_b, total_diff=diff,
                  keep_qs=urlencode(keep), base=c.base_currency, fmt_date=fmt_date)


def _item(c, kind: str, request: Request, item_id: int | None):
    if kind == "category":
        return c.categories.get(item_id), c.categories.display_name(item_id)
    if kind == "account":
        account = c.accounts.get(item_id)
        return account, account.name
    name = str(request.query_params.get("name", "")).strip()
    if not name:
        raise HTTPException(404)
    return name, name


@router.get("/analysis/{kind}/{item_id:int}")
@router.get("/analysis/{kind}")
async def item_page(request: Request, kind: str, item_id: int | None = None):
    c = container(request)
    if kind not in ("category", "account", "payee") or (kind != "payee" and item_id is None):
        raise HTTPException(404)
    try:
        item, name = _item(c, kind, request, item_id)
    except LightningError:
        raise HTTPException(404)
    if item is None:
        raise HTTPException(404)
    data = analyse(c, kind, item)
    if request.query_params.get("format") == "csv":
        return _csv("lightning-item.csv", ("month", "spent"), [(t["month"], str(t["value"])) for t in data["trend"]])
    search = name if kind != "account" else ""
    edit_href = (f"/accounts/{item.id}?" if kind == "account" else "/transactions?") + urlencode(
        {k: v for k, v in (("q", search), ("date_from", data["date_from"]), ("date_to", data["date_to"])) if v})
    rule_href = "/rules/new?" + urlencode({"counterparty": name} if kind == "payee" else
                                          {"category_id": item.id} if kind == "category" else {"account_id": item.id})
    return render(request, "analysis/item.html", kind=kind, item_name=name, data=data, edit_href=edit_href,
                  rule_href=rule_href, base=c.base_currency,
                  csv_href=str(request.url.include_query_params(format="csv")))


@router.get("/reports")
async def reports_page(request: Request):
    c = container(request)
    presets = []
    for kind, label in (("month", "This month against last month"), ("quarter", "This quarter against last quarter"),
                        ("year", "This year against last year")):
        a, b = preset_periods(kind)
        rows = compare(c, a, b)
        total_a, total_b = sum((r["a"] for r in rows), ZERO), sum((r["b"] for r in rows), ZERO)
        presets.append({"kind": kind, "label": label, "a": a, "b": b, "total_a": total_a, "total_b": total_b,
                        "diff": total_a - total_b, "mover": rows[0] if rows else None})
    try:
        views = c.saved_views.list(None)
    except (LightningError, TypeError, AttributeError):
        views = []
    return render(request, "analysis/reports.html", presets=presets, views=views, base=c.base_currency, fmt_date=fmt_date)
