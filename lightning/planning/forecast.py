"""Cash forecast: free cash today, carried forward month by month.

An estimate. It reads the plan, the budget and reserves and never changes net worth or free cash.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from lightning.core.dates import fmt_date, month_of, parse_date, parse_month, today
from lightning.core.figures import label
from lightning.core.money import ZERO, from_e6
from lightning.deposits.domain import DepositEvent

from .domain import CashForecast, EverydayBudget, ForecastMonth, Payment, PaymentStatus, PlanKind
from .dated_cash import dated_cash_forecast

HORIZON_MONTHS = 3


def _months(start: date, count: int) -> list[str]:
    index = start.year * 12 + start.month - 1
    return [f"{(index + i) // 12}-{(index + i) % 12 + 1:02d}" for i in range(count)]


def _due_circle_events(service, day: date) -> list[DepositEvent]:
    """Cash still needed today, without guessing when an overdue payout arrives."""
    gameya = getattr(service, "gameya", None)
    if gameya is None:
        return []
    result = []
    for circle, terms in gameya.circles():
        progress = gameya.progress(circle.id, day)
        if progress.due_amount:
            result.append(DepositEvent(fmt_date(day), terms.funding_account_id, -progress.due_amount,
                                       "INSTALLMENT", circle.id, source="GAMEYA"))
    return result


def _deposit_cash_events(service, as_of: date, end: date):
    """Return projected CD events, replacing maturity projections already posted as transfers."""
    if service is None:
        return []
    events = service.future_events(as_of, end)
    db = getattr(service, "db", None)
    if db is None:
        return events
    replaced: set[tuple[int, int, str]] = set()
    actual = {}
    for event in events:
        if event.kind not in ("PRINCIPAL", "MATURITY"):
            continue
        destination_id = getattr(event, "destination_account_id", getattr(event, "account_id", None))
        key = (event.deposit_account_id, destination_id, event.date)
        if key in actual:
            continue
        rows = db.all(
            "SELECT dst.quantity_e6 FROM transactions t "
            "JOIN ledger_entries src ON src.transaction_id=t.id "
            "JOIN ledger_entries dst ON dst.transaction_id=t.id "
            "WHERE t.status='POSTED' AND t.type='TRF' AND t.date=? "
            "AND src.account_id=? AND src.effect='INTERNAL' "
            "AND dst.account_id=? AND dst.effect='INTERNAL'",
            (event.date, event.deposit_account_id, destination_id),
        )
        actual[key] = sum((abs(int(row["quantity_e6"])) for row in rows), 0)
        if actual[key]:
            replaced.add(key)
    if not replaced:
        return events
    adjusted = [event for event in events if (
        event.deposit_account_id,
        getattr(event, "destination_account_id", getattr(event, "account_id", None)),
        event.date,
    ) not in replaced]
    for deposit_id, destination_id, event_date in replaced:
        amount_e6 = actual[(deposit_id, destination_id, event_date)]
        adjusted.append(type("RecordedDepositEvent", (), {
            "date": event_date, "amount": from_e6(amount_e6),
            "deposit_account_id": deposit_id, "destination_account_id": destination_id,
        })())
    return adjusted


def emergency_fund(reserves, budgets, month: str):
    """The emergency fund the plan check and the forecast share: what Reserves sets aside, in months of the
    chosen average. Read straight from Reserves: building a whole position here doubled the budget page's queries."""
    reserve = next((row for row in reserves.list_active() if row["kind"] == "EMERGENCY"), None)
    return budgets.emergency_fund(month, reserve["effective_allocated"] if reserve else None)


