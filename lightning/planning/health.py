"""Named financial-health figures and profile-owned comparison limits."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal

from lightning.core.dates import fmt_date, month_of, parse_month, today
from lightning.core.errors import ValidationError
from lightning.core.money import ZERO, check_places, fmt, to_decimal
from lightning.database.settings import SettingsStore

from lightning.budgeting.domain import INCOME_FROM_RECURRING

from .domain import PlanKind, per_year
from .forecast import emergency_fund


@dataclass(frozen=True)
class Ratio:
    key: str                 # its figure registry key
    part: Decimal            # what is divided: What you owe, payments a month
    whole: Decimal | None    # what it is divided by: Net worth, Cash you own, Average monthly income

    @property
    def percent(self) -> Decimal | None:
        return self.part / self.whole * 100 if self.whole is not None and self.whole > 0 else None


@dataclass(frozen=True)
class Health:
    debt_to_net_worth: Ratio
    debt_to_cash: Ratio
    loan_payments_to_income: Ratio
    fixed_costs_to_income: Ratio
    bills_a_month: Decimal       # bills and subscriptions, a month
    loans_a_month: Decimal       # loan payments still to make, a month


@dataclass(frozen=True)
class HealthMonth:
    month: str
    savings_rate: Decimal | None
    net_worth: Decimal | None
    gap: str = ""                # said instead of a rate below −100% (CashFlow.rate_says_nothing)


@dataclass(frozen=True)
class HealthFigure:
    key: str
    value: Decimal | None
    unit: str
    period: str
    limit: Decimal | None
    direction: str
    status: str | None
    support: tuple[tuple[str, Decimal | None], ...]
    href: str
    gap: str = ""                # said instead of a rate below −100% (CashFlow.rate_says_nothing)
    alert: Decimal | None = None  # where "Needs you" starts; `limit` is where "Good" starts
    band: str | None = None      # "good" | "watch" | "alert" (HealthService.band); None without a limit or a value


@dataclass(frozen=True)
class PlanCheck:
    """A month's spending plan against the savings target and dated goals (owner request 2026-10-05:
    a budget must leave the savings rate you set). Plan only: it moves no money."""
    month: str
    income: Decimal | None        # Average monthly income for the month
    planned: Decimal | None       # Planned: the month's plan as every screen shows it; None without a plan
    target_percent: Decimal       # the Savings rate limit in Financial health
    goals: Decimal                # Saving for goals: what dated goals need this month
    emergency: Decimal = ZERO     # Emergency fund top-up: the fund's gap to six months over two years

    @property
    def needs(self) -> Decimal:
        """Saving for goals + Emergency fund top-up."""
        return self.goals + self.emergency

    @property
    def savings_target(self) -> Decimal | None:
        """Average monthly income × Savings rate limit."""
        return None if self.income is None else (self.income * self.target_percent / 100).quantize(Decimal("0.01"))

    @property
    def to_save(self) -> Decimal | None:
        """What the plan must leave: the savings target, or goals and the emergency top-up when they need more."""
        return None if self.savings_target is None else max(self.savings_target, self.needs)

    @property
    def spending_room(self) -> Decimal | None:
        """The most the month's plan can be and still leave what you want to save."""
        return None if self.to_save is None else self.income - self.to_save

    @property
    def plan_saves(self) -> Decimal | None:
        """Average monthly income − Planned."""
        return None if self.income is None or self.planned is None else self.income - self.planned

    @property
    def planned_savings_rate(self) -> Decimal | None:
        return (self.plan_saves / self.income * 100
                if self.plan_saves is not None and self.income and self.income > 0 else None)

    @property
    def over_by(self) -> Decimal:
        """How much to take out of the plan to leave what you want to save; zero when it already does."""
        if self.plan_saves is None or self.to_save is None:
            return ZERO
        return max(self.to_save - self.plan_saves, ZERO)

    @property
    def short_for(self) -> str:
        """Which need the plan misses: goals and the emergency fund when they need more than the target, else the target."""
        return "goals" if self.needs > (self.savings_target or ZERO) else "target"

    @property
    def needs_label(self) -> str:
        """What "goals" means in a sentence: dated goals, the emergency fund, or both."""
        if self.goals and self.emergency:
            return "your goals and emergency fund need"
        return "your emergency fund needs" if self.emergency else "your goals need"


