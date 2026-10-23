from __future__ import annotations

import calendar

from decimal import Decimal, InvalidOperation
from datetime import timedelta
from collections import defaultdict
from urllib.parse import urlencode

from fastapi import APIRouter, Request

from lightning.accounts.domain import AccountType
from lightning.core.dates import fmt_date, month_of, months_back, parse_date, parse_month, today
from lightning.core.errors import LightningError, ValidationError
from lightning.core.figures import FIGURES, label
from lightning.core.money import ZERO, fmt as _fmt, to_decimal


def fmt(value, places: int = 0, signed: bool = False) -> str:
    """Reporting text rounds to the nearest unit (stored values keep their decimals)."""
    return _fmt(value, places, signed)
from lightning.investments.report import investing_rate, investment_period, saved_and_invested
from lightning.workflows.review import GROUP_LABELS, ReviewInbox, group_of, grouped

from ..web import container, render
from ..web import redirect
from ..periods import Period, parse_period
from .. import keynotes, kpis, status as page_status, visuals
from .sms import read_phone_sms

router = APIRouter()

_ACCOUNT_TYPE_LABELS = {
    AccountType.CASH: "Cash",
    AccountType.BANK: "Bank",
    AccountType.DEPOSIT: "Deposits",
    AccountType.GAMEYA: "Gam'eya",
    AccountType.BROKERAGE: "Brokerage",
    AccountType.PHYSICAL_ASSET: "Physical assets",
    AccountType.OTHER_ASSET: "Other assets",
}


def _owned_account_type_rows(c, accounts, as_of, include_types=None):
    groups = {}
    for account in accounts:
        if include_types is not None and account.account_type not in include_types:
            continue
        value = c.reporting.owned_account_value(account.id, as_of)
        group = groups.setdefault(account.account_type, {"label": _ACCOUNT_TYPE_LABELS[account.account_type],
                                                         "value": ZERO, "accounts": []})
        group["value"] += value
        group["accounts"].append({"id": account.id, "label": account.label, "value": value})
    return [groups[account_type] for account_type in AccountType if account_type in groups]


def _owned_wealth_rows(c, net_worth, as_of):
    """Allocate held-for-others balances to their classes for reconciled breakdowns."""
    values = {group.code: group.value for group in net_worth.by_class if group.code != "CUSTODY"}
    labels = {group.code: group.label for group in net_worth.by_class if group.code != "CUSTODY"}

    def root_code(class_id):
        return c.assets.get_class(class_id).code.split(".", 1)[0]

    for account in c.accounts.list(active_only=True):
        held = c.money_from_others.cash_total_for_account(account.id, as_of)
        if held:
            valuation = c.reporting.value_of(c.assets.cash_asset(account.currency).id, held, as_of)
            code = root_code(account.cash_class_id)
            if valuation.value is not None and code in values:
                values[code] -= valuation.value
    for position in c.money_from_others.investment_positions(as_of):
        asset = c.assets.get_asset(position["asset_id"])
        valuation = c.reporting.value_of(asset.id, position["units"], as_of)
        code = root_code(asset.asset_class_id)
        if valuation.value is not None and code in values:
            values[code] -= valuation.value
    if "GAMEYA" in values:
        values["GAMEYA"] += net_worth.gameya_owed  # a negative circle is a debt (What you owe), not a negative asset
    brokerage_cash = c.reporting.owned_brokerage_cash(as_of)
    if brokerage_cash:
        if "CASH" in values:
            values["CASH"] -= brokerage_cash
        values["BROKERAGE_CASH"] = brokerage_cash
        labels["BROKERAGE_CASH"] = "Brokerage cash"
    return [{"code": code, "label": labels[code], "value": value,
             "percentage": value / net_worth.what_you_own * 100 if net_worth.what_you_own else ZERO}
            for code, value in values.items()]


