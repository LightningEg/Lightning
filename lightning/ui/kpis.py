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
from lightning.core.figures import FIGURES, label as figure_label
from lightning.core.money import ZERO, fmt, signed_pct

from . import charts

TONES = {"in", "hold", "out", "over"}


def chip(text: str, tone: str = "quiet", arrow: str | None = None) -> dict:
    return {"text": text, "tone": tone, "arrow": arrow}


def compare(text: str, figure: str = "", tone: str = "plain") -> dict:
    return {"figure": figure, "tone": tone, "text": text}


def line(text: str = "", action: str = "", href: str = "", popup: bool = False) -> dict:
    return {"text": text, "action": action, "href": href, "popup": popup}


# A card whose label is a registry figure carries that figure's key, read by tests through data-fig (IT-12AE1).
FIGURE_KEY_OF = {f.label: key for key, f in FIGURES.items()}


def card(label: str, value: Decimal | None, comparison: dict, *, tone: str, chip_: dict | None = None,
         visual: dict | None = None, line_: dict | None = None, href: str = "", kind: str = "money",
         signed: bool = False, needs: bool = False, key: str = "", working=None) -> dict:
    """One KPI card. The comparison is what makes it a KPI (A08.1, A16 "A figure alone"). With a ``working``
    (lightning.core.working) the figure itself opens How it adds up in place (NF-12AB3), so the card links nowhere else."""
    if not comparison or not (comparison.get("text") or comparison.get("figure")):
        raise ValueError(f"KPI card {label!r} has no comparison")
    if tone not in TONES:
        raise ValueError(f"KPI card {label!r}: tone {tone!r} is not one of {sorted(TONES)}")
    return {"key": key, "fig": FIGURE_KEY_OF.get(label, ""), "label": label, "value": value, "kind": kind, "signed": signed, "tone": tone, "needs": needs,
            "chip": chip_, "compare": comparison, "visual": visual, "line": line_ or line(),
            "href": "" if working is not None else href, "working": working}


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
def budget_month(e, *, over: list[dict], check, raise_offer: dict | None, move: dict | None, month: str, funded_elsewhere: bool = False) -> list[dict]:
    """A month's four cards: Left in plan, Everyday spending, Over plan (only when something is) and what the
    plan leaves to save. ``e`` is the forecaster's EverydayBudget; ``over`` the categories over plan, largest
    first, each {"name", "over"}; ``move`` the room to cover the largest from, {"href", "name", "amount"}."""
    previous = month_of(parse_month(month)[0] - timedelta(days=1))
    if e.left < 0:
        left_compare = compare("over the plan", fmt(-e.left, 0), "bad")
    elif e.current and e.days_left:
        left_compare = (compare(f"for everyday, about {fmt(e.per_day, 0)} a day", fmt(e.everyday_left, 0), "good") if e.everyday_left > 0
                        else compare("for everyday: bills take the rest", "0", "bad"))
    else:
        left_compare = compare("of the plan spent", f"{e.spent / e.planned * 100:.0f}%" if e.planned else "—")
    spent_label = "From monthly plan" if funded_elsewhere else "Spent"
    left_visual = (segments([(spent_label, e.spent, "out"), ("Bills to pay", e.bills_to_pay, "neutral"), ("Everyday", e.everyday_left, "in")])
                   if e.current else segments([(spent_label, min(e.spent, e.planned), "out"), ("Left", max(e.left, ZERO), "in")]))
    cards = [card(figure_label("left_in_plan"), e.left, left_compare, tone="in" if e.left >= 0 else "over", key="left", working=e.left_working,
                  chip_=chip(f"{e.days_left} days left" if e.current and e.days_left else month),
                  visual=left_visual or meter(e.spent, e.planned),
                  line_=line(f"{spent_label} {fmt(e.spent, 0)} of {fmt(e.planned, 0)} planned"), href="#budget-meters")]

    if e.current and e.day:
        gap = e.pace_gap
        pace_compare = (compare("under the plan's pace", fmt(-gap, 0), "good") if gap <= 0
                        else compare("over the plan's pace", fmt(gap, 0), "bad"))
        before = e.last_month_same_day
        tail = (line(f"{_signed(e.everyday_spent - before)} against {previous} by day {e.day}") if before is not None
                else line(f"Everyday plan {fmt(e.everyday_plan, 0)}"))
        cards.append(card("Everyday spending", e.everyday_spent, pace_compare, tone="out", key="everyday",
                          chip_=chip(f"by day {e.day}"), visual=None,  # the pace chart beside it is its picture (audit 12, B1)
                          line_=tail, href="#budget-pace"))
    elif e.day:
        before = e.last_month_by_day[-1] if e.last_month_by_day else None
        change = (compare(f"against {previous}", _signed(e.everyday_spent - before), "good" if e.everyday_spent <= before else "bad")
                  if before is not None else compare("of the everyday plan", f"{e.everyday_spent / e.everyday_plan * 100:.0f}%" if e.everyday_plan > 0 else "—"))
        cards.append(card("Everyday spending", e.everyday_spent, change, tone="out", key="everyday", chip_=chip(month),
                          visual=meter(e.everyday_spent, e.everyday_plan), line_=line(f"Everyday plan {fmt(e.everyday_plan, 0)}"),
                          href="#budget-pace"))

    if over:
        total = sum((row["over"] for row in over), ZERO)
        names = len(over)
        parts = [(row["name"], row["over"], "over" if i == 0 else "out") for i, row in enumerate(over[:3])]
        if len(over) > 3:
            parts.append(("Other", sum((row["over"] for row in over[3:]), ZERO), "neutral"))
        act = (line(action=f"Move {fmt(move['amount'], 0)} from {move['name']}", href=move["href"], popup=True) if move
               else line(action="See categories", href="#budget-meters"))
        cards.append(card("Over plan", total, compare("over their plan", f"{names} categor{'y' if names == 1 else 'ies'}", "bad"),
                          tone="over", needs=True, key="over", chip_=chip("Needs you", "over"),
                          visual=segments(parts) or meter(total, total), line_=act, href="#budget-meters"))

    if check is not None and check.planned is not None and check.plan_saves is not None and check.planned_savings_rate is not None:
        rate, target = check.planned_savings_rate, check.target_percent
        scale = max(rate, target, Decimal(1)) * Decimal("1.4")
        if raise_offer:
            tail = line(f"Income up {fmt(raise_offer['raise'], 0)}", "Raise the plan", f"/budget/raise?month={month}", popup=True)
        elif check.over_by:
            tail = line(f"Plan {fmt(check.over_by, 0)} less to keep {fmt(check.to_save, 0)} a month")
        elif check.unassigned is not None and check.unassigned > 0:
            tail = line(f"{fmt(check.unassigned, 0)} of the income is not yet given a job", "Give it a job", f"/budget/fill?month={month}")
        else:
            tail = line(f"{fmt(check.to_save, 0)} a month to save")
        good = not check.over_by
        cards.append(card("Plan leaves to save", check.plan_saves,
                          compare(f"of income, target {target.normalize():f}%", f"{rate:.0f}%", "good" if good else "bad"),
                          tone="in", key="saves", chip_=chip("Good", "good") if good else chip("Watch"),
                          visual=meter(rate, scale, target, f"{target.normalize():f}%"), line_=tail,
                          href="/settings?section=financial-health"))
    return row(cards)


