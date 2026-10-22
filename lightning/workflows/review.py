"""One review inbox: every decision Lightning is waiting on, in one ordered list.

The Overview's Needs you shows it. Each item names what needs a decision, gives one line of
detail, and links to the page that settles it, with the action's name. Nothing here changes data.
Reconciliation diagnostics stay in the Integrity checks view; this lists actions a user can take.
"""
from __future__ import annotations

import json
from datetime import date

from lightning.accounts.domain import AccountType
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


# Needs you groups its items by what they are about (feedback ticket 84): one row per group on the Overview,
# and each group opens its own page. First match on the item's link wins; the order is the order shown.
GROUPS = (("payments", "Bills and payments", ("/plan/items/", "/gameya/", "/deposits/")),
          ("activity", "Activity to sort out", ("/sms", "/accounts/", "/transactions", "/activity", "/reimbursements")),
          ("budget", "Budget and saving", ("/budget", "/financial-health")),
          ("cash", "Cash and goals", ("/plan",)),
          ("prices", "Prices and valuations", ("/investments/", "/settings")))
GROUP_LABELS = {key: label for key, label, _ in GROUPS}


def group_of(item: dict) -> str:
    return next((key for key, _, prefixes in GROUPS if item["href"].startswith(prefixes)), "other")


# Each page shows its own items under its Lead (guideline A09); the Overview shows them all. First match wins.
PAGES = (("budget", ("/budget",)), ("health", ("/financial-health",)), ("cash", ("/plan",)),
         ("investments", ("/investments/", "/deposits/")), ("accounts", ("/accounts/", "/sms", "/transactions")))


def page_of(item: dict) -> str:
    return next((key for key, prefixes in PAGES if item["href"].startswith(prefixes)), "overview")


def grouped(items: list[dict]) -> list[dict]:
    """The inbox as groups, most urgent first: key, label, its items, and where the row leads. A group of one
    leads straight to its item, so a single decision is still one click away."""
    groups: dict[str, dict] = {}
    for item in items:
        key = group_of(item)
        group = groups.setdefault(key, {"key": key, "label": GROUP_LABELS.get(key, "Other"), "items": []})
        group["items"].append(item)
    out = []
    for group in groups.values():
        first = group["items"][0]
        group["priority"] = min(item["priority"] for item in group["items"])
        if len(group["items"]) == 1:  # shown as itself: its own words, detail and action
            group.update(label=first["label"], detail=first["detail"], href=first["href"],
                         popup=bool(first.get("popup")), action=first.get("action") or "Review", count=1,
                         late_days=first.get("late_days", 0))
        else:
            names = ", ".join(i["label"] for i in group["items"][:2])
            more = f" and {len(group['items']) - 2} more" if len(group["items"]) > 2 else ""
            group.update(detail=names + more, href=f"/needs-you/{group['key']}", popup=False, action="See them",
                         count=len(group["items"]))
        out.append(group)
    order = [key for key, _, _ in GROUPS] + ["other"]
    return sorted(out, key=lambda g: (g["priority"], order.index(g["key"])))


