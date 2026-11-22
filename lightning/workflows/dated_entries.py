"""Save the posting and its estimate-date choice as one local or synchronized command."""
from lightning.core.money import to_decimal


class DatedEntries:
    def __init__(self, db, transactions, budgets, reimbursements):
        self.db = db
        self.transactions = transactions
        self.budgets = budgets
        self.reimbursements = reimbursements

    def capture(self, estimate_date, date, account_id, amount, category_id, counterparty, notes, owner_id,
                unsorted=False, left_out=False, paid_for_work=False, expected=None, payer_id=None):
        with self.db.transaction():
            amount = to_decimal(amount, "amount")
            post = self.transactions.record_outflow if amount < 0 else self.transactions.record_inflow
            txn = post(date, account_id, abs(amount), category_id, counterparty=counterparty, notes=notes,
                       allow_system_category=unsorted, owner_id=owner_id)
            self.budgets.set_estimate_date(txn.id, estimate_date)
            if left_out:
                self.budgets.set_left_out(txn.id, True)
            if paid_for_work:
                self.reimbursements.create_work_claim(txn.id, expected, payer_id)
            return txn

    def record(self, estimate_date, **entry):
        with self.db.transaction():
            txn = self.transactions.record_in_account(**entry)
            self.budgets.set_estimate_date(txn.id, estimate_date)
            return txn

    def edit(self, txn_id, estimate_date, **entry):
        with self.db.transaction():
            txn = self.transactions.update_in_account(txn_id, **entry)
            self.budgets.set_estimate_date(txn.id, estimate_date)
            return txn

    def edit_metadata(self, txn_id, estimate_date, date, counterparty, notes):
        with self.db.transaction():
            txn = self.transactions.update_metadata(txn_id, date, counterparty, notes)
            self.budgets.set_estimate_date(txn.id, estimate_date)
            return txn