class CashForecaster:
    def __init__(self, planning, reporting, reserves, budgets, categories, position, deposits=None):
        self.planning = planning
        self.position = position
        self.reporting = reporting
        self.reserves = reserves
        self.budgets = budgets
        self.categories = categories
        self.deposits = deposits
        self.savings_rate = lambda: ZERO  # the Savings rate limit (Financial health); bootstrap wires it

    # -------------------------------------------------------------- inputs
    def average_income(self, as_of: date) -> tuple[Decimal | None, int]:
        """Average monthly income: the same figure the budget uses (BudgetService.income_average)."""
        average = self.budgets.income_average(month_of(as_of))
        return average.amount, average.months_counted

    def free_cash(self, as_of: date) -> Decimal:
        """Free cash from the position: Cash you own − Reserves − Bills due."""
        position = self.position.at(as_of)
        if position.free_cash is not None:
            return position.free_cash
        return position.cash_you_own - self.reserves.cash_summary(ZERO)["allocated"] - position.bills_due

    def _budget(self, month: str, current: bool) -> tuple[Decimal, set[int]]:
        """Budget still to spend in the month, and the categories the plan covers.

        It is the Budget screen's own plan (BudgetService.plan_summary): limits plus background
        estimates, so the forecast and the Budget tab show one Left in plan (audit 2026-10-05 #7)."""
        view = self.budgets.month_view(month)
        summary = self.budgets.plan_summary(month)
        covered = {line.category_id for section in view.sections for line in section.lines
                   if line.budget is not None or line.covered}
        covered |= {estimate["category_id"] for estimate in summary["estimates"]}
        room = summary["left"] if current else summary["planned"]
        return max(room, ZERO), covered

    def _goal_need(self, month: str, as_of: date) -> Decimal:
        """What dated reserve goals still need set aside, spread over the months left."""
        return sum((row["amount"] for row in self.goal_needs(month, as_of)), ZERO)

    def goal_needs(self, month: str, as_of: date | None = None) -> list[dict]:
        """Informational monthly saving needs for dated project reserves."""
        day = as_of or today()
        month_start, _ = parse_month(month)
        result = []
        for reserve in self.reserves.list_active():
            if reserve["kind"] == "EMERGENCY" or not reserve.get("due_date"):
                continue
            due = date.fromisoformat(reserve["due_date"])
            if due < month_start:
                continue
            # Everything set aside so far counts, including what the goal has already paid for: a goal
            # funded in full and partly spent needs nothing more (audit 2026-10-05 #8).
            missing = max(reserve["target"] - reserve["allocated"], ZERO)
            months_left = max((due.year - day.year) * 12 + due.month - day.month + 1, 1)
            amount = (missing / months_left).quantize(Decimal("0.01"))
            if amount:
                result.append({"id": reserve["id"], "name": reserve["name"], "amount": amount,
                               "due_date": reserve["due_date"], "missing": missing})
        return result

    # -------------------------------------------------------------- everyday
    def everyday(self, month: str, as_of: date | None = None) -> EverydayBudget:
        """The month's plan as bills and everyday money (owner 2026-10-19). Bills to pay are the bills and loan
        payments in planned categories not paid yet, counted as the forecast counts them for this month, so
        Everyday left here is Budget until payday's own figure; a month already over has none left to pay."""
        day = as_of or today()
        first, last = parse_month(month)
        current = first <= day <= last
        counted = day if current else last if day > last else None
        summary = self.budgets.plan_summary(month)
        _, covered = self._budget(month, current)
        payments = [p for p in self.planning.all_payments(last, day)
                    if not p.item.is_income and p.item.category_id in covered and p.status != PaymentStatus.SKIPPED
                    and (p.due_date[:7] == month or (current and p.outstanding and p.due_date < fmt_date(first)))]
        unpaid: dict[int, Decimal] = {}
        if current:
            for p in payments:
                if p.outstanding:
                    unpaid[p.item.category_id] = unpaid.get(p.item.category_id, ZERO) + self.planning.amount_in_base(p, p.still_owed, day)
        bills_to_pay = sum(unpaid.values(), ZERO)
        everyday_left = max(summary["left"] - bills_to_pay, ZERO) if current else summary["left"]
        scheduled = sum((amount for cid, amount in self.budgets.scheduled_payments(month).items() if cid in covered), ZERO)
        by_day = self._everyday_by_day(first, counted) if counted else []
        before_last = first - timedelta(days=1)
        last_month = self._everyday_by_day(before_last.replace(day=1), before_last)
        view = self.budgets.month_view(month)
        room = {line.category_id: line.remaining - unpaid.get(line.category_id, ZERO)
                for section in view.sections for line in section.lines
                if line.depth > 1 and line.remaining is not None}
        return EverydayBudget(month, summary["planned"], summary["spent"], summary["left"], bills_to_pay, everyday_left,
                              summary["planned"] - scheduled, by_day[-1] if by_day else ZERO,
                              counted.day if counted else 0, last.day, current, by_day, last_month, room, payments)

    def _everyday_by_day(self, start: date, end: date) -> list[Decimal]:
        """Everyday spending added up day by day from ``start`` to ``end``: the budget's spending (one-off and
        investment categories left out) less bill and loan payments. A payment is a bill's when it is marked paid
        against one, or when it pays a bill's payee in that bill's category (a bill paid before it was scheduled,
        or never marked paid)."""
        linked = self.planning.linked_transaction_ids()
        payees = {(item.counterparty_id, item.category_id) for item in self.planning.items()
                  if not item.is_income and item.counterparty_id and item.category_id}
        left_out = self.budgets.one_off_ids() | self.budgets._investment_ids()
        daily: dict[str, Decimal] = {}
        for line in self.reporting.spending_lines(start, end):
            if (line["transaction_id"] in linked or line["category_id"] in left_out
                    or (line.get("counterparty_id"), line["category_id"]) in payees):
                continue
            daily[line["date"]] = daily.get(line["date"], ZERO) + line["value"]
        out, total, cursor = [], ZERO, start
        while cursor <= end:
            total += daily.get(fmt_date(cursor), ZERO)
            out.append(total)
            cursor += timedelta(days=1)
        return out

    # -------------------------------------------------------------- forecast
    def forecast(self, as_of: date | None = None, months: int = HORIZON_MONTHS) -> CashForecast:
        day = as_of or today()
        free = self.free_cash(day)
        average, average_months = self.average_income(day)
        month_keys = _months(day, months)
        horizon_end = parse_month(month_keys[-1])[1]
        all_events = _deposit_cash_events(self.deposits, day, horizon_end)
        receipts = getattr(self, "deposit_receipts", None)
        if receipts is not None:
            all_events = receipts.adjust_events(all_events, day)
        deposit_events = [e for e in all_events if getattr(e, "source", "CD") != "GAMEYA"]
        circle_events = [e for e in all_events if getattr(e, "source", "CD") == "GAMEYA"]
        # A payment whose money already moved early (salary 12 days before payday) is in free cash: counting
        # it as upcoming too would add it twice (7K).
        early = {(e["item"].id, e["payment"].due_date) for e in self.planning.early_payments(day)}
        upcoming = [p for p in self.planning.all_payments(horizon_end, day)
                    if p.outstanding and p.due_date > fmt_date(day) and (p.item.id, p.due_date) not in early]
        # Payments already due: bills are in free cash already (Bills due); income not yet received
        # is still expected this month.
        due = [p for p in self.planning.all_payments(day, day) if p.outstanding and p.due_date <= fmt_date(day)]
        has_scheduled_income = any(i.kind == PlanKind.INCOME for i in self.planning.items((PlanKind.INCOME,)))

        rows, opening = [], free
        # The emergency fund's top-up, as the plan check counts it: what each month must leave for it until full.
        fund = emergency_fund(self.reserves, self.budgets, month_keys[0])
        emergency_gap = max((fund.target or ZERO) - (fund.set_aside or ZERO), ZERO)
        # Saving needed, as the plan check counts it: the savings target, or goals and the top-up when larger.
        target = (average * self.savings_rate() / 100).quantize(Decimal("0.01")) if average else ZERO
        for index, key in enumerate(month_keys):
            current = index == 0
            in_month = [p for p in upcoming if p.due_date[:7] == key]
            due_now = due if current else []
            # Only this month's unreceived income is still expected now. Older paydays that were never
            # marked received are not added on top (audit 2026-10-05 #3: five months of salary at once).
            income = sum((self.planning.amount_in_base(p, p.still_owed, day) for p in in_month + [p for p in due_now if p.due_date[:7] == key]
                          if p.item.is_income), ZERO)
            estimated = False
            if not has_scheduled_income and average:
                received = (self.reporting.cash_flow(parse_month(key)[0], day).inflows if current else ZERO)
                income, estimated = max(average - received, ZERO), True
            outgoing = [p for p in in_month if not p.item.is_income]
            budget_room, covered = self._budget(key, current)
            covered_bills = sum((self.planning.amount_in_base(p, p.still_owed, day) for p in outgoing if p.item.category_id in covered), ZERO)
            other_bills = sum((self.planning.amount_in_base(p, p.still_owed, day) for p in outgoing if p.item.category_id not in covered), ZERO)
            # A bill in a budgeted category is part of that budget, not on top of it. That holds for
            # bills already due too: they come off free cash, so they come off the budget room here.
            due_covered = sum((self.planning.amount_in_base(p, p.still_owed, day) for p in due_now if not p.item.is_income
                               and p.item.category_id in covered), ZERO)
            budget_spending = max(budget_room - covered_bills - due_covered, ZERO)
            commitments = covered_bills + other_bills
            goals = self._goal_need(key, day)
            emergency = min(fund.top_up, emergency_gap)
            emergency_gap -= emergency
            rest = max(target - goals - emergency, ZERO)
            deposit_cash = sum((event.amount for event in deposit_events if event.date[:7] == key), ZERO)
            circle_in = sum((e.amount for e in circle_events if e.date[:7] == key and e.amount > ZERO), ZERO)
            circle_out = -sum((e.amount for e in circle_events if e.date[:7] == key and e.amount < ZERO), ZERO)
            closing = (opening + income + deposit_cash + circle_in - circle_out - commitments - budget_spending
                       - goals - emergency - rest)
            rows.append(ForecastMonth(key, opening, income, estimated, commitments, budget_spending, goals, closing,
                                      deposit_cash, emergency, rest, circle_in, circle_out))
            opening = closing

        next_income = next((p for p in upcoming if p.item.is_income), None)
        if next_income:
            next_date, next_estimated = next_income.due_date, False
        elif average:
            next_date, next_estimated = fmt_date(parse_month(month_keys[1])[0]) if len(month_keys) > 1 else None, True
        else:
            next_date, next_estimated = None, False
        before = [p for p in upcoming if not p.item.is_income and (next_date is None or p.due_date < next_date)]
        instalments = -sum((e.amount for e in circle_events if e.kind == "INSTALLMENT"
                            and (next_date is None or e.date < next_date)), ZERO)
        safe, parts = self._safe_to_spend(free, before, next_date, day, rows, instalments)
        return CashForecast(fmt_date(day), free, average, average_months, next_date, next_estimated,
                            safe, parts, rows, [p for p in upcoming if p.due_date <= next_date] if next_date else upcoming[:10],
                            before, dated_cash_forecast(self.reporting, due + upcoming,
                                                      all_events + _due_circle_events(self.deposits, day),
                                                      day, horizon_end))

    def _safe_to_spend(self, free: Decimal, before: list[Payment], until: str | None, day: date,
                       rows: list[ForecastMonth], instalments: Decimal = ZERO) -> tuple[Decimal, list[tuple[str, Decimal]]]:
        """Free cash less what is already promised before the next income.

        Budget, goal and savings needs count for every month until the next income, not just this one: between
        jobs, next month's spending still comes out of today's cash. The month the income lands in
        counts for the days before it."""
        bills = sum((self.planning.amount_in_base(p, p.still_owed, day) for p in before), ZERO)
        spending = goals = emergency = rest = ZERO
        for index, row in enumerate(rows):
            share = Decimal(1)
            if index:
                if until is None:
                    break
                first_day, last_day = parse_month(row.month)
                pay_day = parse_date(until)
                if pay_day <= first_day:
                    break
                if pay_day <= last_day:
                    share = Decimal((pay_day - first_day).days) / Decimal((last_day - first_day).days + 1)
            spending += row.budget_spending * share
            goals += row.goal_saving * share
            emergency += row.emergency_saving * share
            rest += row.target_saving * share
        spending, goals = spending.quantize(Decimal("0.01")), goals.quantize(Decimal("0.01"))
        emergency, rest = emergency.quantize(Decimal("0.01")), rest.quantize(Decimal("0.01"))
        bills_part = (label("payments_before_next_income"), -bills)
        circle_part = ("Gam'eya instalments before next income", -instalments)
        parts = [(label("free_cash"), free), bills_part, circle_part,
                 (label("left_in_plan_after_bills"), -spending), (label("saving_for_goals"), -goals),
                 (label("emergency_top_up"), -emergency), (label("savings_target_rest"), -rest)]
        return (free - bills - instalments - spending - goals - emergency - rest,
                [(name, value) for name, value in parts if value or name == label("free_cash")])