@router.get("/")
async def dashboard(request: Request):
    c = container(request)
    month = str(request.query_params.get("month", month_of(today())))
    first_activity = c.reporting.first_activity_date()
    try:
        period = parse_period(request.query_params, today(), first_activity)
        period_error = ""
    except ValidationError as exc:
        fallback = parse_period({"period": "month", "month": month_of(today())}, today(), first_activity)
        selected = str(request.query_params.get("period", "month"))
        period = Period(selected, "Custom" if selected == "custom" else fallback.label,
                        fallback.start, fallback.end) if selected in {"all", "ytd", "month", "custom"} else fallback
        period_error = exc.message
    first, as_of = period.start, period.end
    accounts = c.accounts.list()
    if not accounts:
        from lightning.samples.profiles import sample_stories
        registry = c.currencies
        held = [row["code"] for row in registry.list()]
        base = c.base_currency
        common = ["USD", "EUR", "SAR", "AED", "GBP", "KWD"]
        names = {row["code"]: row["name"] for row in registry.suggestions()}
        order = [code for code in common if code in names] + [code for code in names if code not in common]
        return render(request, "dashboard/welcome.html", base=base, currencies=c.profile_currencies,
                      currency_choices=[(code, names[code]) for code in order],
                      held_currencies=[base] + [code for code in held if code != base],
                      extra_currencies=[code for code in held if code != base],
                      currencies_done=c.settings.get("setup_currencies_done") == "1",
                      editing_currencies=request.query_params.get("currencies") == "edit",
                      sample_stories=sample_stories(WELCOME_SAMPLES))
    # Every position figure comes from one calculation; see lightning/planning/position.py.
    period_position = c.position.at(as_of)
    # Your position follows the period too, as of its end (never past today): the cards then agree with the
    # Net worth chart beside them, which ends there (feedback ticket 80, 2026-10-14).
    position_day = min(as_of, today())
    position = period_position if position_day == as_of else c.position.at(position_day)
    net_worth = c.reporting.net_worth(as_of)
    account_contributions = _owned_account_type_rows(c, accounts, position_day)
    cash_accounts = [
        {"id": account.id, "label": account.label,
         "value": c.reporting.owned_account_value(account.id, position_day),
         "type": _ACCOUNT_TYPE_LABELS[account.account_type]}
        for account in accounts if account.account_type in {AccountType.CASH, AccountType.BANK}
    ]
    cash_accounts.extend({**row, "type": "Brokerage cash"}
                         for row in c.reporting.owned_brokerage_cash_by_account(position_day))
    owe = position.owe
    read_phone_sms(request, c)  # new bank messages join the review before Needs you is counted
    # One review inbox: every decision waiting on the user (lightning/workflows/review.py).
    inbox = ReviewInbox(c)
    attention = inbox.items(today())
    attention_groups = grouped(attention)
    setup = _setup_steps(c, accounts)
    change, change_reason = c.position.change_in_what_you_own(first, as_of, since_first_record=period.key == "all")
    change_label = (f"{label('change_in_what_you_own')} since your first record" if period.key == "all"
                    else label("change_in_what_you_own"))
    cash_flow = c.reporting.cash_flow(first, as_of)
    spending_groups = c.reporting.spending_by_category(first, as_of, depth=2)
    categorized_spending = sum((max(group.value, ZERO) for group in spending_groups), ZERO)
    expense_groups = []
    expense_group_index = {}
    for group in spending_groups:
        category = c.categories.get_by_code(group.code)
        parent = c.categories.get(category.parent_id) if category.parent_id else category
        query = urlencode({"category_id": category.id, "date_from": fmt_date(first),
                           "date_to": fmt_date(as_of)})
        child = {"label": category.name, "value": group.value,
                 "share": max(group.value, ZERO) / categorized_spending * 100
                 if categorized_spending else ZERO,
                 "category_id": category.id, "href": f"/transactions?{query}"}
        if parent.id not in expense_group_index:
            expense_group_index[parent.id] = {"id": parent.id, "label": parent.name,
                                              "children": [], "total": ZERO}
            expense_groups.append(expense_group_index[parent.id])
        expense_group_index[parent.id]["children"].append(child)
        expense_group_index[parent.id]["total"] += group.value
    # Give every L1 group its two largest L2 categories first, then fill the
    # remaining places with the next-largest categories overall, capped at 8.
    selected_ids = set()
    for parent in expense_groups:
        for child in parent["children"][:2]:
            if len(selected_ids) < 8:
                selected_ids.add(child["category_id"])
    remaining_children = sorted(
        (child for parent in expense_groups for child in parent["children"]
         if child["category_id"] not in selected_ids),
        key=lambda child: child["value"], reverse=True)
    for child in remaining_children:
        if len(selected_ids) >= 8:
            break
        selected_ids.add(child["category_id"])
    selected_groups = []
    for parent in expense_groups:
        children = [child for child in parent["children"] if child["category_id"] in selected_ids]
        if children:
            other_children = [child for child in parent["children"] if child["category_id"] not in selected_ids]
            selected_groups.append({
                "id": parent["id"], "label": parent["label"], "children": children,
                "total": parent["total"], "other_count": len(other_children),
                "other_total": sum((child["value"] for child in other_children), ZERO),
            })
    expense_groups = selected_groups
    closing_report = investment_period(c.db, c.accounts, c.assets, c.reporting, fmt_date(first), fmt_date(as_of))
    opening_report = closing_report["opening"]
    period_result = closing_report["result"]
    holdings_value = closing_report["value"]
    investment_cash = closing_report["investment_cash"]
    portfolio_value = holdings_value   # owner decision 2026-10-04: brokerage cash is not portfolio
    investment_report = {
        "holdings_value": holdings_value, "brokerage_cash": investment_cash,
        "portfolio_value": portfolio_value, "new_money": closing_report["net_money"],
        "income_collected": closing_report["dividends"],
        "period_result": period_result, "period_result_available": period_result is not None,
        "missing": closing_report["missing"] + opening_report["missing"],
        "at_cost": closing_report["at_cost"],
        "holdings_count": sum(1 for row in closing_report["holdings"] if row["price_source"] != "CASH"),
    }
    investment_holdings = [
        {"label": f"{row['asset']} · {row['account']}", "value": row["value"],
         "weight": (row["value"] / portfolio_value * 100
                    if row["value"] is not None and portfolio_value else None)}
        for row in sorted((row for row in closing_report["holdings"] if row["price_source"] != "CASH"),
                          key=lambda row: (row["value"] is None, -(row["value"] or ZERO), row["asset"]))[:5]
    ]
    investment_flow = closing_report["new_money"]
    investment_share = (investment_flow / cash_flow.inflows * 100
                        if cash_flow.inflows > ZERO else None)
    savings_rate = cash_flow.savings_rate
    networth_trend = visuals.net_worth_trend(c, as_of)
    stats = _period_stats(c, period, first, as_of, period_position, cash_flow, change, change_reason,
                          closing_report["net_money"], networth_trend, urlencode(request.query_params))
    # Answer first (guideline 3.33, A09): the change in net worth is the Lead's comparison, not a card of its own;
    # Safe to spend takes its place in the row while the position is today's.
    change_tile = stats.pop(0)
    current = as_of >= today()
    lead_change = page_status.change(change_tile["value"], period.key, current)
    if position_is_today := position_day == today():
        stats.insert(len(stats) - 1, _safe_tile(inbox.forecast))  # the phone's tiles (C06.1)
    # The PC's row is A08 cards, each against something: the savings rate against your usual one, the investing
    # rate against the period before, Safe to spend against free cash, Left in plan against the plan.
    if period.key == "month":
        before_to = first - timedelta(days=1)
        before_from, before_label = before_to.replace(day=1), month_of(before_to)
    else:
        before_to = first - timedelta(days=1)
        before_from, before_label = before_to - (as_of - first), "the period before"
    flow_before = c.reporting.cash_flow(before_from, before_to)
    added_before = investment_period(c.db, c.accounts, c.assets, c.reporting, fmt_date(before_from), fmt_date(before_to))["net_money"]
    plan_month = month_of(as_of)
    kpi_cards = kpis.overview(
        cash_flow, period_chip=_period_chip(period, first, as_of), rates=visuals.savings_rates(c, as_of),
        usual=c.reporting.usual_savings_rate(as_of), invest=investing_rate(closing_report["net_money"], cash_flow.net),
        invest_before=investing_rate(added_before, flow_before.net), before_label=before_label,
        money_added=closing_report["net_money"], forecast=inbox.forecast if position_is_today else None,
        plan=c.budgets.plan_summary(plan_month) if c.budgets.has_plan(plan_month) else None, month=plan_month,
        savings_href="#savings-squares", invest_href=f"/investments?{urlencode(request.query_params)}")
    status = page_status.overview(cash_flow.inflows, cash_flow.outflows, cash_flow.net, cash_flow.savings_rate,
                                  cash_flow.rate_says_nothing, period.key, current, bool(accounts))
    dates_note = ("so far" if current and period.key in ("month", "ytd") else "year to date" if period.key == "ytd" else "")
    recent_rows = c.reporting.register_page(None, "1900-01-01", "9999-12-31", 1, 10)[0]  # the phone leads with these (C11.1)
def _period_chip(period, first, as_of) -> str:
    """The period, short, as every card's chip names it."""
    partial = as_of.day < calendar.monthrange(as_of.year, as_of.month)[1]
    return {"month": month_of(first) + (" so far" if partial else ""), "ytd": "Year to date",
            "all": "All time"}.get(period.key, f"{fmt_date(first)} to {fmt_date(as_of)}")