# Three bands per figure (U15): Good from `LIMIT_DEFAULTS` (the old single limit), Needs you from `ALERT_DEFAULTS`,
# Watch in between. Loan payments: 36% of income is the usual ceiling lenders use. Debt to cash has no
# default limit, so it has no band until the user sets one.
LIMIT_DEFAULTS: dict[str, Decimal | None] = {
    "emergency_fund": Decimal("6"),
    "savings_rate": Decimal("20"),
    "fixed_costs_to_income": Decimal("50"),
    "loan_payments_to_income": Decimal("20"),
    "debt_to_cash": None,
    "debt_to_net_worth": Decimal("30"),
}
ALERT_DEFAULTS: dict[str, Decimal | None] = {
    "emergency_fund": Decimal("3"),
    "savings_rate": Decimal("10"),
    "fixed_costs_to_income": Decimal("70"),
    "loan_payments_to_income": Decimal("36"),
    "debt_to_cash": None,
    "debt_to_net_worth": Decimal("70"),
}
LIMIT_DIRECTIONS = {
    "emergency_fund": "minimum",
    "savings_rate": "minimum",
    "fixed_costs_to_income": "maximum",
    "loan_payments_to_income": "maximum",
    "debt_to_cash": "maximum",
    "debt_to_net_worth": "maximum",
}
LIMIT_LABELS = {
    "emergency_fund": "Emergency fund",
    "savings_rate": "Savings rate",
    "fixed_costs_to_income": "Fixed costs to income",
    "loan_payments_to_income": "Loan payments to income",
    "debt_to_cash": "Debt to cash",
    "debt_to_net_worth": "Debt to net worth",
}
LIMIT_PREFIX = "financial_health_limit_"      # the old single limit: read as the Good boundary until `GOOD_PREFIX` is saved
GOOD_PREFIX = "financial_health_good_"
ALERT_PREFIX = "financial_health_alert_"
EMERGENCY_FUND_MONTHS = Decimal("6")
RAISE_SHARE = Decimal("1.05")  # recurring income at least 5% above the average is a raise worth planning with
RAISE_DECLINED = "income_raise_declined"         # the recurring amount whose offer was declined

NO_LIMIT_SUPPORTED = frozenset({"debt_to_cash", "debt_to_net_worth"})
GOOD_LOCKED = frozenset({"emergency_fund"})  # its Good boundary is the six-month target on the Reserves page


def _gap(flow) -> str:
    """The Overview's words for a month whose money out is more than twice its money in."""
    return f"{fmt(-flow.net, 0)} more went out than the {fmt(flow.inflows, 0)} that came in"


def compare_to_limit(value: Decimal | None, limit: Decimal | None, direction: str) -> str | None:
    """Compare an available figure to a set limit; equality is within the limit."""
    if value is None or limit is None:
        return None
    within = value >= limit if direction == "minimum" else value <= limit
    return "within your limit" if within else "outside your limit"


def band_of(value: Decimal | None, good: Decimal | None, alert: Decimal | None, direction: str) -> str | None:
    """Good from `good` (equality is good), Needs you past `alert`, Watch between. No band without both a value and a limit."""
    if value is None or good is None:
        return None
    if (value >= good) if direction == "minimum" else (value <= good):
        return "good"
    if alert is not None and ((value < alert) if direction == "minimum" else (value > alert)):
        return "alert"
    return "watch"


