"""One review inbox: every decision Lightning is waiting on, in one ordered list.

The Overview's Needs you shows it. Each item names what needs a decision, gives one line of
detail, and links to the page that settles it, with the action's name. Visibility preferences
never post money or settle the underlying financial action.
Reconciliation diagnostics stay in the Integrity checks view; this lists actions a user can take.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from hashlib import sha256

from lightning.core.errors import LightningError, ValidationError

from lightning.accounts.domain import AccountType
from lightning.core.dates import fmt_date, month_of
from lightning.core.money import ZERO, fmt
from lightning.planning.salary_day import review_identity, salary_review
from lightning.transactions.domain import TxnFilter
from lightning.workflows.market_prices import missing_prices


def _month_name(month: str) -> str:
    """yyyy-mm as "September 2026"."""
    return date.fromisoformat(month + "-01").strftime("%B %Y")


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def glance(name: str, verb: str, amount=None, when: str = "", n=None, sa: str = "") -> dict:
    """The item at a glance, for Home's To do (IV-11E, guideline C11.1: `Vodafone 350 · in 3 days  Pay ›`): what it is
    about, its figure, when or how many as a translatable phrase (``{n}`` and ``{sa}`` filled in), and one verb that
    says what happens. Not part of the item's identity: the label and detail already carry the same facts."""
    return {"name": name, "verb": verb, "amount": amount, "when": when, "n": n, "sa": sa}


# Needs you groups its items by what they are about (feedback ticket 84): one row per group on the Overview,
# and each group opens its own page. First match on the item's link wins; the order is the order shown.
GROUPS = (("payments", "Bills and payments", ("/plan/items/", "/plan/bill-alerts/", "/gameya/", "/deposits/")),
          ("activity", "Activity to sort out", ("/rules", "/sms", "/accounts/", "/transactions", "/activity", "/reimbursements")),
          ("budget", "Budget and saving", ("/budget", "/financial-health")),
          ("cash", "Cash and goals", ("/plan", "/payday")),
          ("prices", "Prices and valuations", ("/investments/", "/settings")))
GROUP_LABELS = {key: label for key, label, _ in GROUPS}


def group_of(item: dict) -> str:
    return next((key for key, _, prefixes in GROUPS if item["href"].startswith(prefixes)), "other")


# NF-3AZ10: the same items by job and consequence, whatever page shows them: what puts money at risk, events that
# do not yet agree with the bank or the ledger, and cleanup that can wait. Reviewed and snoozed items are still open.
CONSEQUENCES = (("risk", "Money at risk"), ("unreconciled", "Unreconciled events"), ("cleanup", "Optional cleanup"))
CONSEQUENCE_LABELS = dict(CONSEQUENCES)
_UNRECONCILED = ("/sms", "/accounts/", "/transactions", "/activity", "/deposits/", "/reimbursements")


def consequence_of(item: dict) -> str:
    explicit = item.get("consequence")
    if explicit in CONSEQUENCE_LABELS:
        return explicit
    label = item.get("label", "")
    if item["href"].startswith(_UNRECONCILED) or "arrived early" in label or "paid early" in label:
        return "unreconciled" if not item["label"].startswith(("Bill due", "Loan payment due")) else "risk"
    return "risk" if item.get("priority", 2) <= 1 else "cleanup"


