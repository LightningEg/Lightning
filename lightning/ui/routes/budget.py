from __future__ import annotations

from datetime import timedelta
from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from math import pi
import json
import uuid

from fastapi import APIRouter, Request, Response

from lightning.core.dates import fmt_date, month_of, parse_month, today
from lightning.core.errors import LightningError, ValidationError
from lightning.categories.domain import Movement, Scope
from lightning.core.money import ZERO, quantize, to_decimal

from lightning.budgeting.domain import INCOME_FROM_RECURRING
from lightning.planning.domain import KIND_LABELS, PaymentStatus
from lightning.planning.health import PlanCheck

from .. import charts, keynotes, kpis, status as page_status
from ..web import container, redirect, render
from ..periods import parse_period

router = APIRouter(prefix="/budget")
TRACK_SUGGESTION_PERCENT = Decimal(20)


def _category_setting_ids(c, key: str) -> set[int]:
    values = json.loads(c.settings.get(key) or "[]")
    by_code = {category.code: category.id for category in c.categories.tree()}
    result = set()
    for value in values:
        try:
            result.add(int(value))
        except (ValueError, TypeError):
            if str(value) in by_code:
                result.add(by_code[str(value)])
    return result


def _save_category_setting(c, key: str, ids: set[int] | list[int]) -> None:
    values = sorted({c.categories.get(item).code for item in ids}) if getattr(c, "is_journal", False) else sorted(set(ids))
    c.settings.set(key, json.dumps(values))


def _month(request: Request) -> str:
    month = request.query_params.get("month") or month_of(today())
    parse_month(month)
    return month


def _neighbours(month: str) -> tuple[str, str]:
    first, last = parse_month(month)
    previous = month_of(first - timedelta(days=1))
    try:
        following = month_of(last + timedelta(days=1))
    except OverflowError:
        following = month
    return previous, following


