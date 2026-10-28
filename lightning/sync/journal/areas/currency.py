"""Currencies, rates, foreign accounts, conversions and money set aside (reserves)."""
from .spec import AMOUNT, DATE, LONG, RATE, TEXT, Command, choice, optional, ref

TABLES = ("registered_currencies", "fx_rates", "cash_reserves", "reserve_transaction_links", "reserve_allocation_history")
# A rate row keeps its identity when a service rewrites it (trade rates are rebuilt after every conversion).
NATURAL = {"fx_rates": ("date", "base", "quote", "source")}
# History rows name their reserve without a declared foreign key.
REFS = {"reserve_allocation_history": {"reserve_id": "cash_reserves"}}

RESERVE = dict(name=TEXT, target=AMOUNT, due_date=optional(DATE), recurrence=choice("NONE", "WEEKLY", "MONTHLY", "YEARLY"),
               counterparty_id=optional(ref("counterparties")), category_id=optional(ref("categories")),
               account_id=optional(ref("accounts")))
CONVERSION = dict(date=DATE, from_account_id=ref("accounts"), to_account_id=ref("accounts"), sent=AMOUNT, received=AMOUNT,
                  fee=optional(AMOUNT), description=TEXT, notes=LONG)
# The emergency fund shortcut creates or edits, so it has no single target. Not covered: removing a currency (no
# service), deleting a reserve (its history would name a removed reserve) and the profile currency (a setting).
COMMANDS = {
    "currencies.register": Command("currencies.register", dict(code=TEXT, name=optional(TEXT))),
    "currencies.save_rate": Command("fx.save", dict(currency=TEXT, day=DATE, rate=RATE)),
    "transactions.record_conversion": Command("transactions.record_conversion", CONVERSION, creates="transactions"),
    "transactions.update_conversion": Command("transactions.update_conversion", dict(txn_id=ref("transactions"), **CONVERSION),
                                              target=("transactions", "txn_id")),
    "reserves.create": Command("reserves.create", dict(RESERVE, kind=choice("PROJECT", "EMERGENCY")), creates="cash_reserves"),
    "reserves.update": Command("reserves.update", dict(reserve_id=ref("cash_reserves"), **RESERVE),
                               target=("cash_reserves", "reserve_id")),
    "reserves.allocate": Command("reserves.allocate", dict(reserve_id=ref("cash_reserves"), amount=AMOUNT),
                                 target=("cash_reserves", "reserve_id")),
    "reserves.complete": Command("reserves.complete", dict(reserve_id=ref("cash_reserves")),
                                 target=("cash_reserves", "reserve_id")),
    "reserves.link_payment": Command("reserves.set_expense_link", dict(
        reserve_id=ref("cash_reserves"), transaction_id=ref("transactions"), amount=AMOUNT),
        target=("cash_reserves", "reserve_id")),
    "reserves.unlink_payment": Command("reserves.unlink_expense", dict(
        reserve_id=ref("cash_reserves"), transaction_id=ref("transactions")), target=("cash_reserves", "reserve_id")),
    "reserves.set_emergency_fund": Command("reserves.set_emergency_fund", dict(amount=AMOUNT, salary_target=AMOUNT)),
}