def budget_period(spent: Decimal, planned: Decimal, months: list[tuple[str, Decimal, bool]], period_label: str,
                  funded_elsewhere: bool = False) -> list[dict]:
    """A longer period (YTD, All time, Custom): what was spent of the plan, and how many finished months ended
    within it. ``months`` is (yyyy-mm, left in plan, finished) for each month with a plan; the running one is hatched."""
    if not planned or planned <= 0:
        return []
    left = planned - spent
    ended = [value for _, value, finished in months if finished]
    within = sum(1 for value in ended if value >= 0)
    cards = [card("From monthly plan" if funded_elsewhere else "Spent", spent, compare(f"of the {fmt(planned, 0)} plan", f"{spent / planned * 100:.0f}%",
                                          "good" if spent <= planned else "bad"),
                  tone="out", key="spent", chip_=chip(period_label), visual=meter(spent, planned),
                  line_=line(f"Planned {fmt(planned, 0)}"), href="#budget-meters"),
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
def cash_plan(f, *, day: date, before: list, late: list, late_total: Decimal, free_then: Decimal | None, then: str, past_free: list[Decimal],
              position, monthly_spending: Decimal | None, has_income: bool) -> list[dict]:
    """Safe to spend, Free cash, Due before payday and the lowest point ahead, each against something."""
    parts = dict(f.safe_to_spend_parts)
    until = f.next_income_date
    if f.safe_to_spend < 0:
        safe_compare = compare("more is promised than your free cash", fmt(-f.safe_to_spend, 0), "bad")
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
                  line_=line("On top of your plan"), working=f.safe_to_spend_working)]

    if free_then is not None:
        change = f.free_cash - free_then
        free_compare = compare(f"since {then}", _signed(change), "good" if change >= 0 else "bad")
        free_chip = chip(month_of(day), "good" if change >= 0 else "bad", "up" if change > 0 else "down" if change < 0 else None)
    else:
        free_compare, free_chip = compare("Your first month: nothing to compare yet"), chip(month_of(day))
    held = (position.kept_apart or ZERO) + (position.reserves or ZERO) + position.bills_due
    cards.append(card(figure_label("free_cash"), f.free_cash, free_compare, tone="hold", key="free", chip_=free_chip,
                      visual=spark([*past_free, f.free_cash]),
                      line_=line(f"Cash you own {fmt(position.cash_you_own, 0)}, including {fmt(position.brokerage_cash, 0)} in your brokerage"
                                 if position.brokerage_cash else
                                 f"Cash you own {fmt(position.cash_you_own, 0)}, less {fmt(held, 0)} set aside or due"), href="/"))

    before_total = f.payments_before_income_total  # the same total Safe to spend takes off (7N)
    if late:
        due_compare = compare("already late", fmt(late_total, 0), "bad")
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
        low_compare = (compare("below today", fmt(drop, 0)) if drop > 0 else compare("above today", fmt(-drop, 0), "good"))
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
    return ("+" if value > 0 else "−" if value < 0 else "") + fmt(abs(value), 0)