def _page(request: Request, month: str, values: dict | None = None, error: str = "", status_code: int = 200):
    c = container(request)
    earliest = c.budgets.first_owned_spending_date()
    try:
        period = parse_period(request.query_params, today(), earliest)
    except ValidationError as exc:
        period = parse_period({"period": "month", "month": month}, today())
        error = error or exc.message  # say why the month is shown instead of the range asked for
    month = period.end.strftime("%Y-%m")
    view = c.budgets.month_view(month)
    cursor = period.start.replace(day=1)
    month_views = []
    while cursor <= period.end:
        key = cursor.strftime("%Y-%m")
        # A longer period includes only months with a saved plan, matching its spending window.
        if period.key == "month" or c.budgets.has_plan(key):
            month_views.append((key, c.budgets.month_view(key)))
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    period_base = ZERO
    period_opening = ZERO
    period_carryover = ZERO
    if month_views:
        period_opening = month_views[0][1].available - month_views[0][1].budget
        period_carryover = period_opening
        if period.key == "custom":
            first_month = parse_month(month_views[0][0])
            overlap_start, overlap_end = max(first_month[0], period.start), min(first_month[1], period.end)
            opening_factor = Decimal((overlap_end-overlap_start).days+1) / Decimal((first_month[1]-first_month[0]).days+1)
            period_opening *= opening_factor
            period_carryover *= opening_factor
    period_budgeted = period_base + period_opening
    group_totals = {}
    for _, month_view in month_views:
        m_first, m_last = parse_month(month_view.month)
        overlap_start, overlap_end = max(m_first, period.start), min(m_last, period.end)
        # Saved monthly limits stay whole in month, YTD and all-time views; only custom dates prorate them.
        factor = (Decimal(1) if period.key != "custom" else
                  Decimal((overlap_end-overlap_start).days+1) / Decimal((m_last-m_first).days+1)
                  if overlap_end >= overlap_start else ZERO)
        period_base += month_view.budget * factor
        for section in month_view.sections:
            for group in section.groups:
                row = group_totals.setdefault(group.category_id, {"name": group.name, "section": section.name,
                    "budgeted": ZERO, "carryover": ZERO, "spent": ZERO, "left": ZERO})
                row["budgeted"] += (group.budget or ZERO) * factor
                if month_views and month_view.month == month_views[0][0]:
                    row["budgeted"] += group.opening_carryover * factor
                    row["carryover"] += group.opening_carryover * factor
    for row in group_totals.values():
        row["left"] = row["budgeted"] - row["spent"]
    if period.key == "month":
        for section in view.sections:
            for group in section.groups:
                row = group_totals.get(group.category_id)
                if row:
                    row["budgeted"] = group.available or ZERO
                    row["carryover"] = group.opening_carryover
                    row["left"] = quantize(row["budgeted"], 0) - quantize(row["spent"], 0)
        # Keep the headline aligned with the L1 group rows, including carryover.
        period_budgeted = sum((row["budgeted"] for row in group_totals.values()), ZERO)
    prev_month, next_month = _neighbours(month)
    has_plan = c.budgets.has_plan(month)
    suggestions = c.budgets.suggested_plan(month) if not has_plan else {}
    suggestions_view = {category_id: (c.categories.display_name(category_id), amount)
                        for category_id, amount in suggestions.items()}
    suggestion_groups: dict[str, list] = {}  # L1 as a header, each category under it by its own name
    for category_id, (name, amount) in suggestions_view.items():
        parts = name.split(" › ")
        suggestion_groups.setdefault(parts[0], []).append((category_id, " › ".join(parts[1:]) or parts[0], amount))
    tracked = {line.category_id for section in view.sections for line in section.lines
               if line.direct is not None or line.average_months or line.income_percent is not None}
    try:
        tracked |= _category_setting_ids(c, "budget_tracked_categories")
    except (ValueError, TypeError):
        pass
    tracked = {int(item) for item in tracked}
    first, _ = parse_month(month)
    completed_last = first - timedelta(days=1)
    completed_first = completed_last.replace(day=1)
    for _ in range(5):
        completed_first = (completed_first - timedelta(days=1)).replace(day=1)
    category_amounts = c.budgets._owned_spending(completed_first, completed_last)
    six_months = []
    month_end = completed_last
    for _ in range(6):
        month_first, _ = parse_month(month_of(month_end))
        six_months.append(c.budgets._owned_spending(month_first, month_end))
        month_end = month_first - timedelta(days=1)
    categories = c.categories.tree(Movement.OUTFLOW)
    by_id = {category.id: category for category in categories}
    children: dict[int, list[int]] = {}
    for category in categories:
        if category.parent_id:
            children.setdefault(category.parent_id, []).append(category.id)
    def category_tree_ids(category_id):
        descendants = {category_id}
        pending = [category_id]
        while pending:
            kids = children.get(pending.pop(), [])
            descendants.update(kids)
            pending.extend(kids)
        return descendants

    averages = {}; averages6 = {}; average_observations = {}; average_observations6 = {}
    for section in view.sections:
        for line in section.lines:
            descendants = category_tree_ids(line.category_id)
            observed3 = [sum((amounts.get(category_id, ZERO) for category_id in descendants), ZERO)
                         for amounts in six_months[:3] if any(category_id in amounts for category_id in descendants)]
            observed6 = [sum((amounts.get(category_id, ZERO) for category_id in descendants), ZERO)
                         for amounts in six_months if any(category_id in amounts for category_id in descendants)]
            observed = observed3
            averages[line.category_id] = (sum(observed, ZERO) / len(observed)).quantize(Decimal("0.01")) if observed else None
            averages6[line.category_id] = (sum(observed6, ZERO) / len(observed6)).quantize(Decimal("0.01")) if observed6 else None
            average_observations[line.category_id] = len(observed3)
            average_observations6[line.category_id] = len(observed6)
    by_group = {}
    for section in view.sections:
        for group in section.groups:
            by_group[group.category_id] = sorted(category_tree_ids(group.category_id) - {group.category_id})
    background_counts, background_totals = {}, {}
    for group_id, child_ids in by_group.items():
        untracked_lines = [line for section in view.sections for line in section.lines
                           if line.category_id in child_ids and line.category_id not in tracked]
        background_counts[group_id] = len(untracked_lines)
        background_totals[group_id] = sum((averages.get(line.category_id) or ZERO for line in untracked_lines), ZERO)
    income_basis = c.budgets.budgeting_income(month)
    # A default, not a setting (owner, 2026-10-06): suggest tracking a category that averages a fifth of income.
    threshold, fixed_threshold = TRACK_SUGGESTION_PERCENT, ZERO
    try:
        raw_exclusions = c.settings.get("budget_one_off_exclusions") or "[]"
        exclusions = _category_setting_ids(c, "budget_one_off_exclusions") if raw_exclusions.strip().startswith("[") else set()
    except (ValueError, TypeError):
        exclusions = set()
    background_counts, background_totals = {}, {}
    for group_id, child_ids in by_group.items():
        background = [line for section in view.sections for line in section.lines
                      if line.category_id in child_ids and line.category_id not in tracked and not line.covered
                      and not children.get(line.category_id) and line.category_id not in exclusions]
        background_counts[group_id] = len(background)
        background_totals[group_id] = sum((averages.get(line.category_id) or ZERO for line in background), ZERO)
    suppressed = json.loads(c.settings.get("budget_suppressed_categories") or "{}")
    if isinstance(suppressed, list):
        suppressed = {str(category_id): "never" for category_id in suppressed}
    else:
        for category in by_id.values():
            if str(category.id) not in suppressed and category.code in suppressed:
                suppressed[str(category.id)] = suppressed[category.code]
    tracking_suggestions = []
    for line in (line for section in view.sections for line in section.lines
                 if line.depth > 1 and line.category_id not in tracked):
        category = by_id.get(line.category_id)
        dismissal = suppressed.get(str(line.category_id))
        if not category or dismissal in {"never", month}:
            continue
        descendants = category_tree_ids(category.id)
        spent_six = sum((amounts.get(category_id, ZERO) for amounts in six_months
                         for category_id in descendants), ZERO)
        if category.id in exclusions:
            continue
        observed_count = sum(1 for amounts in six_months if any(cid in amounts for cid in descendants))
        monthly_average = (spent_six / observed_count).quantize(Decimal("0.01")) if observed_count else None
        share = (monthly_average / income_basis * 100) if income_basis and monthly_average is not None else ZERO
        crossed_percent = threshold is not None and income_basis is not None and monthly_average is not None and share >= threshold
        crossed_fixed = fixed_threshold > ZERO and monthly_average is not None and monthly_average >= fixed_threshold
        if (crossed_percent or crossed_fixed) and spent_six > ZERO:
            parent = category
            while parent.depth > 1 and parent.parent_id and by_id.get(parent.parent_id):
                parent = by_id[parent.parent_id]
            group_id = parent.id
            tracking_suggestions.append({"id": category.id, "name": line.name, "share": share,
                                         "group_id": group_id, "spent": spent_six,
                                         "reason": (f"{share:.1f}% of average monthly income" if crossed_percent else
                                                    f"Average {monthly_average:,.0f} EGP crossed fixed threshold")})

    # Background estimates are monthly expectations for untracked leaf
    # categories. Parent direct plans already cap these expenses, so children
    # under those caps are not added a second time.
    for _, month_view in month_views:
        m_first, m_last = parse_month(month_view.month)
        overlap_start, overlap_end = max(m_first, period.start), min(m_last, period.end)
        # Saved monthly limits stay whole in month, YTD and all-time views; only custom dates prorate them.
        factor = (Decimal(1) if period.key != "custom" else
                  Decimal((overlap_end-overlap_start).days+1) / Decimal((m_last-m_first).days+1)
                  if overlap_end >= overlap_start else ZERO)
        for section in month_view.sections:
            for line in section.lines:
                if (line.depth <= 1 or line.category_id in tracked or line.covered or children.get(line.category_id)
                        or line.category_id in exclusions):
                    continue
                estimate = c.budgets._rolling_average(line.category_id, month_view.month, 3, children, {})
                if estimate is None:
                    continue
                parent = by_id.get(line.category_id)
                while parent and parent.depth > 1 and parent.parent_id:
                    parent = by_id.get(parent.parent_id)
                group_id = parent.id if parent else None
                if group_id in group_totals:
                    group_totals[group_id]["budgeted"] += estimate * factor
                    period_base += estimate * factor
    period_budgeted = period_base + period_opening
    one_offs = c.budgets.one_off_ids()
    # Planned and Spent cover the same months: a long period (YTD, All time, custom) counts spending
    # from the first month that has a plan, because months before it have nothing planned.
    plan_months = [key for key, _ in month_views if c.budgets.has_plan(key)]
    spending_start = period.start
    if period.key != "month" and plan_months:
        spending_start = max(period.start, parse_month(plan_months[0])[0])
    period_spending = {cid: v for cid, v in c.budgets._owned_spending(spending_start, period.end).items()
                       if cid not in one_offs}  # one-off spending stays in cash flow, out of the budget
    period_actual = sum(period_spending.values(), ZERO)
    category_periods = {}
    for _, month_view in month_views:
        m_first, m_last = parse_month(month_view.month)
        overlap_start, overlap_end = max(m_first, period.start), min(m_last, period.end)
        # Saved monthly limits stay whole in month, YTD and all-time views; only custom dates prorate them.
        factor = (Decimal(1) if period.key != "custom" else
                  Decimal((overlap_end-overlap_start).days+1) / Decimal((m_last-m_first).days+1)
                  if overlap_end >= overlap_start else ZERO)
        for section in month_view.sections:
            for line in section.lines:
                if line.depth <= 1:
                    continue
                row = category_periods.setdefault(line.category_id, {
                    "base_budget": ZERO, "carryover": ZERO, "current_budget": ZERO,
                    "budgeted": ZERO, "spent": ZERO,
                })
                row["base_budget"] += (line.budget or ZERO) * factor
                if month_views and month_view.month == month_views[0][0]:
                    row["carryover"] += line.opening_carryover * factor
    for category_id, row in category_periods.items():
        row["current_budget"] = row["base_budget"] + row["carryover"]
        row["budgeted"] = row["current_budget"]
        row["spent"] = sum((period_spending.get(cid, ZERO) for cid in category_tree_ids(category_id)), ZERO)
        row["left"] = quantize(row["current_budget"], 0) - quantize(row["spent"], 0)  # as the figures beside it read
    for group_id, child_ids in by_group.items():
        row = group_totals.get(group_id)
        if row:
            row["spent"] = sum((period_spending.get(cid, ZERO) for cid in child_ids), ZERO)
            row["left"] = quantize(row["budgeted"], 0) - quantize(row["spent"], 0)
    period_income = ZERO
    for key, _ in month_views:
        basis = c.budgets.budgeting_income(key) or ZERO
        m_first, m_last = parse_month(key)
        overlap_start, overlap_end = max(m_first, period.start), min(m_last, period.end)
        # Saved monthly limits stay whole in month, YTD and all-time views; only custom dates prorate them.
        factor = (Decimal(1) if period.key != "custom" else
                  Decimal((overlap_end-overlap_start).days+1) / Decimal((m_last-m_first).days+1)
                  if overlap_end >= overlap_start else ZERO)
        period_income += basis * factor
    # One savings target for every screen (Financial health › Savings rate limit). A month is checked
    # with its goals below, in the key notes; a longer period against the target alone.
    check = c.health.plan_check(month) if period.key == "month" else None
    period_check = PlanCheck(period.label, period_income, period_base, c.health.limit_values()["savings_rate"], ZERO)
    ceiling_warning = ("" if period_income <= ZERO or check is not None else
                       "Planned amounts exceed average monthly income" if period_base > period_income else
                       f"This plan saves less than your {period_check.target_percent.normalize():f}% savings target: "
                       f"plan {keynotes.fmt(period_check.over_by)} less" if period_check.over_by else "")
    period_left = period_budgeted-period_actual
    # Feedback ticket 93: the System group counts as Personal spending, so its section read "Personal" under
    # "System Categories". Say what is in it instead.
    lines = {line.category_id: line for _, view in month_views for section in view.sections
             for line in [*section.groups, *section.lines]}
    system_id = next((cid for cid, line in lines.items() if line.code == "EXP.SYSTEM"), None)
    if system_id in group_totals:
        names = [lines[cid].name for cid in by_group.get(system_id, []) if cid in lines
                 and (period_spending.get(cid) or category_periods.get(cid, {}).get("budgeted"))]
        group_totals[system_id]["note"] = ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")
    group_rows = sorted(group_totals.items(),
                        key=lambda item: (item[1]["left"] >= ZERO, -item[1]["spent"], item[1]["name"].casefold()))
    unplanned_spending = period_actual - sum((row["spent"] for row in group_totals.values()), ZERO)
    plan_outside_groups = period_budgeted - sum((row["budgeted"] for row in group_totals.values()), ZERO)
    grouped_category_ids = {category_id for child_ids in by_group.values() for category_id in child_ids}
    outside_spending_rows = sorted(({"id": category_id, "name": c.categories.display_name(category_id),
                                    "amount": amount}
                                   for category_id, amount in period_spending.items()
                                   if category_id not in grouped_category_ids and amount != ZERO),
                                  key=lambda row: -abs(row["amount"]))
    bulk_undo = None
    token = str(request.query_params.get("undo", ""))
    if token:
        try:
            snapshot = json.loads(c.settings.get("budget_bulk_undo") or "{}")
            if snapshot.get("token") == token and snapshot.get("month") == month:
                bulk_undo = token
        except (ValueError, TypeError):
            pass
    # Spent of plan for each planned category in the month, over plan first (guide 08 · budget meters).
    meter_lines = []
    for section in view.sections:
        for line in section.lines:
            if line.depth > 1 and line.available is not None and (line.available or line.planned_actual):
                meter_lines.append({"label": line.name, "used": line.planned_actual, "total": line.available, "category_id": line.category_id,
                                    "m": charts.meter(line.planned_actual, line.available),
                                    "b": charts.bullet(line.planned_actual, line.available),
                                    "href": f"/transactions?category_id={line.category_id}&date_from={month}-01"})
    meter_lines.sort(key=lambda r: (not r["m"]["over"], -(r["m"].get("share") or 0)))
    month_first, month_last = parse_month(month)
    days_left = (month_last - today()).days + 1 if month_first <= today() <= month_last else 0
    # The same Left in plan as the headline and the Overview (background estimates counted in).
    month_left = c.budgets.plan_summary(month)["left"] if c.budgets.has_plan(month) else ZERO
    notes = keynotes.budget_left(month_left, days_left,
                                 [r["label"] for r in meter_lines if r["m"]["over"]], "#budget-meters") if c.budgets.has_plan(month) else []
    if check is not None and check.planned is not None:
        notes = keynotes.plan_check(check) + notes
    left_note = keynotes.per_day(month_left, days_left) if c.budgets.has_plan(month) else ""
    # KPI cards (guideline 3.32 A08): every figure against something, two to four in the row. The figures come
    # from the forecaster's EverydayBudget, the same Budget until payday Cash planning shows.
    raise_offer = c.health.raise_offer(month) if period.key == "month" else None
    kpi_cards, pace, plan_bills, everyday = [], None, [], None
    if period.key == "month" and has_plan:
        everyday = c.forecaster.everyday(month, today())
        over = sorted(({"name": r["label"], "over": r["b"]["over_by"], "category_id": r["category_id"]}
                       for r in meter_lines if r["b"]["is_over"]), key=lambda r: -r["over"])
        kpi_cards = kpis.budget_month(everyday, over=over, check=check, raise_offer=raise_offer,
                                      move=_cover_from(c, month, over[0], everyday.room) if over else None, month=month)
        if everyday.day and everyday.everyday_plan > 0:
            pace = charts.pace(everyday.by_day, everyday.everyday_plan, everyday.days_in_month, everyday.last_month_by_day)
        plan_bills = _plan_bills(c, everyday)
    elif period.key != "month":
        kpi_cards = kpis.budget_period(period_actual, period_budgeted,
                                       [(key, c.budgets.plan_summary(key)["left"], parse_month(key)[1] < today())
                                        for key, _ in month_views if c.budgets.has_plan(key)],
                                       period.label)
    # Answer first (guideline 3.33, A09): Left in plan is the page's Lead with the pace chart beside it; what is over
    # plan is a Needs you row under it; Everyday spending and Plan leaves to save stay as the KPI row.
    lead, pace_card, needs = None, None, []
    if period.key == "month" and has_plan:
        by_key = {k["key"]: k for k in kpi_cards}
        lead, pace_card = by_key.get("left"), by_key.get("everyday")
        kpi_cards = kpis.row([by_key.get("everyday"), by_key.get("saves")])
        rows = {r["category_id"]: r for r in meter_lines}
        for i, o in enumerate(over):
            move = _cover_from(c, month, o, everyday.room) if i == 0 else None
            r = rows[o["category_id"]]
            needs.append({"label": f"{o['name']} is {keynotes.fmt(o['over'])} over its plan",
                          "detail": f"{keynotes.fmt(r['used'])} spent of {keynotes.fmt(r['total'])}",
                          "href": move["href"] if move else r["href"], "popup": bool(move),
                          "action": f"Move {keynotes.fmt(move['amount'])} from {move['name']}" if move else "See it"})
        if raise_offer and not by_key.get("saves"):
            needs.append({"label": "Your income went up",
                          "detail": f"Recurring expects {keynotes.fmt(raise_offer['raise'])} more than your average.",
                          "href": f"/budget/raise?month={month}", "popup": True, "action": "Choose"})
    status = page_status.budget(everyday, has_plan, period.key, period_actual, period_budgeted)
    phone_plan: dict = {}
    if getattr(request.state, "phone", False):  # the phone's Budget (templates/phone/budget.html); the PC reads none of this
        phone_cats = _phone_categories(view, tracked, category_periods, by_group, period)
        phone_plan = {"ring": _plan_ring(period_budgeted, period_actual, period_left) if has_plan else None,
                      "cats": phone_cats,
                      "over": _phone_over(phone_cats, month, days_left if period.key == "month" else 0,
                                          c, everyday),
                      "edit_href": f"/budget?month={month}&open_group=all#groups-heading",
                      "notes": [n for n in notes if n.get("label") not in OVER_NOTE_LABELS]}
    return render(request, "budget.html", notes=notes, phone_plan=phone_plan, kpi_cards=kpi_cards, pace=pace, plan_bills=plan_bills, everyday=everyday,
                  lead=lead, pace_card=pace_card, needs=needs, status=status,
                  raise_in_card=bool(needs and needs[-1]["href"].startswith("/budget/raise")) or any(k["key"] == "saves" for k in kpi_cards),
                  raise_offer=raise_offer, meter_lines=meter_lines, left_note=left_note, check=check,
                  plan_bar=charts.plan_bar(period_budgeted, period_actual),
                  status_code=status_code, view=view, month=month,
                  prev_month=prev_month, next_month=next_month, values=values or {}, error=error,
                  has_plan=has_plan, suggestions=suggestions_view, suggestion_groups=suggestion_groups,
                  tracked=tracked, averages=averages,
                  averages6=averages6, average_observations=average_observations,
                  average_observations6=average_observations6,
                  tracking_suggestions=tracking_suggestions, suggestion_threshold=threshold,
                  carryover=c.settings.get("budget_carryover_global") == "1",
                  overall_ceiling=c.settings.get("budget_overall_ceiling"), this_month=month_of(today()),
                  personal_group=next((cat.id for cat in c.categories.tree(Movement.OUTFLOW)
                                       if cat.depth == 1 and cat.scope == Scope.PERSONAL), None),
                  free_cash=c.reserves.cash_summary(c.reporting.owned_spendable_cash(today()), c.planning.what_you_owe().bills_due)["free_cash"],
                  low_confidence=keynotes.low_confidence_note(c.budgets.plan_summary(month)["low_confidence"]) if period.key == "month" else "",
                  plan_from=fmt_date(spending_start) if spending_start != period.start else "",
                  period=period, period_actual=period_actual, period_budgeted=period_budgeted,
                  period_left=period_left, period_carryover=period_carryover, group_totals=group_totals,
                  group_rows=group_rows,
                  unplanned_spending=unplanned_spending, plan_outside_groups=plan_outside_groups,
                  outside_spending_rows=outside_spending_rows, base=c.reporting.base_currency,
                  by_group=by_group, background_counts=background_counts, background_totals=background_totals,
                  period_income=period_income, ceiling_warning=ceiling_warning,
                  monthly_income_basis=income_basis,
                  category_periods=category_periods,
                  bulk_undo=bulk_undo,
                  effective_month=month, previous_month=_neighbours(month)[0],
                  previous_bridge=c.budgets.month_view(_neighbours(month)[0]))


