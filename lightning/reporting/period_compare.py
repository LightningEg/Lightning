"""Spending figures of the PC analysis and Spending pages, worked out from the spending lines (IT-12AE4).

Compare periods (one row per category or payee: this period, the other and the difference), Item analysis (a
monthly trend, its total and average, the top payments) and the Spending tab's cards (against the period before,
the usual month, the average payment). The pages hand in what they listed; every sum is made here."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal

from lightning.core.money import ZERO


def compare_rows(entries: Iterable[tuple[str, str, str, int | None, Decimal]]) -> list[dict]:
    """``entries`` are (which, key, name, id, value) with ``which`` "a" (this period) or "b" (the other): one row
    per key with both periods' totals, the difference and its percent of the other period, biggest change first."""
    rows: dict[str, dict] = {}
    for which, key, name, item_id, value in entries:
        row = rows.setdefault(key, {"key": key, "name": name, "id": item_id, "a": ZERO, "b": ZERO})
        row[which] += value
    out = []
    for row in rows.values():
        if row["a"] == ZERO and row["b"] == ZERO:
            continue
        row["diff"] = row["a"] - row["b"]
        row["pct"] = (row["diff"] / row["b"] * 100).quantize(Decimal("1")) if row["b"] > ZERO else None
        out.append(row)
    return sorted(out, key=lambda r: -abs(r["diff"]))


@dataclass(frozen=True)
class CompareTotals:
    total_a: Decimal
    total_b: Decimal

    @classmethod
    def of(cls, rows: Iterable[dict]) -> CompareTotals:
        rows = list(rows)
        return cls(sum((r["a"] for r in rows), ZERO), sum((r["b"] for r in rows), ZERO))

    @property
    def diff(self) -> Decimal:
        return self.total_a - self.total_b


def item_trend(month_keys: Iterable[str], lines: Iterable[dict], payee: Callable[[dict], str], this_key: str,
               last_key: str, top_shown: int) -> dict:
    """One category, account or payee over the months: each month's total and its height against the peak,
    the total, the monthly average, this month and last, how many payments and the biggest ones."""
    months: dict[str, Decimal] = {key: ZERO for key in month_keys}
    by_txn: dict[int, dict] = {}
    for row in lines:
        months[row["date"][:7]] = months.get(row["date"][:7], ZERO) + row["value"]
        entry = by_txn.setdefault(row["transaction_id"], {"id": row["transaction_id"], "date": row["date"],
                                                          "ref": row["ref"], "payee": payee(row), "value": ZERO})
        entry["value"] += row["value"]
    total = sum(months.values(), ZERO)
    peak = max(months.values(), default=ZERO)
    trend = [{"month": k, "value": v, "pct": int(v / peak * 100) if peak > ZERO else 0} for k, v in months.items()]
    return {"trend": trend, "total": total, "average": (total / len(months)).quantize(Decimal("0.01")) if months else ZERO,
            "this_month": months.get(this_key, ZERO), "last_month": months.get(last_key, ZERO),
            "count": len(by_txn),
            "top": sorted((e for e in by_txn.values() if e["value"] > ZERO), key=lambda e: -e["value"])[:top_shown]}


def change(now: Decimal, then: Decimal) -> tuple[Decimal, Decimal | None]:
    """Now against then: the difference, and its size as a percent of then (None when then is zero)."""
    diff = now - then
    return diff, (abs(diff) / then * 100 if then else None)


def total(values: Iterable[Decimal]) -> Decimal:
    return sum(values, ZERO)


def average(values: Iterable[Decimal], count: int) -> Decimal | None:
    """The average of ``count`` payments (None with none)."""
    return sum(values, ZERO) / count if count else None


def usual_over(usual: Decimal | None, months: int) -> Decimal | None:
    """The usual month's money out over ``months`` months."""
    return usual * months if usual is not None else None


def ratio(part: Decimal, whole: Decimal) -> Decimal:
    """``part`` as a multiple of ``whole`` (the largest payment against the average one)."""
    return part / whole


def share(part: Decimal, whole: Decimal) -> Decimal:
    """``part`` as a percent of ``whole``."""
    return part / whole * 100