# ── Overview ───────────────────────────────────────────────────────────────────────────────────────────────
def overview(flow, *, period_chip: str, rates: list[Decimal | None], usual: Decimal | None, invest: Decimal | None,
             invest_before: Decimal | None, before_label: str, money_added: Decimal, forecast, plan: dict | None,
             month: str, savings_href: str, invest_href: str) -> list[dict]:
    """Savings rate against your usual, Investing rate against the period before, Safe to spend against free cash
    (today only) and Left in plan against the plan. ``flow`` is the period's CashFlow, ``rates`` the recent months'
    savings rates for the sparkline, ``plan`` BudgetService.plan_summary for ``month``."""
    cards = []
    rate = flow.savings_rate
    if rate is None or flow.inflows <= 0:
        cards.append(card(figure_label("savings_rate"), None, compare("No money in this period"), tone="in", key="savings",
                          chip_=chip(period_chip), href=savings_href))
    elif flow.rate_says_nothing:  # honest numbers (A01): a rate like −1,177% says nothing, the sentence does
        cards.append(card(figure_label("savings_rate"), None,
                          compare(f"{fmt(-flow.net, 0)} more went out than the {fmt(flow.inflows, 0)} that came in"),
                          tone="over", key="savings", chip_=chip(period_chip, "bad"), href=savings_href,
                          line_=line(f"Money out {fmt(flow.outflows, 0)}")))
    elif flow.net < 0:
        cards.append(card("Spent over money in", -flow.net,
                          compare(f"{fmt(-flow.net, 0)} more went out than the {fmt(flow.inflows, 0)} that came in"),
                          tone="over", key="savings", chip_=chip(period_chip, "bad"), href=savings_href,
                          line_=line(f"Money out {fmt(flow.outflows, 0)}")))
    else:
        if usual is not None:
            gap = rate - usual
            savings_compare = compare(f"on your usual {usual:.1f}%", f"{signed_pct(gap)} points", "good" if gap >= 0 else "bad")
            arrow = "up" if gap > 0 else "down" if gap < 0 else None
            savings_chip = chip(period_chip, "good" if gap >= 0 else "bad", arrow)
        else:
            savings_compare, savings_chip = compare("Your first month: nothing to compare yet"), chip(period_chip)
        cards.append(card(figure_label("savings_rate"), rate, savings_compare, tone="in", key="savings", kind="rate",
                          chip_=savings_chip, visual=spark(rates), href=savings_href, working=flow.savings_rate_working,
                          line_=line(f"{fmt(flow.net, 0)} kept of {fmt(flow.inflows, 0)} money in")))

    cards.append(_investing(flow, invest, invest_before, before_label, money_added, period_chip, invest_href))

    if forecast is not None:
        f, until = forecast, forecast.next_income_date
        promised = max(f.free_cash - f.safe_to_spend, ZERO)
        safe_compare = (compare("of your free cash", f"{f.safe_to_spend / f.free_cash * 100:.0f}%", "hold") if f.free_cash > 0 and f.safe_to_spend >= 0
                        else compare("more is promised than your free cash", fmt(-f.safe_to_spend, 0), "bad") if f.safe_to_spend < 0
                        else compare("No free cash today"))
        cards.append(card(figure_label("safe_to_spend"), f.safe_to_spend, safe_compare, tone="hold" if f.safe_to_spend >= 0 else "over",
                          key="safe", chip_=chip(f"until {until}" if until else "3 months"),
                          visual=segments([("Safe", max(f.safe_to_spend, ZERO), "hold"), ("Promised", promised, "out")]),
                          line_=line("On top of your plan", "How it is worked out", "/plan#safe-section"), href="/plan#safe-section"))

    if plan is not None:
        planned, left = plan["planned"], plan["left"]
        used = planned - left
        plan_compare = (compare("over the plan", fmt(-left, 0), "bad") if left < 0
                        else compare(f"of the {fmt(planned, 0)} plan used", f"{used / planned * 100:.0f}%" if planned > 0 else "—"))
        cards.append(card(figure_label("left_in_plan"), left if left >= 0 else -left, plan_compare,
                          tone="over" if left < 0 else "out", needs=left < 0, key="plan",
                          chip_=chip("Over plan", "over") if left < 0 else chip(month), visual=meter(used, planned),
                          line_=line(f"Spent {fmt(used, 0)} of {fmt(planned, 0)} planned"), href=f"/budget?month={month}"))
    else:
        cards.append(card(figure_label("left_in_plan"), None, compare(f"No plan for {month} yet"), tone="out",
                          key="plan", chip_=chip(month), line_=line(action=f"Set a plan for {month}", href=f"/budget?month={month}"),
                          href=f"/budget?month={month}"))
    return row(cards)