# The key notes the phone's over-plan row and hero already say (keynotes.budget_left).
OVER_NOTE_LABELS = {"Categories over plan", "Over plan this month"}
RING_RADIUS = 40


def _plan_ring(budgeted: Decimal, spent: Decimal, left: Decimal) -> dict | None:
    """The phone's ring: how much of the plan is spent, whole percent, and the arc for it (a full turn at 100%).
    None when nothing is planned, so there is no share to draw."""
    if budgeted <= ZERO:
        return None
    pct = max(int((spent / budgeted * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)), 0)
    circumference = 2 * pi * RING_RADIUS
    return {"pct": min(pct, 999), "wide": pct >= 100, "over": quantize(left, 0) < 0, "amount": abs(left),
            "arc": round(circumference * min(pct, 100) / 100, 2), "circumference": round(circumference, 2)}


def _phone_categories(view, tracked: set[int], category_periods: dict, by_group: dict, period) -> list[dict]:
    """One row per category that has a limit: over plan first (largest overspend first), then the ones closest to
    their limit. The same figures as the group rows below: what was spent, the limit and what is left."""
    group_of = {category_id: group_id for group_id, ids in by_group.items() for category_id in ids}
    rows, seen = [], set()
    for section in view.sections:
        for line in section.lines:
            cid = line.category_id
            if line.depth <= 1 or cid in seen or cid not in tracked or cid not in category_periods:
                continue
            seen.add(cid)
            figures = category_periods[cid]
            planned, spent, left = figures["current_budget"], figures["spent"], figures["left"]
            if not planned and not spent:
                continue
            share = (spent / planned * 100) if planned > ZERO else Decimal(100 if spent > ZERO else 0)
            rows.append({"category_id": cid, "group_id": group_of.get(cid), "name": line.name, "spent": spent,
                         "planned": planned, "over": left < ZERO, "amount": abs(left), "share": share,
                         "width": round(float(min(max(share, ZERO), Decimal(100))), 1),
                         "href": f"/transactions?category_id={cid}&date_from={period.start_text}&date_to={period.end_text}"})
    rows.sort(key=lambda r: (0, -r["amount"], r["name"].casefold()) if r["over"] else (1, -r["share"], r["name"].casefold()))
    return rows


