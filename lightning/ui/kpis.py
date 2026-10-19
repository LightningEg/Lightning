"""KPI cards (guideline 3.32, A08): five fixed slots, the comparison always there.

1 label and chip · 2 figure · 3 comparison · 4 one micro-visual · 5 one line or one action. Builders only phrase
figures that services computed and compare two of them at most, as keynotes.py does; they never work out a
money figure of their own. A card is a dict the `kpi_row` macro draws:

  label    the figure's one name (lightning/core/figures.py)
  tone     what the figure means (A03): in · hold · out · over; it colours the edge and the micro-visual
  needs    True tints the card (Needs you); Watch stays quiet (A08)
  chip     {"text", "tone": good | bad | over | quiet, "arrow": up | down | None}
  value    a Decimal, or None for "—" (A08.5); kind money | rate | count; signed for a change
  compare  {"figure", "tone": good | bad | hold | plain, "text"}: required, a card without one is a row (A08.1)
  visual   {"kind": spark | meter | segments | timeline | columns, ...} (A08.4), or None
  line     {"text", "action", "href", "popup"}
  href     what the card opens
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from lightning.core.dates import month_of, parse_date, parse_month
from lightning.core.figures import label as figure_label
from lightning.core.money import ZERO

from . import charts
from .keynotes import fmt

TONES = {"in", "hold", "out", "over"}


def chip(text: str, tone: str = "quiet", arrow: str | None = None) -> dict:
    return {"text": text, "tone": tone, "arrow": arrow}


def compare(text: str, figure: str = "", tone: str = "plain") -> dict:
    return {"figure": figure, "tone": tone, "text": text}


def line(text: str = "", action: str = "", href: str = "", popup: bool = False) -> dict:
    return {"text": text, "action": action, "href": href, "popup": popup}


def card(label: str, value: Decimal | None, comparison: dict, *, tone: str, chip_: dict | None = None,
         visual: dict | None = None, line_: dict | None = None, href: str = "", kind: str = "money",
         signed: bool = False, needs: bool = False, key: str = "") -> dict:
    """One KPI card. The comparison is what makes it a KPI (A08.1, A16 "A figure alone")."""
    if not comparison or not (comparison.get("text") or comparison.get("figure")):
        raise ValueError(f"KPI card {label!r} has no comparison")
    if tone not in TONES:
        raise ValueError(f"KPI card {label!r}: tone {tone!r} is not one of {sorted(TONES)}")
    return {"key": key, "label": label, "value": value, "kind": kind, "signed": signed, "tone": tone, "needs": needs,
            "chip": chip_, "compare": comparison, "visual": visual, "line": line_ or line(), "href": href}


def row(cards: list[dict | None]) -> list[dict]:
    """Two to four cards that fill the row (A09); a lone card is a Lead card's job, not a row's."""
    shown = [c for c in cards if c]
    return shown[:4] if len(shown) >= 2 else []


# ── micro-visuals (A08.4) ────────────────────────────────────────────────────────────────────────────────────
def spark(values: list[Decimal | None], mark: str = "last") -> dict | None:
    s = charts.sparkline(values, mark)
    return {"kind": "spark", **s} if s.get("points") else None


def meter(used: Decimal, total: Decimal, tick: Decimal | None = None, tick_label: str = "") -> dict | None:
    if not total or total <= 0:
        return None
    width = float(max(min(used / total * 100, Decimal(100)), ZERO))
    at = float(max(min(tick / total * 100, Decimal(100)), ZERO)) if tick is not None else None
    return {"kind": "meter", "width": width, "tick": at, "tick_label": tick_label, "over": used > total}


def segments(parts: list[tuple[str, Decimal, str]]) -> dict | None:
    """What the figure is made of: (name, value, tone) for two to four parts; empty parts are left out."""
    shown = [(name, value, tone) for name, value, tone in parts if value and value > 0]
    total = sum((value for _, value, _ in shown), ZERO)
    if len(shown) < 2 or not total:
        return None
    return {"kind": "segments", "parts": [{"name": name, "value": value, "tone": tone, "share": float(value / total * 100)}
                                         for name, value, tone in shown]}


def timeline(day: date, until: str | None, late: list, ahead: list) -> dict | None:
    """Payments from today to payday: late ones in a cluster before Today, the rest at their date."""
    if not late and not ahead:
        return None
    end = parse_date(until) if until else None
    span = max((end - day).days, 1) if end else max([(parse_date(p.due_date) - day).days for p in ahead] + [1])
    dots = [{"x": 18 + 80 * max((parse_date(p.due_date) - day).days, 0) / span, "late": False,
             "title": f"{p.item.name} · {p.due_date}"} for p in ahead]
    return {"kind": "timeline", "late": min(len(late), 3), "dots": dots, "payday": bool(end)}


def columns(values: list[Decimal], running: bool = False) -> dict | None:
    """The last periods, one column each; positive green, negative strong rose; the running one hatched."""
    if len(values) < 2:
        return None
    top = max((abs(v) for v in values), default=ZERO) or Decimal(1)
    return {"kind": "columns", "bars": [{"height": float(abs(v) / top * 100), "negative": v < 0,
                                         "running": running and i == len(values) - 1} for i, v in enumerate(values)]}


# ── Budget ─────────────────────────────────────────────────────────────────────────────────────────────────
def budget_month(e, *, over: list[dict], check, raise_offer: dict | None, move: dict | None, month: str) -> list[dict]:
    """A month's four cards: Left in plan, Everyday spending, Over plan (only when something is) and what the
    plan leaves to save. ``e`` is the forecaster's EverydayBudget; ``over`` the categories over plan, largest
    first, each {"name", "over"}; ``move`` the room to cover the largest from, {"href", "name", "amount"}."""
    previous = month_of(parse_month(month)[0] - timedelta(days=1))
    if e.left < 0:
        left_compare = compare("over the plan", fmt(-e.left), "bad")
    elif e.current and e.days_left:
        left_compare = (compare(f"for everyday, about {fmt(e.per_day)} a day", fmt(e.everyday_left), "good") if e.everyday_left > 0
                        else compare("for everyday: bills take the rest", "0", "bad"))
    else:
        left_compare = compare("of the plan spent", f"{e.spent / e.planned * 100:.0f}%" if e.planned else "—")
    left_visual = (segments([("Spent", e.spent, "out"), ("Bills to pay", e.bills_to_pay, "neutral"), ("Everyday", e.everyday_left, "in")])
                   if e.current else segments([("Spent", min(e.spent, e.planned), "out"), ("Left", max(e.left, ZERO), "in")]))
    cards = [card(figure_label("left_in_plan"), e.left, left_compare, tone="in" if e.left >= 0 else "over", key="left",
                  chip_=chip(f"{e.days_left} days left" if e.current and e.days_left else month),
                  visual=left_visual or meter(e.spent, e.planned),
                  line_=line(f"Spent {fmt(e.spent)} of {fmt(e.planned)} planned"), href="#budget-meters")]

    if e.current and e.day:
        gap = e.everyday_spent - e.pace
        pace_compare = (compare("under the plan's pace", fmt(-gap), "good") if gap <= 0
                        else compare("over the plan's pace", fmt(gap), "bad"))
        before = e.last_month_same_day
        tail = (line(f"{_signed(e.everyday_spent - before)} against {previous} by day {e.day}") if before is not None
                else line(f"Everyday plan {fmt(e.everyday_plan)}"))
        cards.append(card("Everyday spending", e.everyday_spent, pace_compare, tone="out", key="everyday",
                          chip_=chip(f"by day {e.day}"), visual=meter(e.everyday_spent, e.everyday_plan, e.pace, "pace"),
                          line_=tail, href="#budget-pace"))
    elif e.day:
        before = e.last_month_by_day[-1] if e.last_month_by_day else None
        change = (compare(f"against {previous}", _signed(e.everyday_spent - before), "good" if e.everyday_spent <= before else "bad")
                  if before is not None else compare("of the everyday plan", f"{e.everyday_spent / e.everyday_plan * 100:.0f}%" if e.everyday_plan > 0 else "—"))
        cards.append(card("Everyday spending", e.everyday_spent, change, tone="out", key="everyday", chip_=chip(month),
                          visual=meter(e.everyday_spent, e.everyday_plan), line_=line(f"Everyday plan {fmt(e.everyday_plan)}"),
                          href="#budget-pace"))

    if over:
        total = sum((row["over"] for row in over), ZERO)
        names = len(over)
        parts = [(row["name"], row["over"], "over" if i == 0 else "out") for i, row in enumerate(over[:3])]
        if len(over) > 3:
            parts.append(("Other", sum((row["over"] for row in over[3:]), ZERO), "neutral"))
        act = (line(action=f"Move {fmt(move['amount'])} from {move['name']}", href=move["href"], popup=True) if move
               else line(action="See categories", href="#budget-meters"))
        cards.append(card("Over plan", total, compare("over their plan", f"{names} categor{'y' if names == 1 else 'ies'}", "bad"),
                          tone="over", needs=True, key="over", chip_=chip("Needs you", "over"),
                          visual=segments(parts) or meter(total, total), line_=act, href="#budget-meters"))

    if check is not None and check.planned is not None and check.plan_saves is not None and check.planned_savings_rate is not None:
        rate, target = check.planned_savings_rate, check.target_percent
        scale = max(rate, target, Decimal(1)) * Decimal("1.4")
        if raise_offer:
            tail = line(f"Income up {fmt(raise_offer['raise'])}", "Raise the plan", f"/budget/raise?month={month}", popup=True)
        elif check.over_by:
            tail = line(f"Plan {fmt(check.over_by)} less to keep {fmt(check.to_save)} a month")
        else:
            tail = line(f"{fmt(check.to_save)} a month to save")
        good = not check.over_by
        cards.append(card("Plan leaves to save", check.plan_saves,
                          compare(f"of income, target {target.normalize():f}%", f"{rate:.0f}%", "good" if good else "bad"),
                          tone="in", key="saves", chip_=chip("Good", "good") if good else chip("Watch"),
                          visual=meter(rate, scale, target, f"{target.normalize():f}%"), line_=tail,
                          href="/settings?section=financial-health"))
    return row(cards)


def budget_period(spent: Decimal, planned: Decimal, months: list[tuple[str, Decimal, bool]], period_label: str) -> list[dict]:
    """A longer period (YTD, All time, Custom): what was spent of the plan, and how many finished months ended
    within it. ``months`` is (yyyy-mm, left in plan, finished) for each month with a plan; the running one is hatched."""
    if not planned or planned <= 0:
        return []
    left = planned - spent
    ended = [value for _, value, finished in months if finished]
    within = sum(1 for value in ended if value >= 0)
    cards = [card("Spent", spent, compare(f"of the {fmt(planned)} plan", f"{spent / planned * 100:.0f}%",
                                          "good" if spent <= planned else "bad"),
                  tone="out", key="spent", chip_=chip(period_label), visual=meter(spent, planned),
                  line_=line(f"Planned {fmt(planned)}"), href="#budget-meters"),
             card(figure_label("left_in_plan"), left,
                  compare("ended within plan", f"{within} of {len(ended)} month{'' if len(ended) == 1 else 's'}",
                          "good" if within == len(ended) else "bad")
                  if ended else compare("of the plan left", f"{max(left, ZERO) / planned * 100:.0f}%"),
                  tone="in" if left >= 0 else "over", key="left", chip_=chip(period_label),
                  visual=columns([value for _, value, _ in months], running=bool(months) and not months[-1][2]),
                  line_=line("Each month's left in plan"),
                  href="#budget-meters")]
    return row(cards)


# ── Cash planning ──────────────────────────────────────────────────────────────────────────────────────────
def cash_plan(f, *, day: date, before: list, late: list, free_then: Decimal | None, then: str, past_free: list[Decimal],
              position, monthly_spending: Decimal | None, has_income: bool) -> list[dict]:
    """Safe to spend, Free cash, Due before payday and the lowest point ahead, each against something."""
    parts = dict(f.safe_to_spend_parts)
    until = f.next_income_date
    if f.safe_to_spend < 0:
        safe_compare = compare("more is promised than your free cash", fmt(-f.safe_to_spend), "bad")
    elif f.free_cash > 0:
        safe_compare = compare("of your free cash", f"{f.safe_to_spend / f.free_cash * 100:.0f}%", "hold")
    else:
        safe_compare = compare("No free cash today")
    saving = sum((-parts.get(figure_label(k), ZERO) for k in ("saving_for_goals", "emergency_top_up", "savings_target_rest")), ZERO)
    due = -parts.get(figure_label("payments_before_next_income"), ZERO) - parts.get("Gam'eya instalments before next income", ZERO)
    cards = [card(figure_label("safe_to_spend"), f.safe_to_spend, safe_compare, tone="hold" if f.safe_to_spend >= 0 else "over",
                  key="safe", chip_=chip(f"until {until}" if until else "3 months"),
                  visual=segments([("Safe", max(f.safe_to_spend, ZERO), "hold"),
                                   ("Budget", -parts.get(figure_label("left_in_plan_after_bills"), ZERO), "out"),
                                   ("Savings", saving, "in"), ("Due", due, "over")]),
                  line_=line("On top of your plan", "How it is worked out", "#plan-build"), href="#plan-build")]

    if free_then is not None:
        change = f.free_cash - free_then
        free_compare = compare(f"since {then}", _signed(change), "good" if change >= 0 else "bad")
        free_chip = chip(month_of(day), "good" if change >= 0 else "bad", "up" if change > 0 else "down" if change < 0 else None)
    else:
        free_compare, free_chip = compare("Your first month: nothing to compare yet"), chip(month_of(day))
    held = (position.kept_apart or ZERO) + (position.reserves or ZERO) + position.bills_due
    cards.append(card(figure_label("free_cash"), f.free_cash, free_compare, tone="hold", key="free", chip_=free_chip,
                      visual=spark([*past_free, f.free_cash]),
                      line_=line(f"Cash you own {fmt(position.cash_you_own)}, less {fmt(held)} set aside or due"), href="/"))

    before_total = sum((p.amount for p in before), ZERO)
    late_total = sum((p.still_owed for p in late), ZERO)
    if late:
        due_compare = compare("already late", fmt(late_total), "bad")
        due_chip = chip(f"{len(late)} late", "bad")
    else:
        due_compare = compare(f"payment{'s' if len(before) != 1 else ''} before payday" if until else "payments in the next 3 months",
                              str(len(before)))
        due_chip = chip(f"{len(before)} payment{'s' if len(before) != 1 else ''}")
    nxt = before[0] if before else None
    due_line = (line(f"Next: {nxt.item.name} · {nxt.due_date}", "See late ones" if late else "", "#plan-next" if late else "")
                if nxt else line("Nothing else is due before then", "See late ones" if late else "", "#plan-next" if late else ""))
    cards.append(card(figure_label("payments_before_next_income"), before_total, due_compare, tone="out", key="before",
                      chip_=due_chip, visual=timeline(day, until, late, before), line_=due_line, href="#plan-next"))

    low = f.lowest if has_income else None
    if low is not None:
        drop = f.free_cash - low.closing
        low_compare = (compare("below today", fmt(drop)) if drop > 0 else compare("above today", fmt(-drop), "good"))
        months_text = (f"{low.closing / monthly_spending:.1f} months of spending at its lowest" if monthly_spending and low.closing > 0
                       else "Runs short: the month ends below zero" if low.closing < 0 else "")
        cards.append(card("Lowest point ahead", low.closing, low_compare, tone="over" if low.closing < 0 else "hold", key="low",
                          chip_=chip(low.month, "over" if low.closing < 0 else "quiet"),
                          visual=spark([f.free_cash, *[m.closing for m in f.months]], "low"),
                          line_=line(months_text, "See the forecast", "#plan-forecast"), href="#plan-forecast"))
    else:
        cards.append(card("Lowest point ahead", None, compare("Add your income to see where cash is heading"), tone="hold", key="low",
                          chip_=chip("—"), line_=line(action="Add income", href="/plan/items/new?kind=INCOME")))
    return row(cards)


def _signed(value: Decimal) -> str:
    return ("+" if value > 0 else "−" if value < 0 else "") + fmt(abs(value))