def _investing(flow, invest, invest_before, before_label: str, money_added: Decimal, period_chip: str, href: str) -> dict:
    """Investing rate against the period before; zero is "—" with the last value and what would move it (A08.5)."""
    label_ = figure_label("investing_rate")
    if invest is not None and invest == 0:
        last = f"{before_label}: {invest_before:.1f}%" if invest_before is not None else "nothing before either"
        return card(label_, None, compare(f"Nothing invested yet this period. {last}"), tone="in", key="investing",
                    chip_=chip(period_chip), line_=line(action="Plan to invest", href="/investments/planner"), href=href)
    if invest is not None and invest_before is not None:
        gap = invest - invest_before
        comparison = compare(f"on {before_label} ({invest_before:.1f}%)", f"{signed_pct(gap)} points", "good" if gap >= 0 else "bad")
    elif invest is not None:
        comparison = compare(f"Nothing was kept in {before_label} to compare with")
    else:
        comparison = compare("Nothing kept this period, so nothing to invest from")
    added = max(money_added, ZERO)
    return card(label_, invest, comparison, tone="in", key="investing", kind="rate", chip_=chip(period_chip),
                visual=meter(min(added, flow.net), flow.net) if flow.net > 0 else None,
                line_=line(f"{fmt(added, 0)} moved into investments, a share of the {fmt(flow.net, 0)} you kept" if flow.net > 0 else f"{fmt(added, 0)} moved into investments"), href=href)