def _phone_over(rows: list[dict], month: str, days_left: int, c, everyday) -> dict | None:
    """The phone's over-plan row: what is over, by how much, and the one action that fixes the largest: move room
    to it when another category has room (Move room), else type its limit (its group opens at the field)."""
    over = [r for r in rows if r["over"]]
    if not over:
        return None
    total = sum((r["amount"] for r in over), ZERO)
    title = (page_status.sentence("{name} is over plan", name=over[0]["name"]) if len(over) == 1
             else page_status.sentence("{n} categories are over plan", n=len(over)))
    if days_left > 1:
        line = page_status.sentence("{amt} over · {n} days left", amt=keynotes.fmt(total), n=days_left)
    elif days_left == 1:
        line = page_status.sentence("{amt} over · 1 day left", amt=keynotes.fmt(total))
    else:
        line = page_status.sentence("{amt} over", amt=keynotes.fmt(total))
    largest = over[0]
    move = (_cover_from(c, month, {"category_id": largest["category_id"], "over": largest["amount"]}, everyday.room)
            if everyday is not None else None)
    href = move["href"] if move else (f"/budget?month={month}&open_group={largest['group_id'] or 'all'}"
                                      f"#limit-{largest['category_id']}")
    return {"title": title, "line": line, "count": len(over), "href": href, "popup": bool(move)}