class HealthService:
    def __init__(self, planning, position, budgets, settings: SettingsStore | None = None):
        self.planning = planning
        self.position = position
        self.budgets = budgets
        self.reporting = position.reporting
        self.reserves = position.reserves
        self.settings = settings or SettingsStore(budgets.db)

    def loans_a_month(self, day: date) -> Decimal:
        """Loan payments a month, counting only loans with payments still to make."""
        return sum((self.planning.amount_in_base(item, per_year(item) / 12, day) for item in self.planning.items((PlanKind.LOAN,))
                    if self.planning.loan_progress(item, day)["still_to_pay"] > 0), ZERO)

    def bills_a_month(self, day: date | None = None) -> Decimal:
        """Bills and subscriptions a month: what Cash planning › Recurring totals."""
        return sum((self.planning.amount_in_base(item, per_year(item) / 12, day or today()) for item in self.planning.items((PlanKind.BILL, PlanKind.SUBSCRIPTION))), ZERO)

    def at(self, day: date) -> Health:
        position = self.position.at(day, match_payments=False)
        owe = position.what_you_owe
        income = self.budgets.income_average(day.strftime("%Y-%m")).amount
        loans, bills = self.loans_a_month(day), self.bills_a_month(day)
        return Health(
            debt_to_net_worth=Ratio("debt_to_net_worth", owe, position.net_worth),
            debt_to_cash=Ratio("debt_to_cash", owe, position.cash_you_own),
            loan_payments_to_income=Ratio("loan_payments_to_income", loans, income),
            fixed_costs_to_income=Ratio("fixed_costs_to_income", bills + loans, income),
            bills_a_month=bills, loans_a_month=loans)

    def _stored(self, keys: tuple[str, ...], default: Decimal | None) -> Decimal | None:
        """The first saved setting among ``keys`` (``none`` means no limit); the default when none is saved."""
        for name in keys:
            saved = self.settings.get(name)
            if not saved:
                continue
            if saved.casefold() == "none":
                return None
            try:
                return to_decimal(saved, "limit")
            except ValidationError:
                return default
        return default

    def limit_values(self) -> dict[str, Decimal | None]:
        """Where Good starts, per figure: the saved Good boundary, else the old single limit, else the default."""
        return {key: (default if key in GOOD_LOCKED else
                      self._stored((GOOD_PREFIX + key, LIMIT_PREFIX + key), default))
                for key, default in LIMIT_DEFAULTS.items()}

    def alert_values(self) -> dict[str, Decimal | None]:
        """Where Needs you starts, per figure."""
        good = self.limit_values()
        return {key: (None if good[key] is None else self._stored((ALERT_PREFIX + key,), default))
                for key, default in ALERT_DEFAULTS.items()}

    def band(self, key: str, value: Decimal | None) -> str | None:
        """"good", "watch" or "alert" for a figure's value; None without a value or a limit."""
        good, alert = self.limit_values().get(key), self.alert_values().get(key)
        return band_of(value, good, alert, LIMIT_DIRECTIONS[key])

    def limit_settings(self) -> list[dict]:
        values, alerts = self.limit_values(), self.alert_values()
        return [{"key": key, "label": LIMIT_LABELS[key], "direction": LIMIT_DIRECTIONS[key],
                 "value": values[key], "alert": alerts[key], "default": LIMIT_DEFAULTS[key],
                 "alert_default": ALERT_DEFAULTS[key], "no_limit": values[key] is None,
                 "good_locked": key in GOOD_LOCKED,
                 "supports_no_limit": key in NO_LIMIT_SUPPORTED, "unit": "months" if key == "emergency_fund" else "%"}
                for key in LIMIT_DEFAULTS if key not in GOOD_LOCKED]  # Emergency fund's bands are fixed: 6 and 3 months

    def set_limit(self, key: str, raw: str, no_limit: bool = False, alert_raw: str | None = None) -> Decimal | None:
        """Save where Good starts (and, when given, where Needs you starts). The two must lie on the right sides:
        for a figure you want high, Needs you is below Good; for one you want low, above."""
        if key not in LIMIT_DEFAULTS or key in GOOD_LOCKED:
            raise ValidationError("Choose a financial-health limit.", "limit")
        if no_limit:
            if key not in NO_LIMIT_SUPPORTED:
                raise ValidationError("This figure needs a personal limit.", "limit")
            good = alert = None
        else:
            good = LIMIT_DEFAULTS[key] if key in GOOD_LOCKED else check_places(to_decimal(raw, "limit"), 1, "limit")
            if good < ZERO:
                raise ValidationError("A financial-health limit cannot be negative.", "limit")
            if alert_raw is None or not str(alert_raw).strip():
                alert = self.alert_values()[key] if alert_raw is None else ALERT_DEFAULTS[key]
                if alert is not None and ((alert >= good) if LIMIT_DIRECTIONS[key] == "minimum" else (alert <= good)):
                    alert = None
            else:
                alert = check_places(to_decimal(alert_raw, "limit"), 1, "limit")
                if alert < ZERO:
                    raise ValidationError("A financial-health limit cannot be negative.", "limit")
            if alert is not None and ((alert >= good) if LIMIT_DIRECTIONS[key] == "minimum" else (alert <= good)):
                raise ValidationError("Needs you must start " + ("below" if LIMIT_DIRECTIONS[key] == "minimum" else "above")
                                      + " Good.", "limit")
        self.settings.set(GOOD_PREFIX + key, "none" if good is None else format(good, "f"))
        self.settings.set(ALERT_PREFIX + key, "none" if alert is None else format(alert, "f"))
        return good

    def restore_limit(self, key: str) -> Decimal | None:
        if key not in LIMIT_DEFAULTS:
            raise ValidationError("Choose a financial-health limit.", "limit")
        for name, table in ((GOOD_PREFIX, LIMIT_DEFAULTS), (ALERT_PREFIX, ALERT_DEFAULTS)):
            value = table[key]
            self.settings.set(name + key, "none" if value is None else format(value, "f"))
        self.settings.set(LIMIT_PREFIX + key, "none" if LIMIT_DEFAULTS[key] is None else format(LIMIT_DEFAULTS[key], "f"))
        return LIMIT_DEFAULTS[key]

    def plan_check(self, month: str) -> PlanCheck:
        """The month's plan against the Savings rate limit and Saving for goals. The budget, Needs you
        and Financial health all read this one check."""
        planned = self.budgets.plan_summary(month)["planned"] if self.budgets.has_plan(month) else None
        goals = sum((row["amount"] for row in self.budgets.reserve_goal_needs(month)), ZERO)
        fund = emergency_fund(self.reserves, self.budgets, month)
        return PlanCheck(month, self.budgets.income_average(month).amount, planned,
                         self.limit_values()["savings_rate"], goals, fund.top_up)

    def commitments_note(self, kind: str, day: date | None = None) -> str:
        """After a bill, subscription or loan is saved: where Fixed costs to income (and, for a loan, Loan
        payments to income) now stand against your limits. Empty for income or without average income."""
        if kind == PlanKind.INCOME.value:
            return ""
        health, limits = self.at(day or today()), self.limit_values()
        keys = ("fixed_costs_to_income",) + (("loan_payments_to_income",) if kind == PlanKind.LOAN.value else ())
        parts = []
        for key in keys:
            percent, limit = getattr(health, key).percent, limits[key]
            if percent is None:
                continue
            text = f"{LIMIT_LABELS[key]} is now {percent:.0f}%"
            if compare_to_limit(percent, limit, "maximum") == "outside your limit":
                text += f", above your {limit:.0f}% limit"
            elif limit is not None:
                text += f", within your {limit:.0f}% limit"
            parts.append(text)
        return "; ".join(parts) + "." if parts else ""

    def plan_note(self, month: str | None = None) -> str:
        """After the savings target, a goal or the emergency fund changes: what that does to this month's
        Most you can plan, whether the plan still fits, and whether bills and loans alone already pass it.
        Empty without average income."""
        month = month or month_of(today())
        check = self.plan_check(month)
        room = check.spending_room
        if room is None:
            return ""
        if room <= 0:
            return (f"Saving needed is now {fmt(check.to_save, 0)} a month, all of your income: "
                    "give a goal a later date or a smaller target.")
        text = f"Most you can plan this month is now {fmt(room, 0)}"
        if check.planned is not None:
            text += f"; this month's plan is {fmt(check.over_by, 0)} over it" if check.over_by else "; this month's plan fits"
        fixed = self.bills_a_month(parse_month(month)[0]) + self.loans_a_month(parse_month(month)[0])
        if fixed > room:
            text += f". Bills and loan payments alone come to {fmt(fixed, 0)} a month, more than that"
        return text + "."

    def goal_reach(self, month: str | None = None) -> list[dict]:
        """Dated goals the month's plan cannot reach by their date. What the plan leaves to save (or, without
        a plan, income less bills and loan payments) goes to goals first, earliest date first; a goal that
        gets less than it needs says when it is reached at that pace (None: the plan leaves nothing for it)."""
        month = month or month_of(today())
        check = self.plan_check(month)
        if check.income is None:
            return []
        start = parse_month(month)[0]
        left = (check.plan_saves if check.plan_saves is not None
                else check.income - self.bills_a_month(start) - self.loans_a_month(start))
        late = []
        for goal in sorted(self.budgets.reserve_goal_needs(month), key=lambda row: row["due_date"]):
            share = max(min(goal["amount"], left), ZERO)
            left -= share
            if share >= goal["amount"]:
                continue
            reached = None
            if share > 0:
                months = math.ceil(goal["missing"] / share)  # whole months, rounded up
                index = start.year * 12 + start.month - 1 + months - 1
                reached = f"{index // 12}-{index % 12 + 1:02d}"
            late.append({"id": goal["id"], "name": goal["name"], "due_date": goal["due_date"], "need": goal["amount"],
                         "can": share, "reached": reached, "missing": goal["missing"]})
        return late

    def raise_offer(self, month: str | None = None) -> dict | None:
        """Monthly recurring income (not the yearly or bonus lumps) above Average monthly income (a raise not in
        the average yet): what planning with it would give, and the savings target that keeps today's plan and saves the difference. None when the
        average is set by hand, already is the recurring income, or the offer was declined at this amount."""
        month = month or month_of(today())
        average = self.budgets.income_average(month)
        recurring = self.planning.income_a_month(regular_only=True)  # a yearly bonus is not a raise
        if average.manual or average.scheduled or not average.amount or recurring is None:
            return None
        if recurring < average.amount * RAISE_SHARE or self.settings.get(RAISE_DECLINED) == format(recurring, "f"):
            return None
        check = self.plan_check(month)
        rate = check.target_percent
        keep = ((average.amount * rate / 100 + recurring - average.amount) / recurring * 100).quantize(Decimal("0.1"))
        return {"month": month, "recurring": recurring, "average": average.amount, "raise": recurring - average.amount,
                "room": recurring - max(recurring * rate / 100, check.needs), "rate": rate, "keep_rate": keep}

    def take_raise(self, choice: str, month: str | None = None) -> str:
        """Act on the raise offer: plan with the recurring income, save the difference, or keep the average."""
        offer = self.raise_offer(month)
        if offer is None:
            raise ValidationError("There is no new income to plan with.", "choice")
        if choice == "plan":
            self.settings.set(INCOME_FROM_RECURRING, "1")
            return f"The plan now counts your recurring income, {fmt(offer['recurring'], 0)} a month."
        if choice == "save":
            self.set_limit("savings_rate", format(offer["keep_rate"], "f"))
            return f"Savings target raised to {fmt(offer['keep_rate'], 1)}%: the plan stays and saves the difference."
        if choice == "keep":
            self.settings.set(RAISE_DECLINED, format(offer["recurring"], "f"))
            return "The plan keeps counting your average income."
        raise ValidationError("Choose what to do with the new income.", "choice")

    def short_month(self, day: date | None = None) -> dict | None:
        """The last completed month, when it saved less than the Savings rate limit (Financial health's own
        Savings rate). None without money in that month or when it met the target, and None when less than
        half the usual income came in: the pay landed in another month (paid early, or between jobs), so the
        month's rate says nothing about the plan (Mohab's January, paid on 24 December)."""
        day = day or today()
        end = parse_month(month_of(day))[0] - timedelta(days=1)
        flow = self.reporting.cash_flow(parse_month(month_of(end))[0], end)
        limit = self.limit_values()["savings_rate"]
        if flow.savings_rate is None or not flow.inflows or limit is None or flow.savings_rate >= limit:
            return None
        usual = self.budgets.income_average(month_of(end)).amount
        if usual and flow.inflows < usual / 2:
            return None
        return {"month": month_of(end), "rate": flow.savings_rate, "limit": limit,
                "short": (flow.inflows * limit / 100 - flow.net).quantize(Decimal("0.01"))}

    def fit_fill(self, proposal):
        """Fill this month stops at Most you can plan: rows stay ticked only while they fit in the room the
        plan has left; the rest are unticked with the reason, and you may still tick them yourself.
        Returns the proposal and the room left after the ticked rows (None without income)."""
        check = self.plan_check(proposal.month)
        if check.spending_room is None:
            return proposal, None
        left = check.spending_room - (check.planned or ZERO)
        rows = []
        for row in proposal.rows:
            if row.selected and row.amount is not None:
                change = row.amount - (row.current_amount or ZERO)
                if change > left:
                    reason = f"Past Most you can plan: {fmt(max(left, ZERO), 0)} of room left."
                    row = replace(row, selected=False, conflict=" ".join(x for x in (row.conflict, reason) if x))
                else:
                    left -= change
            rows.append(row)
        return replace(proposal, rows=tuple(rows)), left

    def emergency_fund(self, day: date):
        """Use the Reserves page's single target and selected income-or-spending basis."""
        position = self.position.at(day, match_payments=False)
        reserve = next((row for row in (position.reserve_rows or ()) if row["kind"] == "EMERGENCY"), None)
        return self.budgets.emergency_fund(month_of(day), reserve["effective_allocated"] if reserve else None)

    def cash_months(self, day: date, fund=None) -> Decimal | None:
        """Months of the fund's own average (income or spending) that the cash you own would cover:
        Cash you own ÷ that average. Shown beside the emergency fund, which counts only its reserve."""
        fund = fund or self.emergency_fund(day)
        if not fund.monthly:
            return None
        return self.position.at(day, match_payments=False).cash_you_own / fund.monthly

    def overview(self, as_of: date | None = None) -> dict:
        """Assemble the read-only figures and six completed-month trends for the Health page."""
        day = as_of or today()
        position = self.position.at(day, match_payments=False)
        health = self.at(day)
        fund = self.emergency_fund(day)
        current_month_start, _ = parse_month(month_of(day))
        savings_end = current_month_start - timedelta(days=1)
        savings_month = month_of(savings_end)
        savings_start, _ = parse_month(savings_month)
        savings = self.reporting.cash_flow(savings_start, savings_end)
        income_average = self.budgets.income_average(month_of(day))
        check = self.plan_check(month_of(day))
        limits, alerts = self.limit_values(), self.alert_values()

        def figure(key, value, unit, period, limit, direction, support, href):
            alert_key = "savings_rate" if key == "planned_savings_rate" else key
            return HealthFigure(key, value, unit, period, limit, direction,
                                compare_to_limit(value, limit, direction), tuple(support), href,
                                alert=alerts.get(alert_key), band=band_of(value, limit, alerts.get(alert_key), direction))

        avg_label = "Average monthly income" if fund.basis == "income" else "Average monthly spending"
        emergency_status = compare_to_limit(fund.months, limits["emergency_fund"], "minimum")
        figures = (
            figure("net_worth", position.net_worth, "money", f"As of {fmt_date(day)}", None, "maximum",
                   (("What you own", position.what_you_own), ("What you owe", position.what_you_owe)), "/"),
            HealthFigure("emergency_fund", fund.months, "months", f"As of {fmt_date(day)} · months of {avg_label.lower()}",
                         limits["emergency_fund"], "minimum", emergency_status,
                         (("Reserves for emergencies", fund.set_aside), (avg_label, fund.monthly)), "/plan/reserves",
                         alert=alerts["emergency_fund"],
                         band=band_of(fund.months, limits["emergency_fund"], alerts["emergency_fund"], "minimum")),
            HealthFigure("savings_rate", None, "%", savings_month, limits["savings_rate"], "minimum",
                         "outside your limit" if limits["savings_rate"] is not None else None,
                         (("Net flow", savings.net), ("Money in", savings.inflows)), "/", _gap(savings),
                         alert=alerts["savings_rate"], band="alert" if limits["savings_rate"] is not None else None)
            if savings.rate_says_nothing else
            figure("savings_rate", savings.savings_rate, "%", savings_month, limits["savings_rate"], "minimum",
                   (("Net flow", savings.net), ("Money in", savings.inflows)), "/"),
            figure("planned_savings_rate", check.planned_savings_rate, "%", f"{month_of(day)} plan",
                   limits["savings_rate"], "minimum",
                   (("Plan leaves to save", check.plan_saves), ("Saving for goals", check.goals),
                    ("Emergency fund top-up", check.emergency),
                    ("Average monthly income", check.income)), f"/budget?month={month_of(day)}"),
            figure("debt_to_cash", health.debt_to_cash.percent, "%", fmt_date(day), limits["debt_to_cash"], "maximum",
                   (("What you owe", health.debt_to_cash.part), ("Cash you own", health.debt_to_cash.whole)), "/plan/loans"),
            figure("debt_to_net_worth", health.debt_to_net_worth.percent, "%", fmt_date(day), limits["debt_to_net_worth"], "maximum",
                   (("What you owe", health.debt_to_net_worth.part), ("Net worth", health.debt_to_net_worth.whole)), "/plan/loans"),
            figure("fixed_costs_to_income", health.fixed_costs_to_income.percent, "%", f"Monthly · {income_average.window}", limits["fixed_costs_to_income"], "maximum",
                   (("Bills and subscriptions a month", health.bills_a_month),
                    ("Loan payments a month", health.loans_a_month),
                    ("Average monthly income", health.fixed_costs_to_income.whole)), "/plan/recurring"),
            figure("loan_payments_to_income", health.loan_payments_to_income.percent, "%", f"Monthly · {income_average.window}", limits["loan_payments_to_income"], "maximum",
                   (("Loan payments a month", health.loan_payments_to_income.part),
                    ("Average monthly income", health.loan_payments_to_income.whole)), "/plan/loans"),
        )

        first_activity = self.reporting.first_activity_date()
        first_date = date.fromisoformat(first_activity) if first_activity else None
        month_cursor = savings_start
        for _ in range(5):
            month_cursor = month_cursor.replace(day=1) - timedelta(days=1)
            month_cursor = month_cursor.replace(day=1)
        trends = []
        cursor = month_cursor
        for _ in range(6):
            key = month_of(cursor)
            _, month_end = parse_month(key)
            flow = self.reporting.cash_flow(cursor, month_end)
            worth = (self.position.at(month_end, match_payments=False).net_worth
                     if first_date and month_end >= first_date else None)
            trends.append(HealthMonth(key, None if flow.rate_says_nothing else flow.savings_rate, worth,
                                      _gap(flow) if flow.rate_says_nothing else ""))
            next_month = month_end + timedelta(days=1)
            cursor = next_month
        return {"as_of": fmt_date(day), "savings_month": savings_month, "fund": fund,
                "figures": figures, "trends": tuple(trends), "emergency_months": EMERGENCY_FUND_MONTHS,
                "income_average": income_average, "cash_months": self.cash_months(day, fund)}