# ── Loans ──────────────────────────────────────────────────────────────────────────────────────────────────
_BAND_CHIP = {"good": ("Good", "good"), "watch": ("Watch", "quiet"), "alert": ("Needs you", "over")}


def debt(h, *, limits: dict, band, as_of: str) -> list[dict]:
    """Cash planning › Loans (3Q1): each debt ratio against your limit, the limit a tick on its meter.

    ``h`` is FinancialHealth.at(); ``limits`` its Good boundaries; ``band(key, value)`` its Good/Watch/Needs you."""
    owed, worth, cash = h.debt_to_net_worth.part, h.debt_to_net_worth.whole, h.debt_to_cash.whole
    pay, income = h.loan_payments_to_income.part, h.loan_payments_to_income.whole
    rows = (
        (h.debt_to_net_worth, f"{fmt(owed, 0)} owed against {fmt(worth or ZERO, 0)} net worth",
         "You owe more than you own" if owed and (worth or 0) <= 0 else "Nothing owed", "/"),
        (h.debt_to_cash, f"{fmt(owed, 0)} owed against {fmt(cash or ZERO, 0)} cash you own",
         "No cash to set it against" if owed else "Nothing owed", "/"),
        (h.loan_payments_to_income, f"{fmt(pay, 0)} a month of {fmt(income or ZERO, 0)} income",
         "Set your income categories to measure it" if pay and not income else "No loan payments left", "#loans-list"),
    )
    cards = []
    underwater = bool(owed) and (worth or 0) <= 0  # owing more than you own is said, not divided, and needs you
    for ratio, said, missing, href in rows:
        pct, limit = ratio.percent, limits.get(ratio.key)
        state = band(ratio.key, pct) if pct is not None else ("alert" if underwater and ratio is h.debt_to_net_worth else None)
        text, tone = _BAND_CHIP.get(state, (as_of, "quiet"))
        cards.append(card(figure_label(ratio.key), pct, compare(said if pct is not None and ratio.part else missing),
                          tone="over" if state == "alert" else "out", kind="rate", chip_=chip(text, tone),
                          visual=meter(pct, max(Decimal(100), pct, limit or ZERO), limit,
                                       f"limit {limit:.0f}%" if limit is not None else "") if pct is not None else None,
                          line_=line(f"Your limit {limit:.0f}%" if limit is not None else "No limit set"),
                          href=href, needs=state == "alert", key=ratio.key))
    return row(cards)


# ── Spending ───────────────────────────────────────────────────────────────────────────────────────────────
def spending(stats: list[dict]) -> list[dict]:
    """Spending's summary (3Q1) as KPI cards, from the figures the route already worked out (``_expense_stats``).

    Money out keeps its two comparisons: the period before in the comparison slot, the usual month as its line.
    Largest payment is left out when it is the biggest category's whole amount: one figure, one place (A16)."""
    by = {s["key"]: s for s in stats}
    cards = []
    out = by.get("out")
    if out:
        first, *rest = out.get("compare") or [{"label": "", "text": "", "tone": "flat"}]
        tone = {"up": "bad", "down": "good"}.get(first["tone"], "plain")
        usual = rest[0] if rest else None
        if usual and usual["text"] == first["text"]:   # BV-12D: one month of history, so the usual month is that month
            usual = None
        cards.append(card(out["label"], out["value"], compare(first["label"], first["text"], tone), tone="out",
                          visual=spark(out["spark_values"]) if out.get("spark_values") else None,
                          line_=line(f"{usual['label']} · {usual['text']}") if usual else None,
                          href=out.get("href", ""), key="out"))
    pay = by.get("payments")
    if pay and pay["value"] is not None:
        cards.append(card(pay["label"], pay["value"], compare(pay["sub"]), tone="out", href=pay.get("href", ""), key="payments"))
    top, big = by.get("top"), by.get("payment")
    if top and top["value"] is not None:
        cards.append(card(top["label"], top["value"], compare(top["sub"]), tone="out",
                          visual=meter(Decimal(str(top["meter"]["width"])), Decimal(100)) if top.get("meter") else None,
                          href=top.get("href", ""), key="top"))
    if big and big["value"] is not None and not (top and top["value"] == big["value"] and top.get("single")):
        cards.append(card(big["label"], big["value"], compare(big["sub"]), tone="out",
                          visual=meter(Decimal(str(big["meter"]["width"])), Decimal(100)) if big.get("meter") else None,
                          href=big.get("href", ""), key="payment"))
    return row(cards)


