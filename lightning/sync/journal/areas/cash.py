"""Cash register. The journal's own register uses field groups (`finance.CashAdapter`);
the app's screens send these commands, preconditioned on the transaction row."""
from decimal import Decimal

from .spec import AMOUNT, DATE, LONG, TEXT, Command, items, listof, mapping, optional, ref

TABLES = ("counterparties", "transactions", "ledger_entries", "reconciled_through")
REGISTER = dict(account_id=ref("accounts"), date=DATE, amount=AMOUNT, category_id=optional(ref("categories")),
                other_account_id=optional(ref("accounts")), counterparty=TEXT, notes=LONG,
                owner_id=optional(ref("counterparties")))
TXN = ("transactions", "txn_id")
SELECTED = ("transactions", "txn_ids")
CHECKED = ("reconciled_through", ("account_id",))  # One row per account, named by its key.
# The account form's record: category and counterparty are optional (a transfer has neither).
ENTRY = dict(date=DATE, account_id=ref("accounts"), amount=AMOUNT, notes=LONG, owner_id=optional(ref("counterparties")))
# Ownership postings create a row, or (with txn_id) change the one they made: `creates` keeps an existing identity.
OWNERSHIP = dict(date=DATE, account_id=ref("accounts"), amount=AMOUNT, notes=LONG, txn_id=optional(ref("transactions")))
COMMANDS = {
    "transactions.record_in_account": Command("transactions.record_in_account", REGISTER | dict(description=TEXT),
                                              creates="transactions"),
    "transactions.update_in_account": Command("transactions.update_in_account", dict(txn_id=ref("transactions")) | REGISTER,
                                              target=TXN),
    "transactions.update_metadata": Command("transactions.update_metadata", dict(
        txn_id=ref("transactions"), date=DATE, counterparty=TEXT, notes=LONG), target=TXN),
    "transactions.update_expense_split": Command("transactions.update_expense_split", dict(
        txn_id=ref("transactions"), allocations=items(category_id=ref("categories"), amount=AMOUNT)), target=TXN,
        adapt=lambda values: values | dict(allocations=[(line["category_id"], line["amount"]) for line in values["allocations"]])),
    "transactions.void": Command("transactions.void", dict(txn_id=ref("transactions"), reason=TEXT), target=TXN),
    "transactions.restore": Command("transactions.restore", dict(txn_id=ref("transactions")), target=TXN),
    # Bulk actions on a selection: every selected row together is the precondition.
    "transactions.delete_many": Command("transactions.delete_many", dict(txn_ids=listof(ref("transactions"))), targets=SELECTED),
    "transactions.set_category": Command("transactions.set_category", dict(
        txn_ids=listof(ref("transactions")), category_id=ref("categories")), targets=SELECTED),
    "transactions.record_inflow_described": Command("transactions.record_inflow", ENTRY | dict(
        category_id=ref("categories"), description=TEXT, counterparty=TEXT), creates="transactions"),
    "transactions.record_outflow_described": Command("transactions.record_outflow", ENTRY | dict(
        category_id=ref("categories"), description=TEXT, counterparty=TEXT), creates="transactions"),
    "transactions.record_transfer": Command("transactions.record_transfer", dict(
        date=DATE, from_account_id=ref("accounts"), to_account_id=ref("accounts"), amount=AMOUNT, notes=LONG,
        owner_id=optional(ref("counterparties"))), creates="transactions"),
    "transactions.change_cash_ownership": Command("transactions.change_cash_ownership", OWNERSHIP | dict(
        from_owner_id=optional(ref("counterparties")), to_owner_id=optional(ref("counterparties"))),
        target=TXN, creates="transactions"),
    "transactions.record_expense_paid_by_person": Command("transactions.record_expense_paid_by_person", OWNERSHIP | dict(
        owner_id=ref("counterparties"), category_id=ref("categories")), target=TXN, creates="transactions"),
    # `changes` holds only what the person changed.
    "transactions.bulk_update": Command("transactions.bulk_update", dict(
        txn_ids=listof(ref("transactions")), changes=mapping(
            date=DATE, counterparty=TEXT, notes=LONG, category_id=optional(ref("categories")),
            owner_id=optional(ref("counterparties")))), targets=SELECTED),
    # The preview's fingerprint is made of the device's own row ids, so the home takes its own preview instead; the
    # kept transaction's row hash is the precondition. The merge also moves import-row links, so it needs the
    # bank-import tables to be synchronized.
    "transactions.merge": Command("transactions.merge", dict(
        keep_id=ref("transactions"), drop_id=ref("transactions"), fingerprint=TEXT), target=("transactions", "keep_id"),
        prepare=lambda c, values: values | dict(fingerprint=c.transactions.merge_preview(
            values["keep_id"], values["drop_id"]).fingerprint)),
    # Checking an account against the bank: the checked-through date, the cleared lines and a small adjustment.
    "reconciliation.adjust": Command("reconciliation.adjust", dict(
        account_id=ref("accounts"), through=DATE, bank_balance=AMOUNT), creates="transactions",
        adapt=lambda values: values | dict(bank_balance=Decimal(values["bank_balance"]))),  # The service wants a Decimal.
    "reconciliation.close": Command("reconciliation.close", dict(
        account_id=ref("accounts"), through=DATE, bank_balance=AMOUNT), target=CHECKED),
    "reconciliation.unlock": Command("reconciliation.unlock", dict(account_id=ref("accounts")), target=CHECKED),
}


# Keep the original wire shape readable for edits queued before descriptions were supported.
def _legacy_inflow(c, **values):
    return c.transactions.record_inflow(**values)


def _legacy_outflow(c, **values):
    return c.transactions.record_outflow(**values)


COMMANDS["transactions.record_inflow"] = Command(_legacy_inflow, ENTRY | dict(
    category_id=ref("categories"), counterparty=TEXT), creates="transactions")
COMMANDS["transactions.record_outflow"] = Command(_legacy_outflow, ENTRY | dict(
    category_id=ref("categories"), counterparty=TEXT), creates="transactions")