def _cover_from(c, month: str, target: dict, room: dict[int, Decimal]) -> dict | None:
    """The category with the most room left (its bills still to pay set aside) that can cover the largest
    overspend; both need a plan of their own, as Move room asks (budget_move.html)."""
    plans = c.budgets.amounts_for(month, loans=False)
    if target["category_id"] not in plans:
        return None
    amount = Decimal(target["over"]).to_integral_value(rounding=ROUND_CEILING)
    best = max(((left, cid) for cid, left in room.items()
                if cid != target["category_id"] and cid in plans and left >= amount), default=None)
    if best is None:
        return None
    return {"name": c.categories.get(best[1]).name, "amount": amount,
            "href": f"/budget/move?month={month}&to={target['category_id']}&from={best[1]}&amount={amount}"}


def _plan_bills(c, everyday) -> list[dict]:
    """The bills and loan payments in the month's plan, late first, then due, then paid: each once, with Mark paid."""
    day = today()
    rows = []
    for p in everyday.payments:
        late = p.days_late(day) if p.outstanding else 0
        rows.append({"name": p.item.name, "due": p.due_date, "kind": KIND_LABELS.get(p.item.kind, ""),
                     "amount": c.planning.amount_in_base(p, p.still_owed if p.outstanding else p.amount, day),
                     "state": "paid" if p.status == PaymentStatus.PAID else "late" if late else "due", "late": late,
                     "pay": f"/plan/items/{p.item.id}/pay?due={p.due_date}&back=%2Fbudget" if p.outstanding else ""})
    rows.sort(key=lambda r: ({"late": 0, "due": 1, "paid": 2}[r["state"]], r["due"]))
    return rows


@router.post("/tracking")
async def update_tracking(request: Request):
    c = container(request)
    form = await request.form()
    selected = sorted(int(key[8:]) for key in form if key.startswith("trackon_") and key[8:].isdigit())
    _save_category_setting(c, "budget_tracked_categories", set(selected))
    if request.headers.get("X-Requested-With") == "fetch":
        return Response("Saved", status_code=204)
    return redirect("/budget", "Tracked categories updated.")


@router.post("/suggestions")
async def budget_suggestions(request: Request):
    c = container(request)
    form = await request.form()
    try:
        category_id = int(str(form.get("category_id", "")))
        action = str(form.get("action", ""))
        month = str(form.get("month", month_of(today())))
        parse_month(month)
        if action == "track":
            if getattr(c, "is_journal", False):
                c.journal_workflows.save_category_rule(category_id=category_id, month=month, mode="average3", value="",
                    fingerprint=c.journal_workflows.bulk_budget_fingerprint([category_id]))
                return redirect(f"/budget?month={month}", "Preference saved.")
            selected = _category_setting_ids(c, "budget_tracked_categories")
            selected.add(category_id)
            _save_category_setting(c, "budget_tracked_categories", selected)
            c.budgets.set_budget(category_id, month, "", average_months=3)
        elif action in {"later", "never"}:
            suppressed = json.loads(c.settings.get("budget_suppressed_categories") or "{}")
            if isinstance(suppressed, list):
                suppressed = {str(item): "never" for item in suppressed}
            key = c.categories.get(category_id).code if getattr(c, "is_journal", False) else str(category_id)
            suppressed[key] = "never" if action == "never" else month
            c.settings.set("budget_suppressed_categories", json.dumps(suppressed))
    except (ValueError, TypeError):
        return redirect("/budget", "Choose a valid category.")
    return redirect(f"/budget?month={month}", "Preference saved.")


@router.post("/one-off")
async def mark_budget_one_off(request: Request):
    c = container(request); form = await request.form()
    try:
        category_id = int(str(form.get("category_id", "")))
        month = str(form.get("month", month_of(today()))); parse_month(month)
        c.budgets._budgetable(category_id)
        excluded = _category_setting_ids(c, "budget_one_off_exclusions")
        excluded.add(category_id)
        if getattr(c, "is_journal", False):
            codes = {c.categories.get(item).code for item in excluded}
            c.settings.set("budget_one_off_exclusions", json.dumps(sorted(codes)))
        else:
            _save_category_setting(c, "budget_one_off_exclusions", excluded)
    except (ValueError, TypeError, LightningError) as exc:
        return redirect("/budget", exc.message if isinstance(exc, LightningError) else "Choose a valid category.")
    return redirect(f"/budget?period=month&month={month}", "Category excluded from background estimates.")


def _budget_return_to(raw: str | None) -> str:
    value = str(raw or "")
    if not (value.startswith("/budget") or value.startswith("/settings")) or value.startswith("//") or "\\" in value:
        return "/budget"
    try:
        from urllib.parse import urlsplit, parse_qs
        parts = urlsplit(value)
        if parts.netloc or parts.scheme or not (parts.path == "/budget" or parts.path.startswith("/budget/")):
            return "/budget"
        if parts.query:
            parse_period({key: values[-1] for key, values in parse_qs(parts.query).items()}, today())
    except (ValueError, ValidationError):
        return "/budget"
    return value


@router.get("/settings")
async def budget_settings_page(request: Request):
    return redirect("/settings?section=budget&return_to=%2Fbudget")


