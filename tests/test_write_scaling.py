"""9I (Audit 3, section 1): a write and the reimbursements page do not grow with the whole history."""
from decimal import Decimal

import pytest

from lightning.core.errors import ValidationError
from lightning.core.refs import parse_ref
from lightning.transactions.domain import TxnFilter
from tests.test_reporting_performance import _add_synthetic_transfers


def _food(c):
    return c.categories.get_by_code("EXP.PERSONAL.FOOD")


def _cost(c, action):
    """(SELECT statements, SQLite VM steps in hundreds) one action runs."""
    statements, steps = [], [0]
    c.db.conn.set_trace_callback(statements.append)
    c.db.conn.set_progress_handler(lambda: steps.__setitem__(0, steps[0] + 1), 100)
    try:
        action()
    finally:
        c.db.conn.set_trace_callback(None)
        c.db.conn.set_progress_handler(None, 0)
    return sum(sql.lstrip().upper().startswith("SELECT") for sql in statements), steps[0]


def test_one_expense_runs_the_same_statements_whatever_the_account_history(c, setup):
    accounts, _ = setup

    def expense():
        c.transactions.record_outflow("2026-09-30", accounts["cib"].id, "1", _food(c).id, "Kiosk")

    expense()  # the first one creates the counterparty
    statements, steps = _cost(c, expense)
    _add_synthetic_transfers(c, {"cib": accounts["wallet"], "thndr": accounts["thndr"]}, count=600)
    elsewhere = _cost(c, expense)
    _add_synthetic_transfers(c, accounts, count=600, sequence_start=600)
    same_account = _cost(c, expense)
    assert elsewhere[0] == same_account[0] == statements
    # Other accounts' lines are not read: the negative-cash check sums this account on its own index.
    assert elsewhere[1] <= steps * 1.2 + 10


def test_the_negative_cash_check_reads_the_account_index():
    import inspect
    from lightning.transactions.service import TransactionService

    source = inspect.getsource(TransactionService._refuse_cash_below_zero)
    assert source.count("+le.asset_id=?") == 2  # keeps SQLite off ix_ledger_asset_date (every account's lines)


def test_an_edit_moved_later_still_counts_the_balance_before_it(c, setup):
    accounts, _ = setup
    txn = c.transactions.record_outflow("2026-09-10", accounts["cib"].id, "49000", _food(c).id)
    with pytest.raises(ValidationError, match="would leave CIB Current"):
        c.transactions.update_money(txn.id, "2026-09-25", accounts["cib"].id, "51000", _food(c).id)
    c.transactions.update_money(txn.id, "2026-09-25", accounts["cib"].id, "50000", _food(c).id)
    with pytest.raises(ValidationError, match="would leave CIB Current"):
        c.transactions.record_outflow("2026-09-26", accounts["cib"].id, "1", _food(c).id)
    assert c.reporting.account_balance(accounts["cib"].id) == Decimal("0")


def test_the_reimbursements_lists_do_not_read_per_expense(c, setup):
    accounts, _ = setup
    salary = c.categories.get_by_code("EXP.WORK.SALARY")

    def add(count):
        for n in range(count):
            c.transactions.record_outflow("2026-09-15", accounts["cib"].id, str(10 + n), _food(c).id)
            c.transactions.record_inflow("2026-09-16", accounts["cib"].id, str(5 + n), salary.id)

    def lists():
        return c.reimbursements.eligible_expenses(), c.reimbursements.available_receipts()

    add(2)
    few, _ = _cost(c, lists)
    add(25)
    many, _ = _cost(c, lists)
    expenses, receipts = lists()
    assert few == many
    assert len(expenses) >= 27 and len(receipts) >= 27


def test_next_seq_gives_the_same_sequence_as_a_prefix_match(c):
    for ref in ("OUT-2026-09-25-001", "OUT-2026-09-25-002", "OUT-2026-09-25-1000", "OUT-2026-09-24-007",
                "OUT-2026-09-26-003", "TRF-2026-09-25-009", "IN-2026-09-25-004"):
        c.db.execute("INSERT INTO transactions(ref,type,date,status,source,created_at,updated_at) "
                     "VALUES (?,?,?,'POSTED','MANUAL','x','x')", (ref, ref.split("-")[0], ref.split("-", 1)[1][:10]))
    for prefix in ("OUT-2026-09-25-", "IN-2026-09-25-", "TRF-2026-09-25-", "OUT-2026-09-27-", "BUY-2026-09-25-"):
        rows = c.db.all("SELECT ref FROM transactions WHERE ref LIKE ?", (prefix + "%",))
        assert c.transactions.repo.next_seq(prefix) == max((parse_ref(r["ref"])[2] for r in rows), default=0) + 1
    assert c.transactions.repo.next_seq("OUT-2026-09-25-") == 1001


def test_search_ids_are_the_listed_ids(c, setup):
    accounts, _ = setup
    c.transactions.record_outflow("2026-09-15", accounts["cib"].id, "120", _food(c).id, "Lunch")
    for text in ("Lunch", "120", "CIB", "nothing like it"):
        listed, _ = c.transactions.repo.list(TxnFilter(search=text, limit=100000))
        assert c.transactions.repo.ids(TxnFilter(search=text, limit=100000)) == [t.id for t in listed]


def test_duplicate_indexes_are_gone_and_their_columns_still_lead_another(c):
    dropped = {"ix_ledger_transaction": ("ledger_entries", ["transaction_id"]),
               "ix_price_asset_date": ("price_history", ["asset_id", "date"]),
               "ix_other_asset_valuations_account_date": ("other_asset_valuations", ["account_id", "effective_date"]),
               "ix_budgets_category_month": ("budgets", ["category_id", "month"]),
               "ix_budget_carryover_resets_month": ("budget_carryover_resets", ["category_id", "month"])}
    for name, (table, columns) in dropped.items():
        indexes = {row[1]: row[2] for row in c.db.conn.execute(f"PRAGMA index_list('{table}')")}
        assert name not in indexes
        leading = [[col[2] for col in c.db.conn.execute(f"PRAGMA index_info('{index}')")][:len(columns)]
                   for index, unique in indexes.items() if unique]
        assert columns in leading, table
