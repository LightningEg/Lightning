"""Plans and budgets: bills, income, loans, instalment purchases, monthly budgets and carryover.

Budget category preferences use stable category codes. Payday funding carries the preview’s token; a changed
preview is refused. Automatic plan matching runs only through home automation.
"""
from .spec import AMOUNT, DATE, FLAG, INT, LONG, MONTH, TEXT, Command, choice, items, listof, optional, ref

TABLES = ("planned_items", "planned_payments", "loan_extra_payments", "installment_purchases", "budgets",
          "budget_carryover", "budget_carryover_resets", "cash_funding")

PLAN = dict(kind=choice("BILL", "SUBSCRIPTION", "INCOME", "LOAN"), name=TEXT, amount=AMOUNT,
            frequency=choice("ONCE", "WEEKLY", "MONTHLY", "QUARTERLY", "YEARLY"), interval_count=INT, start_date=DATE,
            end_date=optional(DATE), payment_count=optional(INT), account_id=optional(ref("accounts")),
            category_id=optional(ref("categories")), counterparty_id=optional(ref("counterparties")),
            principal=optional(AMOUNT), notes=LONG, weekend_move=choice("none", "before", "after"))
ITEM = ("planned_items", "item_id")
CATEGORY = ("categories", "category_id")  # A budget cell may not exist yet, so its category is the precondition.
CELLS = items(category=ref("categories"), amount=optional(AMOUNT), average_months=optional(INT))


def _cell(values):
    return values | dict(amount="" if values["amount"] is None else values["amount"])


def _amounts(lines):
    return {line["category"]: "" if line["amount"] is None else line["amount"] for line in lines}


def _month(values):
    lines = values["lines"]
    average = {line["category"]: line["average_months"] for line in lines if line["average_months"]}
    return dict(month=values["month"], amounts=_amounts(lines), only_this_month=values["only_this_month"],
                average_months=average or None)


def _fill(values):
    return dict(month=values["month"], amounts=_amounts(values["lines"]))


def _carryover(values):
    return dict(month=values["month"], settings={line["category"]: line["enabled"] for line in values["lines"]})


def _funding(values):
    return values | dict(amounts={str(line["category"]): line["amount"] for line in values["amounts"]},
                         reserve_additions={str(line["reserve"]): line["amount"] for line in values["reserve_additions"]})


# The columns a budget row keeps; a restored row gets a new id, since ids are local.
BUDGET_ROW = items(category_id=ref("categories"), month=TEXT, one_off=INT, amount_e6=optional(INT), created_at=TEXT,
                   updated_at=TEXT, average_months=optional(INT), income_percent_e6=optional(INT))

COMMANDS = {
    "plans.add_payee": Command("counterparties.create", dict(
        name=TEXT, default_category_id=optional(ref("categories")), alias=optional(TEXT), kind=optional(TEXT)),
        creates="counterparties"),
    "plans.add": Command("planning.create", dict(
        PLAN, month_day=optional(INT), match_window_days=optional(INT), match_tolerance_pct=optional(INT)),
        creates="planned_items"),
    "plans.update": Command("planning.update", dict(
        PLAN, item_id=ref("planned_items"), match_window_days=INT, match_tolerance_pct=INT), target=ITEM),
    "plans.set_amount": Command("planning.set_amount", dict(item_id=ref("planned_items"), amount=AMOUNT), target=ITEM),
    "plans.start_after_paid": Command("planning.start_after_paid", dict(item_id=ref("planned_items")), target=ITEM),
    "plans.remove": Command("planning.remove", dict(item_id=ref("planned_items")), target=ITEM),
    "plans.pay": Command("planning.record_payment", dict(
        item_id=ref("planned_items"), due_date=DATE, date_paid=DATE, amount=AMOUNT,
        account_id=optional(ref("accounts"))), target=ITEM),
    "plans.link_payment": Command("planning.mark_paid", dict(
        item_id=ref("planned_items"), due_date=DATE, transaction_id=ref("transactions")), target=ITEM),
    "plans.skip": Command("planning.skip", dict(item_id=ref("planned_items"), due_date=DATE), target=ITEM),
    "plans.reopen": Command("planning.reopen", dict(item_id=ref("planned_items"), due_date=DATE), target=ITEM),
    "planning.create_purchase": Command("planning.create_purchase", dict(
        name=TEXT, price=AMOUNT, fee=AMOUNT, months=INT, first_date=DATE, account_id=optional(ref("accounts")),
        counterparty_id=optional(ref("counterparties"))), creates="planned_items"),
    "planning.record_early_payment": Command("planning.record_early_payment", dict(
        item_id=ref("planned_items"), principal=AMOUNT, fee=AMOUNT, date_paid=DATE,
        account_id=optional(ref("accounts")), expected_remaining=AMOUNT), target=ITEM),
    "budgets.set": Command("budgets.set_budget", dict(
        category_id=ref("categories"), month=MONTH, amount=optional(AMOUNT), only_this_month=FLAG,
        average_months=optional(INT)), target=CATEGORY, adapt=_cell),
    "budgets.set_income_percent": Command("budgets.set_income_percentage", dict(
        category_id=ref("categories"), month=MONTH, percent=AMOUNT, only_this_month=FLAG), target=CATEGORY),
    "budgets.save_month": Command("budgets.save_month", dict(month=MONTH, lines=CELLS, only_this_month=FLAG),
                                  adapt=_month),
    "budgets.apply_fill": Command("budgets.apply_fill", dict(month=MONTH, lines=CELLS), adapt=_fill),
    "budgets.move_room": Command("budgets.move_room", dict(
        month=MONTH, to_id=ref("categories"), from_id=ref("categories"), amount=AMOUNT)),
    "budgets.set_carryover": Command("budgets.set_carryover", dict(
        month=MONTH, lines=items(category=ref("categories"), enabled=FLAG)), adapt=_carryover),
    "budgets.reset_carryover": Command("budgets.reset_carryover", dict(
        category_id=ref("categories"), month=MONTH), target=CATEGORY),
    "budgets.set_one_off": Command("budgets.set_one_off", dict(category_id=ref("categories"), one_off=FLAG), target=CATEGORY),
    "budgets.set_recurring_income": Command("budgets.set_recurring_income", dict(
        category_id=ref("categories"), recurring=FLAG), target=CATEGORY),
    "budgets.set_emergency_basis": Command("budgets.set_emergency_basis", dict(basis=choice("spending", "income"))),
    "budgets.restore_rows": Command("budgets.restore_rows", dict(category_ids=listof(ref("categories")), rows=BUDGET_ROW)),
    "funding.apply": Command("funding.apply", dict(
        fingerprint=TEXT, amounts=items(category=ref("categories"), amount=TEXT),
        reserve_additions=items(reserve=ref("cash_reserves"), amount=TEXT)), adapt=_funding),
    "planning.not_recurring": Command("planning.not_recurring", dict(counterparty_id=ref("counterparties"))),
}


# Retain previously queued wire actions while native routes use the service methods.
def _purchase(c, **values):
    return c.planning.create_purchase(**values)


def _early(c, **values):
    return c.planning.record_early_payment(**values)


COMMANDS["plans.buy_in_instalments"] = Command(_purchase, **{
    key: value for key, value in vars(COMMANDS["planning.create_purchase"]).items() if key != "call"})
COMMANDS["plans.pay_loan_early"] = Command(_early, **{
    key: value for key, value in vars(COMMANDS["planning.record_early_payment"]).items() if key != "call"})