def by_consequence(items: list[dict]) -> list[dict]:
    """The inbox as three sections, each with its items in the inbox's order; an empty section is left out."""
    out = []
    for key, label in CONSEQUENCES:
        mine = [item for item in items if item.get("consequence") == key]
        if mine:
            out.append({"key": key, "label": label, "items": mine, "count": len(mine)})
    return out


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
        self.handled = {"reviewed": 0, "snoozed": 0}

    def items(self, on: date, *, include_handled: bool = False) -> list[dict]:
        """Everything waiting on the user on `on`, most urgent first (priority 0, then 1, then 2)."""
        c = self.c
        items = [{"label": "Missing valuation", "detail": item, "priority": 0,
                  # a missing exchange rate is typed in Settings; a missing price on the prices page
                  "href": "/settings?section=currencies&tab=rates" if " rate within " in item else "/investments/prices"}
                 for item in c.reporting.net_worth(on).unvalued]
        items.extend(self._statements())
        items.extend(self._sms())
        items.extend(self._balance_checks())
        items.extend(self._uncategorized())
        items.extend(self._smart_suggestions(on))
        from lightning.workflows.bill_alerts import bill_alerts
        intelligence = bill_alerts(c, on)
        items.extend(intelligence)
        salary = salary_review(c.db, on)
        if salary:
            items.append(salary)
        for reserve in c.reserves.list_active():
            if (reserve["spent"] > ZERO and reserve["remaining"] > ZERO
                    and (reserve["kind"] == "EMERGENCY" or reserve["recurrence"] != "NONE")):
                items.append({"label": "Refill a reserve",
                              "detail": f"{reserve['name']} · {fmt(reserve['remaining'], 0)} {c.base_currency} to refill.",
                              "href": "/plan/reserves", "action": "Refill", "priority": 2,
                              "glance": glance(reserve["name"], "Refill", reserve["remaining"], "to refill"),
                              "source_version": {"reserve": reserve["id"],
                                                 "payments": [(row["id"], row["amount_e6"]) for row in
                                                              c.reserves.links_for_reserve(reserve["id"])]}})
            if reserve.get("due_date") and reserve["due_date"] < fmt_date(on) and reserve["effective_allocated"] > ZERO:
                items.append({"label": f"{reserve['name']} is past its date",
                              "detail": f"Due {reserve['due_date']} · {fmt(reserve['effective_allocated'], 0)} {c.base_currency} still set aside.",
                              "href": "/plan/reserves", "priority": 2,
                              "glance": glance(reserve["name"], "Open", reserve["effective_allocated"], "past its date")})
        # Payments that are due and unpaid on this day, whatever period a page shows.
        for payment in c.planning.what_you_owe(on).bills_due_items:
            kind = "Loan payment due" if payment.item.kind.value == "LOAN" else "Bill due"
            items.append({"label": f"{kind}: {payment.item.name}",
                          "detail": f"Due {payment.due_date} · {fmt(payment.amount, 0)} {c.base_currency} · not paid yet.",
                          "href": f"/plan/items/{payment.item.id}/pay?due={payment.due_date}&back=%2F",
                          "popup": True, "action": "Mark paid", "priority": 1,
                          "late_days": payment.days_late(on)})
        # Money that moved before the payment was due (salary 12 days early): the forecast no longer counts it
        # twice, and one press links it (7K).
        for early in c.planning.early_payments(on):
            item, payment, txn = early["item"], early["payment"], early["transaction"]
            currency = c.accounts.get(item.account_id).currency if item.account_id else c.base_currency
            items.append({"label": f"{item.name} arrived early" if item.is_income else f"{item.name} was paid early",
                          "detail": f"{fmt(txn['amount'], 0)} {currency} on {txn['date']}, for the payment due {payment.due_date}. "
                                    "Link it so the plan does not count it again.",
                          "href": f"/plan/items/{item.id}/pay?due={payment.due_date}&back=%2F", "popup": True,
                          "action": "Link", "priority": 1,
                          "glance": glance(item.name, "Link", txn["amount"], "arrived early" if item.is_income else "paid early"),
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
            if any(alert["plan_id"] == changed["id"] for alert in intelligence):
                continue
            from lightning.core.money import from_e6
            currency = c.accounts.get(changed["account_id"]).currency if changed["account_id"] else c.base_currency
            items.append({"label": f"{changed['name']} was paid at a different amount",
                          "detail": f"Latest payment {fmt(from_e6(changed['paid_e6']), 0)} {currency}; "
                                    f"planned {fmt(from_e6(changed['amount_e6']), 0)}. Review future payments.",
                          "href": f"/plan/items/{changed['id']}/edit", "priority": 2,
                          "glance": glance(changed["name"], "Update", from_e6(changed["paid_e6"]), "new amount")})
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
                            "detail": f"{fmt(sum(i['remaining'] for i in issues), 0)} {account.currency} still unmatched"
                                      + (f"; {suggested} have a suggested bank receipt." if suggested else "."),
                            "href": f"/deposits/{account.id}#interest-receipts", "priority": 1, "action": "Review",
                            "glance": glance(name, "Match", sum(i["remaining"] for i in issues),
                                             "1 to match" if len(issues) == 1 else "{n} to match", len(issues))}
                    if suggested:
                        item["post"] = {"href": f"/deposits/{account.id}/certificates/{certificate_id}/interest/match-all",
                                        "label": "Match all suggested"}
                    items.append(item)
        if getattr(c, "reimbursements", None) is not None:
            claims = c.reimbursements.list_claims()
            pairs = c.reimbursements.suggested_pairs(on, claims=claims)
            if pairs:
                count = len(pairs)
                items.append({"label": "Reimbursement receipts to pair",
                              "detail": f"{count} possible pairs in the original expense category. Review before linking.",
                              "href": "/reimbursements#suggested-pairs", "priority": 2, "action": "Review",
                              "glance": glance("Reimbursement receipts", "Pair", None,
                                               "1 to pair" if count == 1 else "{n} to pair", count)})
            for claim in claims:
                if claim["issues"] or (claim["outstanding"] and claim["due_date"] and claim["due_date"] <= on.isoformat()):
                    items.append({"label": "Reimbursement needs review",
                                  "detail": f"{fmt(claim['outstanding'], 0)} {c.base_currency} outstanding.",
                                  "href": "/reimbursements", "priority": 1,
                                  "glance": glance("Reimbursement", "Check", claim["outstanding"], "outstanding")})
        forecast = self.forecast = c.forecaster.forecast(on)  # the Overview's Safe to spend card reads it too
        # A dated daily forecast takes precedence over its monthly summary: the summary can hide which
        # day or account runs short, and would duplicate a more useful warning.
        dated = getattr(forecast, "dated", None)  # older forecast doubles may not expose this yet
        first_shortfall = getattr(dated, "first_shortfall", None)
        account_shortfalls = getattr(dated, "account_shortfalls", ()) or ()
        if first_shortfall is not None:
            items.append({"label": "Cash may run short",
                          "detail": f"Scheduled payments may leave cash short by {fmt(abs(first_shortfall.balance), 0)} "
                                    f"{first_shortfall.currency} on {first_shortfall.date}.",
                          "href": "/plan#plan-dated-cash", "priority": 1,
                          "glance": glance("Cash", "See", abs(first_shortfall.balance), "short on {sa}", sa=first_shortfall.date)})
        elif account_shortfalls:
            earliest = min(account_shortfalls, key=lambda item: item.date)
            items.append({"label": f"{earliest.account_name} may run short",
                          "detail": f"Scheduled payments may leave this account short by {fmt(abs(earliest.balance), 0)} "
                                    f"{earliest.currency} on {earliest.date}.",
                          "href": "/plan#plan-dated-cash", "priority": 1,
                          "glance": glance(earliest.account_name, "See", abs(earliest.balance), "short on {sa}", sa=earliest.date)})
        else:
            # Keep the existing monthly warning for deficits caused by the variable-budget forecast.
            lowest = forecast.lowest
            if lowest is not None and lowest.closing < ZERO:
                items.append({"label": "Cash may run short",
                              "detail": f"The cash forecast ends {lowest.month} at {fmt(lowest.closing, 0)} {c.base_currency}.",
                              "href": "/plan", "priority": 1,
                              "glance": glance("Cash", "See", -lowest.closing, "short in {sa}", sa=lowest.month)})
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
                          "action": "Get prices", "priority": 2,
                          "glance": glance("Prices", "Get prices", None, "1 missing" if len(missing) == 1 else "{n} missing", len(missing))})
        stale = c.reporting.stale_prices(on)
        if stale:
            named = ", ".join(f"{row['name']} ({row['price_date']})" for row in stale[:2])
            more = f" and {len(stale) - 2} more" if len(stale) > 2 else ""
            items.append({"label": "Prices are out of date",
                          "detail": f"Last priced: {named}{more}. Values use these old prices.",
                          "href": "/investments/prices", "action": "Update prices", "priority": 2,
                          "glance": glance("Prices", "Update", None, "1 out of date" if len(stale) == 1 else "{n} out of date", len(stale))})
        for section in c.budgets.month_view(month_of(on), schedule=c.schedules.view()).sections:
            for line in section.lines:
                if line.depth == 2 and line.over:
                    items.append({"label": f"{line.name} over plan",
                                  "detail": f"{fmt(line.planned_actual - line.available, 0)} {c.base_currency} over this month's plan.",
                                  "href": f"/budget?month={month_of(on)}&open_group=all#limit-{line.category_id}",
                                  "action": "Change the plan", "priority": 2,
                                  "glance": glance(line.name, "Adjust", line.planned_actual - line.available, "over plan")})
            if section.planned_actual > section.available:
                items.append({"label": f"{section.name} over plan",
                              "detail": f"{fmt(section.planned_actual - section.available, 0)} {c.base_currency} over this month's plan.",
                              "href": "/budget", "priority": 2,
                              "glance": glance(section.name, "Adjust", section.planned_actual - section.available, "over plan")})
        # A category's own plan below what is already scheduled in it: the bill will overrun the plan.
        for row in c.budgets.below_scheduled(month_of(on), schedule=c.schedules.view()):
            items.append({"label": f"{row['name']} is planned below its bills",
                          "detail": f"Planned {fmt(row['planned'], 0)} {c.base_currency}; bills and loan payments "
                                    f"scheduled this month come to {fmt(row['scheduled'], 0)}.",
                          "href": f"/budget?month={month_of(on)}&open_group=all#limit-{row['category_id']}",
                          "action": "Change the plan", "priority": 2,  # where its limit is typed (IV-3AL2)
                          "glance": glance(row["name"], "Adjust", row["scheduled"] - row["planned"], "below its bills")})
        # The month's plan against the savings target and dated goals (one check: HealthService.plan_check).
        check = c.health.plan_check(month_of(on))
        if check.planned is not None and check.over_by and check.planned_savings_rate is not None:
            if check.short_for == "goals":
                items.append({"label": "This month's plan is short for your goals" if check.goals else
                                       "This month's plan is short for your emergency fund",
                              "detail": f"It leaves {fmt(check.plan_saves, 0)} {c.base_currency}; {check.needs_label} "
                                        f"{fmt(check.needs, 0)}. Plan {fmt(check.over_by, 0)} less.",
                              "href": f"/budget?month={check.month}", "priority": 2,
                              "glance": glance("This month's plan", "Plan less", check.over_by,
                                               "short for your goals" if check.goals else "short for your emergency fund")})
            else:
                items.append({"label": "This month's plan is below your savings target",
                              "detail": f"It saves {fmt(check.planned_savings_rate, 0)}% of income; your target is "
                                        f"{fmt(check.target_percent, 0)}%. Plan {fmt(check.over_by, 0)} {c.base_currency} less.",
                              "href": f"/budget?month={check.month}", "priority": 2,
                              "glance": glance("This month's plan", "Plan less", check.over_by, "below your savings target")})
        items.extend(self._smarter_plan(on, forecast.free_cash))
        items.extend(self._health_alerts(on, items))
        visible = []
        self.handled = {"reviewed": 0, "snoozed": 0}
        for item in sorted(items, key=lambda item: item["priority"]):
            # Visible facts define the situation, not days-late badges or the current date.
            # A changed amount, due date, count or recommendation gets a fresh reminder.
            identity = review_identity(item)
            item["review_id"] = identity
            item["consequence"] = consequence_of(item)
            state = self._state(identity)
            item["review_state"] = "active"
            if state.get("status") == "reviewed":
                item["review_state"] = "reviewed"
            elif state.get("status") == "snoozed" and state.get("until", "") > on.isoformat():
                item["review_state"] = "snoozed"
                item["snoozed_until"] = state["until"]
            if item["review_state"] in self.handled:
                self.handled[item["review_state"]] += 1   # still open: never counted as resolved
            if include_handled or item["review_state"] == "active":
                visible.append(item)
        return visible

    def _smart_suggestions(self, on: date) -> list[dict]:
        """Existing suggestion engines, routed through the same durable review decisions."""
        from lightning.workflows.weekly import WeeklyReview
        items = []
        for offer in self.c.planning.suggestions(on):
            currency = (self.c.accounts.get(offer["account_id"]).currency
                        if offer.get("account_id") else self.c.base_currency)
            items.append({"label": "Looks recurring",
                          "detail": f"{offer['name']} · {fmt(offer['amount'], 0)} {currency} · {offer['months']} months · last {offer['last_date']}.",
                          "href": "/plan/recurring#recurring-suggest", "action": "Track", "priority": 2,
                          "glance": glance(offer["name"], "Make it a bill", offer["amount"], "every month"),
                          "source_version": str(offer["counterparty_id"])})
        for offer in WeeklyReview(self.c).rule_offers():
            items.append({"label": "Make a rule",
                          "detail": f"{offer['name']} · {offer['count']} corrections · {offer['category']}.",
                          "href": offer["href"], "action": "Make a rule", "popup": True,
                          "glance": glance(offer["name"], "Make a rule", None,
                                           "1 correction" if offer["count"] == 1 else "{n} corrections", offer["count"]),
                          "priority": 2, "source_version": offer["id"]})
        return items

    def _health_alerts(self, on: date, existing: list[dict]) -> list[dict]:
        """Reuse Health's alert bands, keeping its existing saving reminders as the single action."""
        from lightning.planning.health import LIMIT_LABELS
        items = []
        for figure in self.c.health.figures(on):
            if figure.band != "alert":
                continue
            if figure.key == "planned_savings_rate" and any(
                    item["label"].startswith("This month's plan is ") for item in existing):
                continue
            if figure.key == "savings_rate" and any(
                    item["label"].endswith(" saved less than your target") for item in existing):
                continue
            if figure.key == "emergency_fund":
                items.append({"label": "Emergency fund needs you",
                              "detail": f"{fmt(figure.value, 1)} months of cover. Review your emergency reserve.",
                              "href": "/financial-health", "action": "Review", "priority": 2,
                              "glance": glance("Emergency fund", "Top up", self.c.health.emergency_fund(on).top_up or None,
                                               "this month")})
                continue
            label = "Planned savings rate" if figure.key == "planned_savings_rate" else LIMIT_LABELS[figure.key]
            if figure.gap:
                detail = figure.gap + "."
            else:
                side = "below" if figure.direction == "minimum" else "above"
                detail = f"{fmt(figure.value, 1)}% · Needs you {side} {fmt(figure.alert, 1)}%."
            if figure.key in {"savings_rate", "planned_savings_rate"}:
                detail += f" {figure.period}."
            items.append({"label": f"{label} needs you", "detail": detail,
                          "href": f"/financial-health#health-{figure.key}", "action": "Review", "priority": 2,
                          "source_version": {"good": str(figure.limit), "alert": str(figure.alert)}})
        return items

    def _state(self, identity: str) -> dict:
        try:
            value = json.loads(self.c.settings.get("review_item_" + identity) or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}

    def decide(self, identity: str, action: str, on: date, until: str = "") -> None:
        """Change only this reminder's visibility. Its financial action remains outstanding."""
        if action not in ("reviewed", "snoozed", "restore"):
            raise ValidationError("Choose Mark as reviewed, Snooze or Restore.")
        if identity not in {item["review_id"] for item in self.items(on, include_handled=True)}:
            raise ValidationError("This item changed or no longer needs you. Review the current list.")
        state = {"status": action}
        if action == "snoozed":
            try:
                wake = date.fromisoformat(until)
                if wake.isoformat() != until or wake <= on:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValidationError("Choose a snooze date after today.") from None
            state["until"] = until
        # One setting per situation avoids overwriting decisions on unrelated items.
        with self.c.db.transaction(undo_label="Needs you preference"):
            self.c.settings.set("review_item_" + identity, json.dumps(state, sort_keys=True))

    def _smarter_plan(self, on: date, free_cash) -> list[dict]:
        """Where the plan's parts disagree: a goal it cannot reach in time, income above the average, a month
        that saved less than the target, a category over its plan two months running (owner decision 2026-10-05)."""
        c, month, cur = self.c, month_of(on), self.c.base_currency
        found = []
        for goal in c.health.goal_reach(month):
            # Nothing moves into a goal by itself: the pace holds only if he sets that much aside each month.
            pace = (f"Setting aside {fmt(goal['can'], 0)} a month, it is ready in {_month_name(goal['reached'])}."
                    if goal["reached"] else "Your plan leaves nothing for it.")
            # Free cash that already covers the goal is the quickest way: set it aside now (Reserves).
            way = (f"Set aside {fmt(goal['missing'], 0)} of your {fmt(free_cash, 0)} free cash now, or give it a later date."
                   if free_cash >= goal["missing"] else "Give it a later date, or plan less.")
            found.append({"label": f"{goal['name']} will not be ready by its date",
                          "detail": f"Due {goal['due_date']} · it needs {fmt(goal['need'], 0)} {cur} a month and your plan "
                                    f"leaves {fmt(goal['can'], 0)} for it. {pace} {way}",
                          "href": "/plan/reserves", "action": "See reserves", "priority": 2,
                          "glance": glance(goal["name"], "Set aside", goal["need"], "a month")})
        offer = c.health.raise_offer(month)
        if offer:
            found.append({"label": "Your income went up",
                          "detail": f"Recurring expects {fmt(offer['recurring'], 0)} {cur} a month, {fmt(offer['raise'], 0)} "
                                    f"more than your average of {fmt(offer['average'], 0)}. Plan with it, or save the difference.",
                          "href": f"/budget/raise?month={month}", "popup": True, "action": "Choose", "priority": 2,
                          "glance": glance("Your income", "Choose", offer["raise"], "more a month")})
        short = c.health.short_month(on)
        if short:
            found.append({"label": f"{_month_name(short['month'])} saved less than your target",
                          "detail": f"It saved {fmt(short['rate'], 0)}% of money in; your target is {fmt(short['limit'], 0)}%, "
                                    f"{fmt(short['short'], 0)} {cur} more.",
                          "href": "/financial-health", "action": "See financial health", "priority": 2,
                          "glance": glance(_month_name(short["month"]), "See", short["short"], "short of your target")})
        below = {row["category_id"] for row in c.budgets.below_scheduled(month, schedule=c.schedules.view())}  # already named: plan below its bills
        for row in (row for row in c.budgets.over_twice(month, schedule=c.schedules.view()) if row["category_id"] not in below):
            first, second = (_month_name(key).split()[0] for key in row["months"])
            detail = f"Over its plan in {first} and {second}, by up to {fmt(row['amount'], 0)} {cur}."
            if row["from_id"]:
                found.append({"label": f"{row['name']} over plan two months running",
                              "detail": f"{detail} Move {fmt(row['amount'], 0)} from {row['from_name']}, "
                                        "which had that left both months.",
                              "href": f"/budget/move?month={month}&to={row['category_id']}&from={row['from_id']}"
                                      f"&amount={row['amount']}", "popup": True, "action": "Move it", "priority": 2,
                              "glance": glance(row["name"], "Move it", row["amount"], "over plan 2 months")})
            else:
                found.append({"label": f"{row['name']} over plan two months running",
                              "detail": f"{detail} Raise its plan, or plan less elsewhere.",
                              "href": f"/budget?month={month}&open_group=all#limit-{row['category_id']}",
                              "action": "Change the plan", "priority": 2,
                              "glance": glance(row["name"], "Adjust", row["amount"], "over plan 2 months")})
        return found

    def _sms(self) -> list[dict]:
        """Bank SMS waiting on the owner before they reach a review: an account to choose, or words to read."""
        found = []
        count, unread = self.c.sms_imports.pending()
        if count:
            found.append({"label": "Bank SMS need their account",
                          "detail": f"{_plural(count, 'message waits', 'messages wait')} until you say which account "
                                    "they belong to.", "href": "/sms", "action": "Choose the account", "priority": 1,
                          "glance": glance("Bank SMS", "Choose", None, "1 needs an account" if count == 1 else "{n} need an account", count)})
        if unread:
            found.append({"label": "Bank SMS kept for you",
                          "detail": f"{_plural(unread, 'message waits', 'messages wait')}: unread, or the other side "
                                    "of a transfer. Enter or dismiss.", "href": "/sms", "action": "Look at them", "priority": 2,
                          "glance": glance("Bank SMS", "Enter", None, "1 kept for you" if unread == 1 else "{n} kept for you", unread)})
        return found

    def _balance_checks(self) -> list[dict]:
        """NF-7AP: the balance a bank message states, compared with the account's ledger on that day. One quiet row per
        account that differs by more than a piastre; it clears when a later message agrees or it is dismissed. An
        account with messages still waiting to be posted is left alone: its entries are not in the ledger yet."""
        c = self.c
        waiting = {b["account_id"] for b in c.bank_imports.waiting_all() if str(b["file_name"]).startswith("SMS ")}
        names = {a.id: a.name for a in c.accounts.list(active_only=True)}
        found = []
        for account_id, note in c.sms_imports.stated_balances().items():
            if note.get("dismissed") or account_id in waiting or account_id not in names:
                continue
            try:
                off = c.reconciliation.balance(account_id, note["date"]) - Decimal(note["balance"])
            except (LightningError, ArithmeticError, ValueError):
                continue
            if abs(off) <= Decimal("0.01"):
                continue
            shown = fmt(abs(off))
            found.append({"label": f"{names[account_id]} is {shown} {'above' if off > 0 else 'below'} the bank's balance",
                          "detail": f"The bank's message on {fmt_date(date.fromisoformat(note['date']))} said "
                                    f"{fmt(Decimal(note['balance']))}; Lightning has {fmt(c.reconciliation.balance(account_id, note['date']))}. "
                                    "An entry may be missing, or a payment is still pending.",
                          "href": f"/accounts/{account_id}?date={note['date']}", "action": "Look at the day", "account_id": account_id,
                          "priority": 2, "consequence": "unreconciled",
                          "glance": glance(names[account_id], "Check", abs(off), "off the bank's balance")})
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
                          "action": "Finish the import", "priority": 1,
                          "glance": glance(batch["file_name"], "Finish", None,
                                           "1 row waits" if batch["waiting"] == 1 else "{n} rows wait", batch["waiting"])})
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
                              "action": "Sort them out", "priority": 2,
                              "glance": glance("No category", "Sort", None,
                                               ("1 payment" if total == 1 else "{n} payments") if code.startswith("EXP")
                                               else ("1 amount in" if total == 1 else "{n} amounts in"), total),
                              "source_version": sha256(json.dumps([tuple(row) for row in self.c.db.all(
                                  "SELECT DISTINCT t.id,t.updated_at FROM transactions t JOIN ledger_entries l "
                                  "ON l.transaction_id=t.id WHERE l.category_id=? AND t.status='POSTED' ORDER BY t.id",
                                  (category.id,))]).encode()).hexdigest()})
        return found

