"""One review inbox: every decision Lightning is waiting on, in one ordered list.

The Overview's Needs you shows it. Each item names what needs a decision, gives one line of
detail, and links to the page that settles it, with the action's name. Nothing here changes data.
Reconciliation diagnostics stay in the Integrity checks view; this lists actions a user can take.
"""
from __future__ import annotations

import json
from datetime import date

from lightning.core.dates import fmt_date, month_of
from lightning.core.money import ZERO, fmt as _fmt
from lightning.transactions.domain import TxnFilter
from lightning.workflows.market_prices import missing_prices


def fmt(value, places: int = 0, signed: bool = False) -> str:
    """Reporting text rounds to the nearest unit (stored values keep their decimals)."""
    return _fmt(value, places, signed)


def _month_name(month: str) -> str:
    """yyyy-mm as "September 2026"."""
    return date.fromisoformat(month + "-01").strftime("%B %Y")


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


class ReviewInbox:
    def __init__(self, container):
        self.c = container

    def items(self, on: date) -> list[dict]:
        """Everything waiting on the user on `on`, most urgent first (priority 0, then 1, then 2)."""
        c = self.c
        items = [{"label": "Missing valuation", "detail": item, "href": "/investments/prices", "priority": 0}
                 for item in c.reporting.net_worth(on).unvalued]
        items.extend(self._statements())
        items.extend(self._sms())
        items.extend(self._uncategorized())
        for reserve in c.reserves.list_active():
            if reserve.get("due_date") and reserve["due_date"] < fmt_date(on) and reserve["effective_allocated"] > ZERO:
                items.append({"label": f"{reserve['name']} is past its date",
                              "detail": f"Due {reserve['due_date']} · {fmt(reserve['effective_allocated'])} {c.base_currency} still set aside.",
                              "href": "/plan/reserves", "priority": 2})
        # Payments that are due and unpaid on this day, whatever period a page shows.
        for payment in c.planning.what_you_owe(on).bills_due_items:
            kind = "Loan payment due" if payment.item.kind.value == "LOAN" else "Bill due"
            items.append({"label": f"{kind}: {payment.item.name}",
                          "detail": f"Due {payment.due_date} · {fmt(payment.amount)} {c.base_currency} · not paid yet.",
                          "href": f"/plan/items/{payment.item.id}/pay?due={payment.due_date}&back=%2F",
                          "popup": True, "action": "Mark paid", "priority": 1})
        forecast = c.forecaster.forecast(on)
        lowest = forecast.lowest
        if lowest is not None and lowest.closing < ZERO:
            items.append({"label": "Cash may run short",
                          "detail": f"The cash forecast ends {lowest.month} at {fmt(lowest.closing)} {c.base_currency}.",
                          "href": "/plan", "priority": 1})
        # Honest numbers: a holding priced more than two months ago is shown at an old value.
        # Month-end prices the price files lack (a fund they do not cover, a stock listed later): typed by hand.
        missing = missing_prices(c)
        if missing:
            by_name: dict[str, list[str]] = {}
            for name, day in missing:
                by_name.setdefault(name, []).append(date.fromisoformat(day).strftime("%B %Y"))
            named = "; ".join(f"{name}, {', '.join(months[:3])}{' and more' if len(months) > 3 else ''}"
                              for name, months in list(by_name.items())[:2])
            more = f"; and {len(by_name) - 2} more" if len(by_name) > 2 else ""
            items.append({"label": _plural(len(missing), "price missing", "prices missing"),
                          "detail": f"{named}{more}.", "href": "/investments/prices#missing",
                          "action": "Get prices", "priority": 2})
        stale = c.reporting.stale_prices(on)
        if stale:
            named = ", ".join(f"{row['name']} ({row['price_date']})" for row in stale[:2])
            more = f" and {len(stale) - 2} more" if len(stale) > 2 else ""
            items.append({"label": "Prices are out of date",
                          "detail": f"Last priced: {named}{more}. Values use these old prices.",
                          "href": "/investments/prices", "action": "Update prices", "priority": 2})
        for section in c.budgets.month_view(month_of(on)).sections:
            if section.planned_actual > section.available:
                items.append({"label": f"{section.name} over plan",
                              "detail": f"{fmt(section.planned_actual - section.available)} {c.base_currency} over this month's plan.",
                              "href": "/budget", "priority": 2})
        # A category's own plan below what is already scheduled in it: the bill will overrun the plan.
        for row in c.budgets.below_scheduled(month_of(on)):
            items.append({"label": f"{row['name']} is planned below its bills",
                          "detail": f"Planned {fmt(row['planned'])} {c.base_currency}; bills and loan payments "
                                    f"scheduled this month come to {fmt(row['scheduled'])}.",
                          "href": f"/budget?month={month_of(on)}", "action": "Change the plan", "priority": 2})
        # The month's plan against the savings target and dated goals (one check: HealthService.plan_check).
        check = c.health.plan_check(month_of(on))
        if check.planned is not None and check.over_by and check.planned_savings_rate is not None:
            if check.short_for == "goals":
                items.append({"label": "This month's plan is short for your goals" if check.goals else
                                       "This month's plan is short for your emergency fund",
                              "detail": f"It leaves {fmt(check.plan_saves)} {c.base_currency}; {check.needs_label} "
                                        f"{fmt(check.needs)}. Plan {fmt(check.over_by)} less.",
                              "href": f"/budget?month={check.month}", "priority": 2})
            else:
                items.append({"label": "This month's plan is below your savings target",
                              "detail": f"It saves {fmt(check.planned_savings_rate)}% of income; your target is "
                                        f"{fmt(check.target_percent)}%. Plan {fmt(check.over_by)} {c.base_currency} less.",
                              "href": f"/budget?month={check.month}", "priority": 2})
        items.extend(self._smarter_plan(on, forecast.free_cash))
        return sorted(items, key=lambda item: item["priority"])

    def _smarter_plan(self, on: date, free_cash) -> list[dict]:
        """Where the plan's parts disagree: a goal it cannot reach in time, income above the average, a month
        that saved less than the target, a category over its plan two months running (owner decision 2026-10-05)."""
        c, month, cur = self.c, month_of(on), self.c.base_currency
        found = []
        for goal in c.health.goal_reach(month):
            # Nothing moves into a goal by itself: the pace holds only if he sets that much aside each month.
            pace = (f"Setting aside {fmt(goal['can'])} a month, it is ready in {_month_name(goal['reached'])}."
                    if goal["reached"] else "Your plan leaves nothing for it.")
            # Free cash that already covers the goal is the quickest way: set it aside now (Reserves).
            way = (f"Set aside {fmt(goal['missing'])} of your {fmt(free_cash)} free cash now, or give it a later date."
                   if free_cash >= goal["missing"] else "Give it a later date, or plan less.")
            found.append({"label": f"{goal['name']} will not be ready by its date",
                          "detail": f"Due {goal['due_date']} · it needs {fmt(goal['need'])} {cur} a month and your plan "
                                    f"leaves {fmt(goal['can'])} for it. {pace} {way}",
                          "href": "/plan/reserves", "action": "See reserves", "priority": 2})
        offer = c.health.raise_offer(month)
        if offer:
            found.append({"label": "Your income went up",
                          "detail": f"Recurring expects {fmt(offer['recurring'])} {cur} a month, {fmt(offer['raise'])} "
                                    f"more than your average of {fmt(offer['average'])}. Plan with it, or save the difference.",
                          "href": f"/budget/raise?month={month}", "popup": True, "action": "Choose", "priority": 2})
        short = c.health.short_month(on)
        if short:
            found.append({"label": f"{_month_name(short['month'])} saved less than your target",
                          "detail": f"It saved {fmt(short['rate'])}% of money in; your target is {fmt(short['limit'])}%, "
                                    f"{fmt(short['short'])} {cur} more.",
                          "href": "/financial-health", "action": "See financial health", "priority": 2})
        below = {row["category_id"] for row in c.budgets.below_scheduled(month)}  # already named: plan below its bills
        for row in (row for row in c.budgets.over_twice(month) if row["category_id"] not in below):
            first, second = (_month_name(key).split()[0] for key in row["months"])
            detail = f"Over its plan in {first} and {second}, by up to {fmt(row['amount'])} {cur}."
            if row["from_id"]:
                found.append({"label": f"{row['name']} over plan two months running",
                              "detail": f"{detail} Move {fmt(row['amount'])} from {row['from_name']}, "
                                        "which had that left both months.",
                              "href": f"/budget/move?month={month}&to={row['category_id']}&from={row['from_id']}"
                                      f"&amount={row['amount']}", "popup": True, "action": "Move it", "priority": 2})
            else:
                found.append({"label": f"{row['name']} over plan two months running",
                              "detail": f"{detail} Raise its plan, or plan less elsewhere.",
                              "href": f"/budget?month={month}", "action": "Change the plan", "priority": 2})
        return found

    def _sms(self) -> list[dict]:
        """Bank SMS waiting on the owner before they reach a review: an account to choose, or words to read."""
        found = []
        count, unread = self.c.sms_imports.pending()
        if count:
            found.append({"label": "Bank SMS need their account",
                          "detail": f"{_plural(count, 'message waits', 'messages wait')} until you say which account "
                                    "they belong to.", "href": "/sms", "action": "Choose the account", "priority": 1})
        if unread:
            found.append({"label": "Bank SMS kept for you",
                          "detail": f"{_plural(unread, 'message waits', 'messages wait')}: unread, or the other side "
                                    "of a transfer. Enter or dismiss.", "href": "/sms", "action": "Look at them", "priority": 2})
        return found

    def _statements(self) -> list[dict]:
        """One item per statement left half reviewed, opening at its first waiting row."""
        found = []
        for batch in self.c.bank_imports.waiting_all():
            try:
                source = json.loads(batch["first_raw_json"])
            except (TypeError, ValueError):
                source = {}
            parsed = source.get("parsed") if isinstance(source, dict) else None
            day = (parsed.get("Date") if isinstance(parsed, dict) else None) or str(batch["created_at"])[:10]
            found.append({"label": "Imported activity needs a decision",
                          "detail": f"{batch['file_name']} · {_plural(batch['waiting'], 'row waits', 'rows wait')}"
                                    f" · from row {batch['first_row_number']} · {day}.",
                          "href": f"/accounts/{batch['account_id']}/import/{batch['batch_id']}"
                                  f"#import-row-{batch['first_row_id']}",
                          "action": "Finish the import", "priority": 1})
        return found

    def _uncategorized(self) -> list[dict]:
        """Posted activity filed as Unaccounted: an import posted it before anyone chose a category."""
        found = []
        for code, one, many in (("EXP.UNACCOUNTED", "payment has no category", "payments have no category"),
                                ("INC.UNACCOUNTED", "incoming amount has no category", "incoming amounts have no category")):
            category = self.c.categories.get_by_code(code)
            _, total = self.c.transactions.find(TxnFilter(category_ids=[category.id], limit=1))
            if total:
                found.append({"label": _plural(total, one, many).capitalize(),
                              "detail": "Choose a category for each, so the budget and reports count it.",
                              "href": f"/transactions?category_id={category.id}",
                              "action": "Sort them out", "priority": 2})
        return found