# ── Recurring ──────────────────────────────────────────────────────────────────────────────────────────────
def recurring(*, monthly_out: Decimal, fixed, limit: Decimal | None, band: str | None, subscriptions_per_year: Decimal,
              due_count: int, due_total: Decimal) -> list[dict]:
    """Cash planning › Recurring (3Q1): what repeats a month, its share of income against your limit, subscriptions
    and what is due now. ``fixed`` is FinancialHealth's fixed_costs_to_income ratio."""
    cards = [card("Bills and subscriptions", monthly_out, compare(f"{fmt(monthly_out * 12, 0)} a year"), tone="out",
                  line_=line("a month"), href="#recurring-totals", key="bills")]
    pct = fixed.percent
    text, tone = _BAND_CHIP.get(band, ("", "quiet"))
    cards.append(card(figure_label(fixed.key), pct,
                      compare(f"{fmt(fixed.part, 0)} a month of {fmt(fixed.whole or ZERO, 0)} income" if pct is not None
                              else "Set your income categories to measure it"),
                      tone="over" if band == "alert" else "out", kind="rate", chip_=chip(text, tone) if text else None,
                      visual=meter(pct, max(Decimal(100), pct, limit or ZERO), limit,
                                   f"limit {limit:.0f}%" if limit is not None else "") if pct is not None else None,
                      line_=line(f"Your limit {limit:.0f}%" if limit is not None else "No limit set"),
                      needs=band == "alert", key=fixed.key))
    if subscriptions_per_year:
        cards.append(card("Subscriptions", subscriptions_per_year / 12, compare(f"{fmt(subscriptions_per_year, 0)} a year"),
                          tone="out", line_=line("a month"), key="subscriptions"))
    if due_count:
        cards.append(card("Due now", due_total, compare(f"in {due_count} payment{'s' if due_count != 1 else ''}"),
                          tone="over", chip_=chip("Needs you", "over"), needs=True, href="#recurring-list", key="due"))
    return row(cards)


# ── Currencies ─────────────────────────────────────────────────────────────────────────────────────────────
def currencies(totals: dict, *, start: str, end: str) -> list[dict]:
    """Investments › Currencies (3Q2): foreign money and what the exchange rate did to it, every card with its
    reference; Spread paid only when there was any. ``totals`` is FxPositions.totals."""
    labels = {"unrealized": figure_label("unrealized_fx_gain"), "realized": figure_label("realized_fx_gain"),
              "spread": figure_label("spread_paid")}
    complete = totals["complete"]
    held = totals["value"] + totals["investments"] if complete else None
    cards = [card("Foreign money", held,
                  compare(f"Cash {fmt(totals['value'], 0)} · investments {fmt(totals['investments'], 0)}"
                          if complete and totals["investments"] else
                          f"as of {end}" if complete else "Some values are unavailable"),
                  tone="hold", key="held")]  # cash and investments are both money you hold (Azure): the words split it
    gain = totals["unrealized"] if complete else None
    cards.append(card(labels["unrealized"], gain,
                      compare(f"on {fmt(totals['cost'], 0)} it cost" if totals.get("cost") else "against what it cost"),
                      tone="in" if gain is None or gain >= 0 else "out", signed=True,
                      line_=line("Not locked in until you spend or convert."), key="unrealized"))
    cards.append(card(labels["realized"], totals["realized"], compare(f"{start} to {end}"),
                      tone="in" if totals["realized"] >= 0 else "out", signed=True, key="realized"))
    if totals["spread"]:
        cards.append(card(labels["spread"], totals["spread"], compare(f"{start} to {end}"), tone="out",
                          line_=line("Beyond the market rate, on conversions."), key="spread"))
    return row(cards)
