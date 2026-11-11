"""Budget, flexible first (IV-3AY9, guideline C11.2): "How much is left, and on what?". The hero is the everyday money
left in the month's plan (the forecaster's EverydayBudget, the figure the PC's Everyday card shows), the list holds
flexible categories only with *left* as the figure, and every bill and loan payment is one Fixed costs row, so a
fixed cost never drags the pace or shows as "0 left". Services calculate; this module only picks and orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal

from lightning.core.dates import month_of, parse_month
from lightning.planning.salary_day import payday_to_plan
from lightning.ui.charts import ranked_donut

ZERO = Decimal(0)
ATTENTION = 4          # Needs attention shows at most this many, then "and N more"
AHEAD_POINTS = 10      # a category this many points ahead of the month's pace needs attention


@dataclass(frozen=True)
class CategoryRow:
    category_id: int
    name: str
    limit: Decimal
    spent: Decimal
    left: Decimal              # negative when over
    share: float               # 0-100 for the bar
    attention: bool
    state: str = "ok"          # "over" | "ahead" (ahead of the month's pace) | "done" (spent to the plan, nothing left) | "ok"


@dataclass(frozen=True)
class BudgetScreen:
    month: str
    prev_month: str
    next_month: str            # "" for the current month
    state: str                 # "no_plan" | "past" | "current" | "future"
    left: Decimal | None       # everyday money left in the plan; None with no plan
    used_pct: int | None
    pace_gap: Decimal | None   # everyday spent less the pace; negative is under it (current month only)
    per_day: Decimal | None
    attention: tuple[CategoryRow, ...]
    attention_more: int
    categories: tuple[CategoryRow, ...]   # every flexible category, least left first
    fixed_planned: Decimal
    fixed_paid: Decimal
    fixed_count: int
    move: dict | None = None          # room to cover the largest overspend: {name, amount, href}
    raise_offer: dict | None = None   # "your income went up": recurring pay is above the plan's average (a current month only)
    month_bar: dict | None = None     # IV-11D2: the everyday plan as one bar: spent, left, over (amounts add to the plan)
    spend: dict | None = None         # IV-11D5: where the month went: a donut of four categories then Other, and its rows
    working: object = None            # NF-12AB4: the hero's working, for its sheet
    payday: dict | None = None        # 3AY9: {amount, date} from the salary's day until this month's plan is saved


def _shift(month: str, step: int) -> str:
    first, _ = parse_month(month)
    return month_of(first + timedelta(days=32) if step > 0 else first - timedelta(days=1))


def build(c, day: date, month: str = "") -> BudgetScreen:
    this = month_of(day)
    try:
        first, last = parse_month(month or this)
    except Exception:
        first, last = parse_month(this)
    shown = month_of(first)
    schedule = c.schedules.view()
    prev, nxt = _shift(shown, -1), "" if shown >= this else _shift(shown, 1)
    if not c.budgets.has_plan(shown, schedule=schedule):
        return BudgetScreen(shown, prev, nxt, "no_plan", None, None, None, None, (), 0, (), ZERO, ZERO, 0)
    e = c.forecaster.everyday(shown, day)
    state = "current" if e.current else ("past" if last < day else "future")
    left = e.everyday_left
    used = int(e.everyday_spent / e.everyday_plan * 100) if e.everyday_plan > 0 else None
    pace_pct = Decimal(e.day) / e.days_in_month * 100 if state == "current" and e.days_in_month else None
    rows = []
    view = c.budgets.month_view(shown, schedule=schedule)
    seen = set()
    for section in view.sections:
        for line in section.lines:
            if (line.depth <= 1 or line.direct is None or line.from_loans or line.from_bills
                    or line.category_id in seen or line.available is None):
                continue
            seen.add(line.category_id)
            limit, spent = line.available, line.planned_actual
            if not limit and not spent:
                continue
            share = float(min(max(spent / limit * 100, ZERO), Decimal(100))) if limit > 0 else (100.0 if spent > 0 else 0.0)
            gap = limit - spent
            ahead = gap > 0 and pace_pct is not None and spent / limit * 100 >= pace_pct + AHEAD_POINTS
            kind = "over" if gap < 0 else ("ahead" if ahead else ("done" if limit > 0 and gap == 0 else "ok"))
            rows.append(CategoryRow(line.category_id, line.name, limit, spent, gap, share,
                                    state != "past" and kind in ("over", "ahead"), kind))
    rows.sort(key=lambda r: (r.left, r.name.casefold()))
    needs = [r for r in rows if r.attention]
    shown_needs = tuple(needs[:ATTENTION])
    listed = tuple(r for r in rows if r not in shown_needs)     # a category is never listed twice
    paid = planned = ZERO
    for p in e.payments:
        if p.due_date[:7] != shown:
            continue
        planned += c.planning.amount_in_base(p, p.amount, day)
        paid += c.planning.amount_in_base(p, p.amount - p.still_owed, day)
    count = sum(1 for p in e.payments if p.due_date[:7] == shown)
    move = _cover(c, shown, schedule, [r for r in rows if r.left < 0], e.room) if state == "current" else None
    return BudgetScreen(shown, prev, nxt, state, left, used,
                        (e.everyday_spent - e.pace) if state == "current" else None, e.per_day,
                        shown_needs, max(len(needs) - ATTENTION, 0), listed, planned, paid, count,
                        move, c.health.raise_offer(shown) if state == "current" else None,
                        month_bar(e.everyday_plan, e.everyday_spent), spend_donut(rows, e.everyday_spent),
                        working=e.everyday_left_working,
                        payday=payday_to_plan(c.db, c.settings, day) if state == "current" else None)


def month_bar(plan: Decimal, spent: Decimal) -> dict | None:
    """IV-11D2: spent, left in plan and over as one bar. ``spent + left`` is the plan; ``over`` is spending past it.
    Widths are shares of the longer of plan and spent, so an overspent bar shows where the plan ended."""
    if plan <= 0 and spent <= 0:
        return None
    part_spent, part_left, part_over = min(spent, plan), max(plan - spent, ZERO), max(spent - plan, ZERO)
    whole = part_spent + part_left + part_over
    return {"spent": part_spent, "left": part_left, "over": part_over, "plan": plan,
            "w_spent": float(part_spent / whole * 100), "w_left": float(part_left / whole * 100),
            "w_over": float(part_over / whole * 100)}


def spend_donut(rows: list[CategoryRow], spent: Decimal) -> dict | None:
    """IV-11D5, BV-12O: where the month went. Fixed costs paid are already inside their categories (rent in Housing), so
    the slices are the categories alone and any spending they leave out joins Other: the total is the plan's Spent."""
    slices = [{"label": r.name, "value": r.spent} for r in rows]
    rest = spent - sum((r.spent for r in rows if r.spent > 0), ZERO)
    if rest > 0:
        slices.append({"label": "Other", "value": rest, "other": True})
    d = ranked_donut(slices)
    return d if d["segments"] else None


def _cover(c, month: str, schedule, over: list[CategoryRow], room: dict) -> dict | None:
    """The category with the most room left (its bills still to pay set aside) that can cover the largest overspend;
    both need a plan of their own, as Move room asks. The PC's Budget makes the same offer."""
    if not over:
        return None
    target = min(over, key=lambda r: r.left)
    plans = c.budgets.amounts_for(month, loans=False, schedule=schedule)
    if target.category_id not in plans:
        return None
    amount = (-target.left).to_integral_value(rounding=ROUND_CEILING)
    best = max(((left, cid) for cid, left in room.items()
                if cid != target.category_id and cid in plans and left >= amount), default=None)
    if best is None:
        return None
    return {"name": c.categories.get(best[1]).name, "amount": amount,
            "href": f"/budget/move?month={month}&to={target.category_id}&from={best[1]}&amount={amount}"}
