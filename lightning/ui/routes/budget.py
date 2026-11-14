from __future__ import annotations

from decimal import Decimal
import json
import uuid

from fastapi import APIRouter, Request, Response

from lightning.core.dates import fmt_date, month_of, parse_month, today
from lightning.core.errors import LightningError, ValidationError
from lightning.workflows.ai_prompts import budget_prompt
from lightning.categories.domain import Movement, Scope
from lightning.core.money import ZERO, fmt, to_decimal
from lightning.core.plural import counted

from lightning.budgeting.domain import INCOME_FROM_RECURRING
from lightning.budgeting.period import budget_period, category_pace, over_matters
from lightning.planning.domain import KIND_LABELS, PaymentStatus
from lightning.planning.health import PlanCheck

from .. import charts, keynotes, kpis, status as page_status
from ..web import container, redirect, render, settled_save
from ..periods import parse_period
from ..budget_rows import cover_from, last_payments, neighbours, pace_line

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


def _page(request: Request, month: str, values: dict | None = None, error: str = "", status_code: int = 200):
    c = container(request)
    earliest = c.budgets.first_owned_spending_date()
    try:
        period = parse_period(request.query_params, today(), earliest)
    except ValidationError as exc:
        period = parse_period({"period": "month", "month": month}, today())
        error = error or exc.message  # say why the month is shown instead of the range asked for
    month = period.end.strftime("%Y-%m")
    schedule = c.schedules.view()
    figures = budget_period(c.budgets, c.categories, schedule, key=period.key, start=period.start, end=period.end,
                            month=month)
    view, month_views, tracked, by_group = figures.view, figures.month_views, figures.tracked, figures.by_group
    period_base, period_carryover, period_budgeted = figures.period_base, figures.period_carryover, figures.period_budgeted
    group_totals, category_periods, period_spending = figures.group_totals, figures.category_periods, figures.period_spending
    background_counts, background_totals = figures.background_counts, figures.background_totals
    spending_start, period_income, period_actual = figures.spending_start, figures.period_income, figures.period_actual
    prev_month, next_month = neighbours(month)
    has_plan = c.budgets.has_plan(month, schedule=c.schedules.view())
    suggestions = c.budgets.first_plan_suggestions(month) if not has_plan else {}  # round numbers (BU-3)
    suggestions_view = {category_id: (c.categories.display_name(category_id), amount)
                        for category_id, amount in suggestions.items()}
    suggestion_groups: dict[str, list] = {}  # L1 as a header, each category under it by its own name
    for category_id, (name, amount) in suggestions_view.items():
        parts = name.split(" › ")
        suggestion_groups.setdefault(parts[0], []).append((category_id, " › ".join(parts[1:]) or parts[0], amount))
    category_averages = c.budgets.category_averages(month, schedule=c.schedules.view())
    averages = {cid: row["average3"] for cid, row in category_averages.items()}
    averages6 = {cid: row["average6"] for cid, row in category_averages.items()}
    average_observations = {cid: row["observed3"] for cid, row in category_averages.items()}
    average_full = {cid: row["full3"] for cid, row in category_averages.items()}
    income_basis = c.budgets.budgeting_income(month, schedule=c.schedules.view())
    # A default, not a setting (owner, 2026-10-06): suggest tracking a category that averages a fifth of income.
    tracking_suggestions = [{**row, "reason": f"{row['share']:.1f}% of average monthly income"}
                            for row in c.budgets.tracking_suggestions(month, TRACK_SUGGESTION_PERCENT, schedule=c.schedules.view())]
    funding_adjustment_total = figures.funding_adjustment_total
    gross_period_spending = figures.gross_period_spending
    # One savings target for every screen (Financial health › Savings rate limit). A month is checked
    # with its goals below, in the key notes; a longer period against the target alone.
    check = c.health.plan_check(month) if period.key == "month" else None
    period_check = PlanCheck(period.label, period_income, period_base, c.health.limit_values()["savings_rate"], ZERO)
    ceiling_warning = ("" if period_income <= ZERO or check is not None else
                       "Planned amounts exceed average monthly income" if period_base > period_income else
                       f"This plan saves less than your {period_check.target_percent.normalize():f}% savings target: "
                       f"plan {fmt(period_check.over_by, 0)} less" if period_check.over_by else "")
    period_left = figures.period_left
    # Feedback ticket 93: the System group counts as Personal spending, so its section read "Personal" under
    # "System Categories". Say what is in it instead.
    lines = {line.category_id: line for _, view in month_views for section in view.sections
             for line in [*section.groups, *section.lines]}
    system_id = next((cid for cid, line in lines.items() if line.code == "EXP.SYSTEM"), None)
    if system_id in group_totals:
        names = [lines[cid].name for cid in by_group.get(system_id, []) if cid in lines
                 and (period_spending.get(cid) or category_periods.get(cid, {}).get("budgeted"))]
        more = len(names) - 3  # not money
        group_totals[system_id]["note"] = ", ".join(names[:3]) + (f" and {more} more" if more > 0 else "")  # not money
        # The PC page names the group by what is in it, never by the internal "System Categories" (audit 12, B4).
        if names:
            group_totals[system_id]["title"] = ", ".join(names[:3]) + (f", +{more}" if more > 0 else "")  # not money
    group_rows = sorted(group_totals.items(),
                        key=lambda item: (item[1]["left"] >= ZERO, -item[1]["spent"], item[1]["name"].casefold()))
    unplanned_spending = figures.unplanned_spending
    plan_outside_groups = figures.plan_outside_groups
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
                                    "href": f"/budget/category/{line.category_id}/sheet?month={month}"})  # the one category sheet (3G6)
    meter_lines.sort(key=lambda r: (not r["m"]["over"], -(r["m"].get("share") or 0)))
    # Over plan or already spending first; the categories nothing has touched fold under "N untouched" (audit 12, B3).
    meter_active = [r for r in meter_lines if r["used"] or r["m"]["over"]]
    meter_rest = [r for r in meter_lines if not (r["used"] or r["m"]["over"])]
    month_first, month_last = parse_month(month)
    days_left = (month_last - today()).days + 1 if month_first <= today() <= month_last else 0  # not money
    # The same Left in plan as the headline and the Overview (background estimates counted in).
    month_left = c.budgets.plan_summary(month, schedule=c.schedules.view())["left"] if c.budgets.has_plan(month, schedule=c.schedules.view()) else ZERO
    notes = keynotes.budget_left(month_left, days_left,
                                 [r["label"] for r in meter_lines if r["m"]["over"]], "#budget-meters") if c.budgets.has_plan(month, schedule=c.schedules.view()) else []
    if check is not None and check.planned is not None:
        notes = keynotes.plan_check(check) + notes  # not money
    left_note = keynotes.per_day(month_left, days_left) if c.budgets.has_plan(month, schedule=c.schedules.view()) else ""
    # KPI cards (guideline 3.32 A08): every figure against something, two to four in the row. The figures come
    # from the forecaster's EverydayBudget, the same Budget until payday Cash planning shows.
    raise_offer = c.health.raise_offer(month) if period.key == "month" else None
    kpi_cards, pace, plan_bills, everyday = [], None, [], None
    if period.key == "month" and has_plan:
        everyday = c.forecaster.everyday(month, today())
        left_note = keynotes.per_day_everyday(everyday)  # one daily figure on the phone and the PC (BV-12A)
        # BU-2 (3H2): an overspend raises Needs you when it matters: 100 or more and 5% or more of the category's plan.
        # A smaller one still reads rose on its own bar.
        over = sorted(({"name": r["label"], "over": r["b"]["over_by"], "category_id": r["category_id"]}
                       for r in meter_lines if r["b"]["is_over"] and over_matters(r["b"]["over_by"], r["total"])),
                      key=lambda r: -r["over"])
        kpi_cards = kpis.budget_month(everyday, over=over, check=check, raise_offer=raise_offer,
                                      move=cover_from(c, month, over[0], everyday.room) if over else None, month=month,
                                      funded_elsewhere=funding_adjustment_total > ZERO)
        if everyday.day and everyday.everyday_plan > 0:
            pace = charts.pace(everyday.by_day, everyday.everyday_plan, everyday.days_in_month, everyday.last_month_by_day)
        plan_bills = _plan_bills(c, everyday)
    elif period.key != "month":
        kpi_cards = kpis.budget_period(period_actual, period_budgeted,
                                       [(key, c.budgets.plan_summary(key, schedule=c.schedules.view())["left"], parse_month(key)[1] < today())
                                        for key, _ in month_views if c.budgets.has_plan(key, schedule=c.schedules.view())],
                                       period.label, funded_elsewhere=funding_adjustment_total > ZERO)
    # Answer first (guideline 3.33, A09): Left in plan is the page's Lead with the pace chart beside it; what is over
    # plan is a Needs you row under it; Everyday spending and Plan leaves to save stay as the KPI row.
    lead, pace_card, needs = None, None, []
    if period.key == "month" and has_plan:
        by_key = {k["key"]: k for k in kpi_cards}
        lead, pace_card = by_key.get("left"), by_key.get("everyday")
        kpi_cards = kpis.row([by_key.get("everyday"), by_key.get("saves")])
        rows = {r["category_id"]: r for r in meter_lines}
        for i, o in enumerate(over):
            move = cover_from(c, month, o, everyday.room) if i == 0 else None
            r = rows[o["category_id"]]
            needs.append({"label": f"{o['name']} is {fmt(o['over'], 0)} over its plan",
                          "detail": f"{fmt(r['used'], 0)} spent of {fmt(r['total'], 0)}",
                          "href": move["href"] if move else r["href"], "popup": True,  # Move room or the category sheet (3G6)
                          "action": f"Move {fmt(move['amount'], 0)} from {move['name']}" if move else "See it"})
        if raise_offer and not by_key.get("saves"):
            needs.append({"label": "Your income went up",
                          "detail": f"Recurring expects {fmt(raise_offer['raise'], 0)} more than your average.",
                          "href": f"/budget/raise?month={month}", "popup": True, "action": "Choose"})
    status = page_status.budget(everyday, has_plan, period.key, period_actual, period_budgeted)
    return render(request, "budget.html", budget_ai_prompt=budget_prompt(), notes=notes, meter_active=meter_active, meter_rest=meter_rest, kpi_cards=kpi_cards, pace=pace, plan_bills=plan_bills, everyday=everyday,
                  lead=lead, pace_card=pace_card, needs=needs, status=status,
                  raise_in_card=bool(needs and needs[-1]["href"].startswith("/budget/raise")) or any(k["key"] == "saves" for k in kpi_cards),
                  raise_offer=raise_offer, meter_lines=meter_lines, left_note=left_note, check=check,
                  plan_bar=charts.plan_bar(period_budgeted, period_actual),
                  status_code=status_code, view=view, month=month,
                  prev_month=prev_month, next_month=next_month, values=values or {}, error=error,
                  has_plan=has_plan, suggestions=suggestions_view, suggestion_groups=suggestion_groups,
                  tracked=tracked, averages=averages,
                  averages6=averages6, average_observations=average_observations, average_full=average_full,
                  tracking_suggestions=tracking_suggestions,
                  carryover=c.settings.get("budget_carryover_global") == "1",
                  overall_ceiling=c.settings.get("budget_overall_ceiling"), this_month=month_of(today()),
                  personal_group=next((cat.id for cat in c.categories.tree(Movement.OUTFLOW)
                                       if cat.depth == 1 and cat.scope == Scope.PERSONAL), None),
                  low_confidence=keynotes.low_confidence_note(c.budgets.plan_summary(month, schedule=c.schedules.view())["low_confidence"]) if period.key == "month" else "",
                  plan_from=fmt_date(spending_start) if spending_start != period.start else "",
                  funding_adjustment_total=funding_adjustment_total,
                  gross_period_spending=gross_period_spending,
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
                  effective_month=month, previous_month=neighbours(month)[0],
                  previous_bridge=c.budgets.month_view(neighbours(month)[0], schedule=c.schedules.view()))


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
    with settled_save(request, container(request)):
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
        with settled_save(request, container(request)):
            if action == "track":
                if getattr(c, "is_journal", False):
                    c.journal_workflows.save_category_rule(category_id=category_id, month=month, mode="average3", value="",
                        fingerprint=c.journal_workflows.bulk_budget_fingerprint([category_id]))
                    return redirect(f"/budget?month={month}", "Preference saved.")
                selected = _category_setting_ids(c, "budget_tracked_categories")
                selected.add(category_id)
                _save_category_setting(c, "budget_tracked_categories", selected)
                c.budgets.set_budget(category_id, month, "", average_months=3, schedule=c.schedules.view())
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
        with settled_save(request, container(request)):
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
        with settled_save(request, container(request)):
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
            tracked = set(c.budgets.amounts_for(carry_month, schedule=c.schedules.view()))
            c.budgets.set_carryover(carry_month, {category_id: enabled for category_id in tracked}, schedule=c.schedules.view())
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
    line = next((line for section in c.budgets.month_view(month, schedule=c.schedules.view()).sections for line in section.lines
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
    previous, _ = neighbours(month)
    prior_view = c.budgets.month_view(previous, schedule=c.schedules.view()); current_view = c.budgets.month_view(month, schedule=c.schedules.view())
    prior = {line.category_id: line for section in prior_view.sections for line in section.lines}
    current = {line.category_id: line for section in current_view.sections for line in section.lines}
    categories = []
    for category_id in sorted(set(prior) | set(current)):
        before, after = prior.get(category_id), current.get(category_id)
        if not after or not after.carryover_enabled:
            continue
        categories.append({"name": after.name, "prior_budget": before.available if before else ZERO,
                          "prior_spent": before.planned_actual if before else ZERO,
                          "incoming": after.opening_carryover,
                          "base": after.budget or ZERO,
                          "current": after.available or ZERO})
    return render(request, "budget_bridge.html", month=month, previous=previous, categories=categories)


@router.post("/carryover/reset/{category_id:int}")
async def reset_carryover(request: Request, category_id: int):
    c = container(request); form = await request.form(); month = str(form.get("month", month_of(today())))
    try:
        with settled_save(request, container(request)):
            c.budgets.reset_carryover(category_id, month, schedule=c.schedules.view())
    except LightningError as exc:
        return redirect(f"/budget?month={month}", exc.message)
    return redirect(f"/budget?month={month}", "Carryover reset from this month.")


@router.get("/category/{category_id:int}/sheet")
async def category_sheet(request: Request, category_id: int):
    """One category sheet for every tab (3G6): this month's spending against its limit, the pace, the last payments,
    then Edit limit, Cover it and See transactions. Budget, Spending and Transactions open the same sheet. Every
    figure is the Budget month view's own (BudgetLine), as the Budget page reads it."""
    c = container(request)
    category = c.categories.get(category_id)
    month = _month(request)
    first, last = parse_month(month)
    line = next((row for section in c.budgets.month_view(month, schedule=c.schedules.view()).sections
                 for row in section.lines if row.category_id == category_id), None)
    group = c.categories.get(category.parent_id).name if category.parent_id and category.depth > 2 else ""
    planned = line.available if line is not None else None
    spent = line.planned_actual if line is not None and planned is not None else (line.actual if line is not None else ZERO)
    r = None
    if planned is not None and planned > ZERO:
        figures = category_pace(planned, spent, first, last, today())
        left, share, current, pace = figures["left"], figures["share"], figures["current"], figures["pace"]
        r = {"category_id": category_id, "over": left < ZERO, "amount": abs(left), "share": share,
             "width": round(float(min(max(share, ZERO), Decimal(100))), 1),
             "risk": figures["risk"],
             "pace": round(float(pace), 1) if pace is not None else None}
        r["line"] = pace_line(r)
        if r["over"] and current:
            move = cover_from(c, month, {"category_id": category_id, "over": r["amount"]},
                               c.forecaster.everyday(month, today()).room)
            r["cover"] = move["href"] if move else ""
    editable = (category.movement == Movement.OUTFLOW and not category.is_root and not category.is_system
                and category.active and not (line is not None and line.from_loans))
    return render(request, "budget/category_sheet.html", category=category, group=group, r=r,
                  spent=spent, planned=planned, editable=editable, **last_payments(c, category_id, month))


@router.get("/category/{category_id:int}/edit")
async def one_category_limit(request: Request, category_id: int):
    """Change one rule without opening or submitting the full budget grid."""
    c = container(request)
    category = c.categories.get(category_id)
    if category.movement != Movement.OUTFLOW or category.is_root or category.is_system or not category.active:
        raise ValidationError("Choose an active spending category.")
    month = _month(request)
    line = next((row for section in c.budgets.month_view(month, schedule=c.schedules.view()).sections
                 for row in section.lines if row.category_id == category_id), None)
    if line is not None and line.from_loans:
        raise ValidationError("Change loan payments from Loans.")
    rule = (f"{line.income_percent.normalize():f}%" if line and line.income_percent is not None
            else f"{line.direct.normalize():f}" if line and line.direct is not None and not line.average_months else "")
    # IV-12Q3: the popup says what was spent against the limit, with a small bar, before you change it.
    from ..charts import meter
    used = line.planned_actual if line else ZERO
    return render(request, "budget_category_rule.html", category=category, month=month, rule=rule, line=line,
                  used=used, bar=meter(used, line.available if line else None))


@router.post("/limit/{category_id:int}")
async def inline_limit(request: Request, category_id: int):
    c = container(request)
    form = await request.form()
    month = str(form.get("month", month_of(today())))
    try:
        with settled_save(request, container(request)):
            if getattr(c, "is_journal", False):
                c.journal_workflows.save_category_rule(category_id=category_id, month=month, mode="fixed",
                    value=str(form.get("amount", "")), fingerprint=c.journal_workflows.bulk_budget_fingerprint([category_id]))
                return Response("Saved", status_code=204) if request.headers.get("X-Requested-With") == "fetch" else redirect(
                    f"/budget?month={month}", "Limit saved.")
            c.budgets.set_budget(category_id, month, str(form.get("amount", "")), schedule=c.schedules.view())
        current = _category_setting_ids(c, "budget_tracked_categories")
        # An empty limit stops tracking the category; a limit starts it.
        (current.add if str(form.get("amount", "")).strip() else current.discard)(category_id)
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
        with settled_save(request, container(request)):
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
                c.budgets.set_budget(category_id, month, raw, schedule=c.schedules.view())
        current = _category_setting_ids(c, "budget_tracked_categories")
        (current.add if raw else current.discard)(category_id)  # an empty rule stops tracking
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
        with settled_save(request, container(request)):
            if getattr(c, "is_journal", False):
                c.journal_workflows.save_category_rule(category_id=category_id, month=month,
                    mode="percentage" if raw else "fixed", value=raw,
                    fingerprint=c.journal_workflows.bulk_budget_fingerprint([category_id]))
                return Response(status_code=204) if request.headers.get("X-Requested-With") == "fetch" else redirect(
                    f"/budget?month={month}", "Income percentage saved.")
            if raw:
                c.budgets.set_income_percentage(category_id, month, raw)
            else:
                c.budgets.set_budget(category_id, month, "", schedule=c.schedules.view())
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
            with settled_save(request, c):
                c.journal_workflows.apply_bulk_budget(month=month, category_ids=selected, action=action,
                    percentage=str(form.get("percentage", "")), token=token,
                    fingerprint=c.journal_workflows.bulk_budget_fingerprint(selected))
        except LightningError as exc:
            return redirect(f"/budget?period=month&month={month}", exc.message)
        return redirect(f"/budget?period=month&month={month}&undo={token}", f"Updated {len(selected)} categories.")
    # Store the exact affected rows so the immediate result can be undone.
    before = c.budgets.snapshot_rows(selected)
    try:
        with settled_save(request, c):
            if action == "percentage":
                percentage = form.get("percentage", "")
                for category_id in selected:
                    c.budgets.set_income_percentage(category_id, month, percentage)
            else:
                period = 3 if action == "average3" else 6
                c.budgets.save_month(month, {category_id: "" for category_id in selected},
                                     average_months={category_id: period for category_id in selected}, schedule=c.schedules.view())
            c.settings.set("budget_bulk_undo", json.dumps({"token": token, "month": month,
                "category_ids": selected, "rows": before}))
    except LightningError as exc:
        return redirect(f"/budget?period=month&month={month}", exc.message)
    return redirect(f"/budget?period=month&month={month}&undo={token}", f"Updated {len(selected)} categories.")


@router.post("/bulk/undo")
async def undo_bulk_budget_rule(request: Request):
    c = container(request); form = await request.form(); token = str(form.get("token", ""))
    try:
        with settled_save(request, container(request)):
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
        with settled_save(request, container(request)):
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


FILL_SOURCES = ("last_month", "average", "schedule")


@router.get("/fill")
async def budget_fill_page(request: Request):
    c = container(request)
    try:
        month = _month(request)
    except ValidationError:
        return redirect("/budget", "That month is invalid. Use YYYY-MM, for example 2026-09.")
    if month > month_of(today()):
        return redirect("/budget", f"{month} has not started yet. Choose a current or past month to fill.")
    source = request.query_params.get("source")
    tried = []
    try:
        if source:
            proposal = c.budgets.fill_proposal(month, source, schedule=c.schedules.view())
        else:
            # IV-12Q3: opened without a source (Fill this month, Give it a job), the page opens on the first source
            # that has something to offer, never on an empty "last month".
            for source in FILL_SOURCES:
                proposal = c.budgets.fill_proposal(month, source, schedule=c.schedules.view())
                if any(row.selectable for row in proposal.rows):
                    break
                tried.append(source)
            else:
                source, proposal = FILL_SOURCES[0], c.budgets.fill_proposal(month, FILL_SOURCES[0], schedule=c.schedules.view())
    except LightningError as exc:
        return render(request, "budget_fill.html", month=month, source="last_month", proposal=None,
                      error=exc.message, status_code=400)
    proposal, room_left = c.health.fit_fill(proposal)
    return render(request, "budget_fill.html", month=month, source=source, proposal=proposal, error="",
                  check=c.health.plan_check(month), room_left=room_left, other_sources=[
                      key for key in FILL_SOURCES if key != source and key not in tried])


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
        proposal = c.budgets.fill_proposal(month, source, schedule=c.schedules.view())
        allowed = {row.category_id for row in proposal.rows if row.selectable and row.category_id is not None}
        selected = {int(value) for value in form.getlist("selected") if str(value).isdigit()}
        if not selected.issubset(allowed):
            raise ValidationError("Refresh the proposal before applying these categories.", "categories")
        amounts = {category_id: str(form.get(f"amount_{category_id}", "")) for category_id in selected}
        with settled_save(request, container(request)):
            changed = c.budgets.apply_fill(month, amounts, schedule=c.schedules.view())
    except LightningError as exc:
        values = {row.category_id: str(form.get(f"amount_{row.category_id}", ""))
                  for row in proposal.rows if row.category_id is not None} if "proposal" in locals() and proposal else {}
        return render(request, "budget_fill.html", month=month, source=source, proposal=proposal if "proposal" in locals() else None,
                      values=values, error=exc.message, status_code=400)
    if not changed:
        return redirect(f"/budget?month={month}", "Those base limits are already set for this month.")
    return redirect(f"/budget?month={month}", f"Applied {counted(changed, 'budget', 'budgets')} for {month} only.")


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
        with settled_save(request, container(request)):
            changed = c.budgets.save_month(month, amounts, only_this_month=only, average_months=averages, schedule=c.schedules.view())
    except LightningError as exc:
        values = {f"b_{k}": v for k, v in amounts.items()} | {f"m_{k}": v for k, v in averages.items()}
        return _page(request, month, values=values, error=exc.message,
                     status_code=400)
    if not changed:
        return redirect(f"/budget?month={month}", "Nothing changed.")
    scope = f"for {month} only" if only else f"from {month} onward"
    return redirect(f"/budget?month={month}&open_group=all", f"Saved {counted(changed, 'budget', 'budgets')} {scope}.")


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
        with settled_save(request, container(request)):
            if amounts:
                c.budgets.save_month(month, amounts, schedule=c.schedules.view())
            else:
                group_id = int(str(form.get("group_id", "")))
                c.budgets.set_budget(group_id, month, str(form.get("broad_limit", "")), schedule=c.schedules.view())
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
        with settled_save(request, container(request)):
            changed = c.budgets.set_carryover(month, settings, schedule=c.schedules.view())
    except LightningError as exc:
        return redirect(f"/budget?month={month}", exc.message)
    return redirect(f"/budget?month={month}", f"Updated carryover for {counted(changed, 'budget line', 'budget lines')}.")


@router.post("/carryover/global")
async def update_global_carryover(request: Request):
    c = container(request)
    form = await request.form()
    month = str(form.get("month", month_of(today())))
    try:
        parse_month(month)
        enabled = form.get("enabled") == "1"
        with settled_save(request, container(request)):
            c.budgets.set_carryover(month, {category_id: enabled for category_id in c.budgets.amounts_for(month, schedule=c.schedules.view())}, schedule=c.schedules.view())
            c.settings.set("budget_carryover_global", "1" if enabled else "0")
    except LightningError as exc:
        if request.headers.get("X-Requested-With") == "fetch":
            return Response(exc.message, status_code=400, media_type="text/plain")
        return redirect(f"/budget?month={month}", exc.message)
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
        with settled_save(request, container(request)):
            message = c.health.take_raise(str(form.get("choice", "")), month)
    except LightningError as exc:
        return redirect(f"/budget?month={month}", exc.message)
    return redirect(f"/budget?month={month}", " ".join(x for x in (message, c.health.plan_note(month)) if x))


@router.get("/move")
async def move_room_popup(request: Request):
    """Move plan room to a category from one with room (Needs you, Budget's cover offer). The dialog says why from the
    evidence itself, never from the link: over plan two months running, ahead of pace, or over plan this month (#626)."""
    c = container(request)
    query = request.query_params
    month = str(query.get("month", month_of(today())))
    try:
        parse_month(month)
        to, source = c.categories.get(int(query.get("to", ""))), c.categories.get(int(query.get("from", "")))
        amount = to_decimal(str(query.get("amount", "")), "amount")
    except (LightningError, ValueError):
        return redirect(f"/budget?month={month}", "Choose two categories and an amount.")
    plans = c.budgets.amounts_for(month, loans=False, schedule=c.schedules.view())
    to_plan, from_plan = plans.get(to.id, (None,))[0], plans.get(source.id, (None,))[0]
    if to_plan is None or from_plan is None:
        return redirect(f"/budget?month={month}", "Both categories need a plan of their own this month.")
    return render(request, "budget_move.html", month=month, to=to, source=source, amount=amount,
                  to_plan=to_plan, from_plan=from_plan, reason=_move_reason(c, month, to.id))


def _move_reason(c, month: str, category_id: int) -> str:
    """Why the category needs room, from the strongest evidence that holds now: 'twice', 'pace', 'over' or ''."""
    schedule = c.schedules.view()
    if any(row["category_id"] == category_id for row in c.budgets.over_twice(month, schedule=schedule)):
        return "twice"
    if any(row["category_id"] == category_id for row in c.budgets.running_out(month, today(), schedule=schedule)):
        return "pace"
    lines = (line for section in c.budgets.month_view(month, schedule=schedule).sections for line in section.lines)
    if any(line.category_id == category_id and line.remaining is not None and line.remaining < 0 for line in lines):
        return "over"
    return ""


@router.post("/move")
async def move_room(request: Request):
    c = container(request)
    form = await request.form()
    month = str(form.get("month", month_of(today())))
    try:
        parse_month(month)
        to_id, from_id = int(str(form.get("to", ""))), int(str(form.get("from", "")))
        with settled_save(request, container(request)):
            c.budgets.move_room(month, to_id, from_id, str(form.get("amount", "")), schedule=c.schedules.view())
    except ValueError:
        return redirect(f"/budget?month={month}", "Choose two categories.")
    except LightningError as exc:
        return redirect(f"/budget?month={month}", exc.message)
    names = c.categories.get(to_id).name, c.categories.get(from_id).name
    return redirect(f"/budget?month={month}", f"Moved plan from {names[1]} to {names[0]} from {month} on.")