class ReviewInbox:
    def __init__(self, container):
        self.c = container

    def items(self, on: date) -> list[dict]:
        """Everything waiting on the user on `on`, most urgent first (priority 0, then 1, then 2)."""
        c = self.c
        items = [{"label": "Missing valuation", "detail": item, "priority": 0,
                  # a missing exchange rate is typed in Settings; a missing price on the prices page
                  "href": "/settings?section=currencies&tab=rates" if " rate within " in item else "/investments/prices"}
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
                          "popup": True, "action": "Mark paid", "priority": 1,
                          "late_days": payment.days_late(on)})
        # Money that moved before the payment was due (salary 12 days early): the forecast no longer counts it
        # twice, and one press links it (7K).
        for early in c.planning.early_payments(on):
            item, payment, txn = early["item"], early["payment"], early["transaction"]
            currency = c.accounts.get(item.account_id).currency if item.account_id else c.base_currency
            items.append({"label": f"{item.name} arrived early" if item.is_income else f"{item.name} was paid early",
                          "detail": f"{fmt(txn['amount'])} {currency} on {txn['date']}, for the payment due {payment.due_date}. "
                                    "Link it so the plan does not count it again.",
                          "href": f"/plan/items/{item.id}/pay?due={payment.due_date}&back=%2F", "popup": True,
                          "action": "Link", "priority": 1,
                          "post": {"href": f"/plan/items/{item.id}/pay", "label": "Link this payment",
                                   "fields": {"outcome": "link", "due": payment.due_date,
                                              "transaction_id": str(txn["id"])}}})
        items.extend(c.gameya.attention(on))  # an instalment or payout past its date and not recorded
        for changed in c.db.all(
                "SELECT i.id,i.name,i.amount_e6,i.account_id,p.amount_e6 AS paid_e6,p.due_date "
                "FROM planned_items i JOIN planned_payments p ON p.planned_item_id=i.id "
                "WHERE i.active=1 AND i.kind IN ('BILL','SUBSCRIPTION') AND p.status='PAID' "
                "AND p.amount_e6<>i.amount_e6 AND p.amount_e6>0 AND p.created_at>i.updated_at "
                "AND p.due_date BETWEEN date(?,'-45 days') AND ? AND p.due_date=(SELECT MAX(q.due_date) "
                "FROM planned_payments q WHERE q.planned_item_id=i.id AND q.status='PAID' AND q.due_date<=?)",
                (on.isoformat(), on.isoformat(), on.isoformat())):
            from lightning.core.money import from_e6
            currency = c.accounts.get(changed["account_id"]).currency if changed["account_id"] else c.base_currency
            items.append({"label": f"{changed['name']} was paid at a different amount",
                          "detail": f"Latest payment {fmt(from_e6(changed['paid_e6']))} {currency}; "
                                    f"planned {fmt(from_e6(changed['amount_e6']))}. Review future payments.",
                          "href": f"/plan/items/{changed['id']}/edit", "priority": 2})
        if getattr(c, "deposit_receipts", None) is not None:
            # One item per certificate, not per month: the bank's fixed payout rarely equals the day-count figure.
            for account in c.accounts.list(active_only=True):
                if account.account_type != AccountType.DEPOSIT:
                    continue
                by_certificate: dict[int, list[dict]] = {}
                for occurrence in c.deposit_receipts.match_plan(account.id, on):
                    if c.deposit_receipts.needs_match(occurrence):
                        by_certificate.setdefault(occurrence["certificate_id"], []).append(occurrence)
                for certificate_id, issues in by_certificate.items():
                    name = c.deposits.certificate(certificate_id).terms.name
                    suggested = sum(1 for issue in issues if issue["suggested"])
                    item = {"label": f"{name}: {len(issues)} interest payments to match" if len(issues) != 1
                                     else f"{name}: 1 interest payment to match",
                            "detail": f"{fmt(sum(i['remaining'] for i in issues))} {account.currency} still unmatched"
                                      + (f"; {suggested} have a suggested bank receipt." if suggested else "."),
                            "href": f"/deposits/{account.id}#interest-receipts", "priority": 1, "action": "Review"}
                    if suggested:
                        item["post"] = {"href": f"/deposits/{account.id}/certificates/{certificate_id}/interest/match-all",
                                        "label": "Match all suggested"}
                    items.append(item)
        if getattr(c, "reimbursements", None) is not None:
            for claim in c.reimbursements.list_claims():
                if claim["issues"] or (claim["outstanding"] and claim["due_date"] and claim["due_date"] <= on.isoformat()):
                    items.append({"label": "Reimbursement needs review",
                                  "detail": f"{fmt(claim['outstanding'])} {c.base_currency} outstanding.",
                                  "href": "/reimbursements", "priority": 1})
        forecast = self.forecast = c.forecaster.forecast(on)  # the Overview's Safe to spend card reads it too
        # A dated daily forecast takes precedence over its monthly summary: the summary can hide which
        # day or account runs short, and would duplicate a more useful warning.
        dated = getattr(forecast, "dated", None)  # older forecast doubles may not expose this yet
        first_shortfall = getattr(dated, "first_shortfall", None)
        account_shortfalls = getattr(dated, "account_shortfalls", ()) or ()
        if first_shortfall is not None:
            items.append({"label": "Cash may run short",
                          "detail": f"Scheduled payments may leave cash short by {fmt(abs(first_shortfall.balance))} "
                                    f"{first_shortfall.currency} on {first_shortfall.date}.",
                          "href": "/plan#plan-dated-cash", "priority": 1})
        elif account_shortfalls:
            earliest = min(account_shortfalls, key=lambda item: item.date)
            items.append({"label": f"{earliest.account_name} may run short",
                          "detail": f"Scheduled payments may leave this account short by {fmt(abs(earliest.balance))} "
                                    f"{earliest.currency} on {earliest.date}.",
                          "href": "/plan#plan-dated-cash", "priority": 1})
        else:
            # Keep the existing monthly warning for deficits caused by the variable-budget forecast.
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