@router.post("/settings/full")
async def save_budget_settings(request: Request):
    c = container(request); form = await request.form()
    return_to = _budget_return_to(str(form.get("return_to", "")))
    try:
        income_months = str(form.get("income_months", "3"))
        if income_months not in {"3", "6"}:
            raise ValidationError("Average monthly income must use three or six completed months.")
        manual = str(form.get("manual_income", "")).strip()
        if manual and to_decimal(manual, "manual_income") < ZERO:
            raise ValidationError("Manual monthly income cannot be negative.")
        enabled = form.get("carryover") == "1"
        carry_month = month_of(today())  # turning carryover on or off takes effect this month (owner, 2026-10-06)
        categories = [int(x) for x in form.getlist("income_category") if str(x).isdigit()]
        exclusions = [int(x) for x in form.getlist("exclusion_category") if str(x).isdigit()]
        if getattr(c, "is_journal", False):
            c.journal_workflows.save_budget_settings(
                income_categories=sorted(set(categories)), income_months=income_months, manual_income=manual,
                exclusions=sorted(set(exclusions)), carryover=enabled, carry_month=carry_month,
                recurring_shown="income_from_recurring_shown" in form,
                income_from_recurring=form.get("income_from_recurring") == "1",
                emergency_basis=str(form.get("emergency_basis", "")) or None,
                fingerprint=c.journal_workflows.budget_settings_fingerprint())
            if request.headers.get("X-Requested-With") == "fetch":
                return Response(status_code=204)
            return redirect(return_to, "Budget settings updated.")
        if "income_from_recurring_shown" in form:  # nor this one (it is offered after a raise)
            c.settings.set(INCOME_FROM_RECURRING, "1" if form.get("income_from_recurring") == "1" else "0")
        if "emergency_basis" in form:  # a form without the choice leaves it alone
            c.budgets.set_emergency_basis(str(form.get("emergency_basis")))
        c.settings.set("budget_income_categories", json.dumps(sorted(set(categories))))
        c.settings.set("budget_income_months", income_months)
        c.settings.set("budget_manual_monthly_income", manual)
        c.settings.set("budget_one_off_exclusions", json.dumps(sorted(set(exclusions))))
        c.settings.set("budget_carryover_global", "1" if enabled else "0")
        c.settings.set("budget_carryover_month", carry_month)
        tracked = set(c.budgets.amounts_for(carry_month))
        c.budgets.set_carryover(carry_month, {category_id: enabled for category_id in tracked})
        if request.headers.get("X-Requested-With") == "fetch":
            return Response(status_code=204)
    except (LightningError, ValueError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Check the entered values."
        if request.headers.get("X-Requested-With") == "fetch":
            return Response(message, status_code=400, media_type="text/plain")
        return redirect("/settings?section=budget", message)
    return redirect(return_to, "Budget settings updated.")


@router.get("/carryover/reset/{category_id:int}")
async def carryover_reset_popup(request: Request, category_id: int):
    c = container(request); month = str(request.query_params.get("month", month_of(today())))
    try:
        parse_month(month)
    except ValidationError as exc:
        return redirect("/budget", exc.message)
    category = c.categories.get(category_id)
    line = next((line for section in c.budgets.month_view(month).sections for line in section.lines
                 if line.category_id == category_id), None)
    if line is None:
        return redirect(f"/budget?month={month}", "This category has no active budget in that month.")
    return render(request, "budget_reset_popup.html", category=category, month=month, amount=line.opening_carryover)


@router.get("/carryover-bridge")
async def carryover_bridge(request: Request):
    c = container(request); month = str(request.query_params.get("month", month_of(today())))
    try:
        parse_month(month)
    except ValidationError as exc:
        return redirect("/budget", exc.message)
    previous, _ = _neighbours(month)
    prior_view = c.budgets.month_view(previous); current_view = c.budgets.month_view(month)
    prior = {line.category_id: line for section in prior_view.sections for line in section.lines}
    current = {line.category_id: line for section in current_view.sections for line in section.lines}
    categories = []
    for category_id in sorted(set(prior) | set(current)):
        before, after = prior.get(category_id), current.get(category_id)
        if not after or not after.carryover_enabled:
            continue
        categories.append({"name": after.name, "prior_budget": before.available if before else ZERO,
                          "prior_spent": before.actual if before else ZERO,
                          "incoming": after.opening_carryover,
                          "base": after.budget or ZERO,
                          "current": after.available or ZERO})
    return render(request, "budget_bridge.html", month=month, previous=previous, categories=categories)


@router.post("/carryover/reset/{category_id:int}")
async def reset_carryover(request: Request, category_id: int):
    c = container(request); form = await request.form(); month = str(form.get("month", month_of(today())))
    try:
        c.budgets.reset_carryover(category_id, month)
    except LightningError as exc:
        return redirect(f"/budget?month={month}", exc.message)
    return redirect(f"/budget?month={month}", "Carryover reset from this month.")


@router.post("/limit/{category_id:int}")
async def inline_limit(request: Request, category_id: int):
    c = container(request)
    form = await request.form()
    month = str(form.get("month", month_of(today())))
    try:
        if getattr(c, "is_journal", False):
            c.journal_workflows.save_category_rule(category_id=category_id, month=month, mode="fixed",
                value=str(form.get("amount", "")), fingerprint=c.journal_workflows.bulk_budget_fingerprint([category_id]))
            return Response("Saved", status_code=204) if request.headers.get("X-Requested-With") == "fetch" else redirect(
                f"/budget?month={month}", "Limit saved.")
        c.budgets.set_budget(category_id, month, str(form.get("amount", "")))
        current = _category_setting_ids(c, "budget_tracked_categories")
        current.add(category_id)
        _save_category_setting(c, "budget_tracked_categories", current)
    except (LightningError, ValueError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Enter a valid monthly limit."
        if request.headers.get("X-Requested-With") == "fetch":
            return Response(message, status_code=400, media_type="text/plain")
        return redirect(f"/budget?month={month}", message)
    if request.headers.get("X-Requested-With") == "fetch":
        return Response("Saved", status_code=204)
    return redirect(f"/budget?month={month}", "Limit saved.")


@router.post("/rule/{category_id:int}")
async def inline_rule(request: Request, category_id: int):
    """One field per category: "1500" is a fixed amount, "12%" is 12% of average monthly income,
    and an empty field clears the category's own rule."""
    c = container(request); form = await request.form()
    month = str(form.get("month", month_of(today())))
    raw = str(form.get("rule", "")).strip().replace("٪", "%")
    try:
        if getattr(c, "is_journal", False):
            mode, value = ("percentage", raw[:-1].strip()) if raw.endswith("%") else ("fixed", raw)
            c.journal_workflows.save_category_rule(category_id=category_id, month=month, mode=mode, value=value,
                fingerprint=c.journal_workflows.bulk_budget_fingerprint([category_id]))
            if request.headers.get("X-Requested-With") == "fetch":
                return Response(status_code=204)
            return redirect(f"/budget?month={month}", "Budget saved." if raw else "Budget cleared: this category has no limit now.")
        if raw.endswith("%"):
            c.budgets.set_income_percentage(category_id, month, raw[:-1].strip())
        else:
            c.budgets.set_budget(category_id, month, raw)
        current = _category_setting_ids(c, "budget_tracked_categories"); current.add(category_id)
        _save_category_setting(c, "budget_tracked_categories", current)
    except (LightningError, ValueError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Enter an amount like 1,500 or a percentage like 12%."
        if request.headers.get("X-Requested-With") == "fetch":
            return Response(message, status_code=400, media_type="text/plain")
        return redirect(f"/budget?month={month}", message)
    if request.headers.get("X-Requested-With") == "fetch":
        return Response(status_code=204)
    if not raw:
        return redirect(f"/budget?month={month}", "Budget cleared: this category has no limit now.")
    return redirect(f"/budget?month={month}", "Budget saved.")


@router.post("/percentage/{category_id:int}")
async def inline_percentage(request: Request, category_id: int):
    c = container(request); form = await request.form()
    month = str(form.get("month", month_of(today())))
    try:
        raw = str(form.get("percentage", "")).strip()
        if getattr(c, "is_journal", False):
            c.journal_workflows.save_category_rule(category_id=category_id, month=month,
                mode="percentage" if raw else "fixed", value=raw,
                fingerprint=c.journal_workflows.bulk_budget_fingerprint([category_id]))
            return Response(status_code=204) if request.headers.get("X-Requested-With") == "fetch" else redirect(
                f"/budget?month={month}", "Income percentage saved.")
        if raw:
            c.budgets.set_income_percentage(category_id, month, raw)
        else:
            c.budgets.set_budget(category_id, month, "")
        current = _category_setting_ids(c, "budget_tracked_categories"); current.add(category_id)
        _save_category_setting(c, "budget_tracked_categories", current)
    except (LightningError, ValueError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Enter a valid percentage."
        return Response(message, status_code=400, media_type="text/plain") if request.headers.get("X-Requested-With")=="fetch" else redirect(f"/budget?month={month}", message)
    if request.headers.get("X-Requested-With") == "fetch":
        return Response(status_code=204)
    return redirect(f"/budget?month={month}", "Income percentage saved.")


@router.post("/bulk")
async def bulk_budget_rule(request: Request):
    c = container(request); form = await request.form()
    month = str(form.get("month", month_of(today())))
    selected = sorted({int(x) for x in form.getlist("category_id") if str(x).isdigit()})
    action = str(form.get("action", ""))
    if not selected:
        return redirect(f"/budget?period=month&month={month}", "Select at least one category.")
    if action not in {"percentage", "average3", "average6"}:
        return redirect(f"/budget?period=month&month={month}", "Choose a bulk rule.")
    token = uuid.uuid4().hex
    if getattr(c, "is_journal", False):
        try:
            c.journal_workflows.apply_bulk_budget(month=month, category_ids=selected, action=action,
                percentage=str(form.get("percentage", "")), token=token,
                fingerprint=c.journal_workflows.bulk_budget_fingerprint(selected))
        except LightningError as exc:
            return redirect(f"/budget?period=month&month={month}", exc.message)
        return redirect(f"/budget?period=month&month={month}&undo={token}", f"Updated {len(selected)} categories.")
    # Store the exact affected rows so the immediate result can be undone.
    before = c.budgets.snapshot_rows(selected)
    try:
        with c.db.transaction():
            if action == "percentage":
                percentage = form.get("percentage", "")
                for category_id in selected:
                    c.budgets.set_income_percentage(category_id, month, percentage)
            else:
                period = 3 if action == "average3" else 6
                c.budgets.save_month(month, {category_id: "" for category_id in selected},
                                     average_months={category_id: period for category_id in selected})
        c.settings.set("budget_bulk_undo", json.dumps({"token": token, "month": month,
            "category_ids": selected, "rows": before}))
    except LightningError as exc:
        return redirect(f"/budget?period=month&month={month}", exc.message)
    return redirect(f"/budget?period=month&month={month}&undo={token}", f"Updated {len(selected)} categories.")


@router.post("/bulk/undo")
async def undo_bulk_budget_rule(request: Request):
    c = container(request); form = await request.form(); token = str(form.get("token", ""))
    try:
        if getattr(c, "is_journal", False):
            snapshot = json.loads(c.settings.get("budget_bulk_undo") or "{}")
            if not token or token != snapshot.get("token"):
                raise ValidationError("This bulk change can no longer be undone.")
            c.journal_workflows.undo_bulk_budget(key="budget_bulk_undo", token=token)
            return redirect(f"/budget?period=month&month={snapshot['month']}", "Bulk change undone.")
        snapshot = json.loads(c.settings.get("budget_bulk_undo") or "{}")
        if not token or token != snapshot.get("token"):
            raise ValidationError("This bulk change can no longer be undone.")
        ids = [int(x) for x in snapshot["category_ids"]]
        rows = snapshot["rows"]
        c.budgets.restore_rows(ids, rows)
        c.settings.set("budget_bulk_undo", "")
        return redirect(f"/budget?period=month&month={snapshot['month']}", "Bulk change undone.")
    except (LightningError, ValueError, KeyError, TypeError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Undo is unavailable."
        return redirect("/budget", message)


@router.post("/ceiling")
async def save_ceiling(request: Request):
    c = container(request)
    form = await request.form()
    amount = str(form.get("amount", "")).strip()
    try:
        if amount:
            from lightning.core.money import to_decimal
            if to_decimal(amount, "amount") < 0:
                raise ValidationError("Ceiling cannot be negative.")
        c.settings.set("budget_overall_ceiling", amount)
    except LightningError as exc:
        if request.headers.get("X-Requested-With") == "fetch":
            return Response(exc.message, status_code=400, media_type="text/plain")
        return redirect("/budget", exc.message)
    if request.headers.get("X-Requested-With") == "fetch":
        return Response("Saved", status_code=204)
    return redirect("/budget", "Overall ceiling saved.")


@router.get("")
async def budget_page(request: Request):
    try:
        month = _month(request)
    except ValidationError:
        return redirect("/budget", "That month is invalid. Use YYYY-MM, for example 2026-09.")
    if month > month_of(today()):
        # Budget amounts repeat into later months, so this month's plan is next month's plan too.
        return redirect("/budget", f"{month} has not started yet. This month's amounts carry on into it "
                                   "until you change them.")
    return _page(request, month)


@router.get("/fill")
async def budget_fill_page(request: Request):
    c = container(request)
    try:
        month = _month(request)
    except ValidationError:
        return redirect("/budget", "That month is invalid. Use YYYY-MM, for example 2026-09.")
    if month > month_of(today()):
        return redirect("/budget", f"{month} has not started yet. Choose a current or past month to fill.")
    source = request.query_params.get("source", "last_month")
    try:
        proposal = c.budgets.fill_proposal(month, source)
    except LightningError as exc:
        return render(request, "budget_fill.html", month=month, source="last_month", proposal=None,
                      error=exc.message, status_code=400)
    proposal, room_left = c.health.fit_fill(proposal)
    return render(request, "budget_fill.html", month=month, source=source, proposal=proposal, error="",
                  check=c.health.plan_check(month), room_left=room_left)


@router.post("/fill")
async def apply_budget_fill(request: Request):
    c = container(request)
    try:
        month = _month(request)
    except ValidationError:
        return redirect("/budget", "That month is invalid. Use YYYY-MM, for example 2026-09.")
    if month > month_of(today()):
        return redirect("/budget", f"{month} has not started yet. Choose a current or past month to fill.")
    form = await request.form()
    source = str(form.get("source", ""))
    try:
        proposal = c.budgets.fill_proposal(month, source)
        allowed = {row.category_id for row in proposal.rows if row.selectable and row.category_id is not None}
        selected = {int(value) for value in form.getlist("selected") if str(value).isdigit()}
        if not selected.issubset(allowed):
            raise ValidationError("Refresh the proposal before applying these categories.", "categories")
        amounts = {category_id: str(form.get(f"amount_{category_id}", "")) for category_id in selected}
        changed = c.budgets.apply_fill(month, amounts)
    except LightningError as exc:
        values = {row.category_id: str(form.get(f"amount_{row.category_id}", ""))
                  for row in proposal.rows if row.category_id is not None} if "proposal" in locals() and proposal else {}
        return render(request, "budget_fill.html", month=month, source=source, proposal=proposal if "proposal" in locals() else None,
                      values=values, error=exc.message, status_code=400)
    if not changed:
        return redirect(f"/budget?month={month}", "Those base limits are already set for this month.")
    return redirect(f"/budget?month={month}", f"Applied {changed} budget{'s' if changed != 1 else ''} for {month} only.")


@router.post("")
async def save_budget(request: Request):
    c = container(request)
    try:
        month = _month(request)
    except ValidationError:
        return redirect("/budget", "That month is invalid. Use YYYY-MM, for example 2026-09.")
    form = await request.form()
    ids = {int(key[2:]) for key in form if key.startswith(("b_", "m_")) and key[2:].isdigit()}
    amounts = {category_id: str(form.get(f"b_{category_id}", "")) for category_id in ids}
    averages = {int(key[2:]): str(value) for key, value in form.items()
                if key.startswith("m_") and key[2:].isdigit()}
    only = bool(form.get("only_this_month"))
    try:
        changed = c.budgets.save_month(month, amounts, only_this_month=only, average_months=averages)
    except LightningError as exc:
        values = {f"b_{k}": v for k, v in amounts.items()} | {f"m_{k}": v for k, v in averages.items()}
        return _page(request, month, values=values, error=exc.message,
                     status_code=400)
    if not changed:
        return redirect(f"/budget?month={month}", "Nothing changed.")
    scope = f"for {month} only" if only else f"from {month} onward"
    return redirect(f"/budget?month={month}", f"Saved {changed} budget{'s' if changed != 1 else ''} {scope}.")


@router.post("/setup")
async def accept_plan(request: Request):
    c = container(request)
    try:
        month = _month(request)
    except ValidationError:
        return redirect("/budget", "That month is invalid. Use YYYY-MM, for example 2026-09.")
    form = await request.form()
    amounts = {}
    try:
        for key, value in form.items():
            if key.startswith("suggest_") and key[8:].isdigit():
                amounts[int(key[8:])] = str(value)
        if amounts:
            c.budgets.save_month(month, amounts)
        else:
            group_id = int(str(form.get("group_id", "")))
            c.budgets.set_budget(group_id, month, str(form.get("broad_limit", "")))
    except (ValueError, LightningError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Choose a valid monthly limit."
        return _page(request, month, error=message, status_code=400)
    return redirect(f"/budget?month={month}", "Your monthly spending plan is ready. You can refine it anytime.")


@router.post("/carryover")
async def update_carryover(request: Request):
    c = container(request)
    try:
        month = _month(request)
    except ValidationError:
        return redirect("/budget", "That month is invalid. Use YYYY-MM, for example 2026-09.")
    form = await request.form()
    ids = {int(key[8:]) for key in form if key.startswith("carryon_") and key[8:].isdigit()}
    # The hidden companion includes unchecked controls so opting out is explicit.
    settings = {int(key[11:]): str(value) == "1" for key, value in form.items()
                if key.startswith("carryvalue_") and key[11:].isdigit()}
    settings.update({category_id: True for category_id in ids})
    try:
        changed = c.budgets.set_carryover(month, settings)
    except LightningError as exc:
        return redirect(f"/budget?month={month}", exc.message)
    return redirect(f"/budget?month={month}", f"Updated carryover for {changed} budget line{'s' if changed != 1 else ''}.")


@router.post("/carryover/global")
async def update_global_carryover(request: Request):
    c = container(request)
    form = await request.form()
    month = str(form.get("month", month_of(today())))
    try:
        parse_month(month)
        enabled = form.get("enabled") == "1"
        c.budgets.set_carryover(month, {category_id: enabled for category_id in c.budgets.amounts_for(month)})
    except LightningError as exc:
        if request.headers.get("X-Requested-With") == "fetch":
            return Response(exc.message, status_code=400, media_type="text/plain")
        return redirect(f"/budget?month={month}", exc.message)
    c.settings.set("budget_carryover_global", "1" if enabled else "0")
    if request.headers.get("X-Requested-With") == "fetch":
        return Response("Saved", status_code=204)
    return redirect(f"/budget?month={month}", "Carryover setting updated.")


@router.get("/raise")
async def raise_offer(request: Request):
    """Income above the average: plan with it, save the difference, or keep the average (Needs you)."""
    c = container(request)
    offer = c.health.raise_offer(str(request.query_params.get("month", month_of(today()))))
    if offer is None:
        return redirect("/budget", "Your plan already counts your income.")
    return render(request, "budget_raise.html", offer=offer)


@router.post("/raise")
async def take_raise(request: Request):
    c = container(request)
    form = await request.form()
    month = str(form.get("month", month_of(today())))
    try:
        parse_month(month)
        message = c.health.take_raise(str(form.get("choice", "")), month)
    except LightningError as exc:
        return redirect(f"/budget?month={month}", exc.message)
    return redirect(f"/budget?month={month}", " ".join(x for x in (message, c.health.plan_note(month)) if x))


@router.get("/move")
async def move_room_popup(request: Request):
    """A category over plan two months running: move room to it from one that had room (Needs you)."""
    c = container(request)
    query = request.query_params
    month = str(query.get("month", month_of(today())))
    try:
        parse_month(month)
        to, source = c.categories.get(int(query.get("to", ""))), c.categories.get(int(query.get("from", "")))
        amount = to_decimal(str(query.get("amount", "")), "amount")
    except (LightningError, ValueError):
        return redirect(f"/budget?month={month}", "Choose two categories and an amount.")
    plans = c.budgets.amounts_for(month, loans=False)
    to_plan, from_plan = plans.get(to.id, (None,))[0], plans.get(source.id, (None,))[0]
    if to_plan is None or from_plan is None:
        return redirect(f"/budget?month={month}", "Both categories need a plan of their own this month.")
    return render(request, "budget_move.html", month=month, to=to, source=source, amount=amount,
                  to_plan=to_plan, from_plan=from_plan)


@router.post("/move")
async def move_room(request: Request):
    c = container(request)
    form = await request.form()
    month = str(form.get("month", month_of(today())))
    try:
        parse_month(month)
        to_id, from_id = int(str(form.get("to", ""))), int(str(form.get("from", "")))
        c.budgets.move_room(month, to_id, from_id, str(form.get("amount", "")))
    except ValueError:
        return redirect(f"/budget?month={month}", "Choose two categories.")
    except LightningError as exc:
        return redirect(f"/budget?month={month}", exc.message)
    names = c.categories.get(to_id).name, c.categories.get(from_id).name
    return redirect(f"/budget?month={month}", f"Moved plan from {names[1]} to {names[0]} from {month} on.")
