"""Shared balance walks preserve each caller's existing daily/row-order policy.

The former SQL window is an independent oracle for the streamed holdings floor.
"""
from collections import defaultdict
import random

import pytest

from lightning.core.balances import running_balances
from lightning.database.connection import Database
from lightning.transactions.repository import TransactionRepository


@pytest.fixture
def history(tmp_path):
    db = Database(tmp_path / "balance-history.db")
    db.execute("CREATE TABLE transactions(id INTEGER PRIMARY KEY, status TEXT)")
    db.execute("CREATE TABLE ledger_entries(date TEXT, transaction_id INTEGER, line_no INTEGER, "
               "account_id INTEGER, asset_id INTEGER, quantity_e6 INTEGER)")
    db.execute("CREATE INDEX history_order ON ledger_entries(account_id, asset_id, date)")
    yield db, TransactionRepository(db)
    db.close()


def _add(db, rows):
    for tid in sorted({r[1] for r in rows}):
        db.execute("INSERT INTO transactions VALUES (?, 'POSTED')", (tid,))
    for day, tid, line, quantity in rows:
        db.execute("INSERT INTO ledger_entries VALUES (?,?,?,1,1,?)", (day, tid, line, quantity))


def _window_oracle(db):
    row = db.one(
        "SELECT q, date FROM (SELECT le.date, SUM(le.quantity_e6) OVER (ORDER BY le.date, t.id, le.line_no)"
        " AS q FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id "
        "WHERE t.status='POSTED' AND le.account_id=1 AND le.asset_id=1) ORDER BY q LIMIT 1")
    return (int(row["q"]), row["date"]) if row else (0, None)


@pytest.mark.parametrize("rows, expected", [
    ([], (0, None)),
    ([("2026-01-01", 1, 1, 10)], (10, "2026-01-01")),
    ([("2026-01-02", 2, 2, 5), ("2026-01-01", 1, 1, 10),
      ("2026-01-02", 2, 1, -12)], (-2, "2026-01-02")),
    ([("2026-01-01", 1, 1, 10), ("2026-01-02", 2, 1, -15),
      ("2026-01-03", 3, 1, 5), ("2026-01-04", 4, 1, -5)], (-5, "2026-01-02")),
])
def test_streamed_holding_floor_matches_old_window_and_earliest_tie(history, rows, expected):
    db, repo = history
    _add(db, rows)
    assert repo.lowest_running_quantity(1, 1) == _window_oracle(db) == expected


def test_holding_floor_filters_void_other_accounts_and_assets(history):
    db, repo = history
    _add(db, [("2026-01-01", 1, 1, 10), ("2026-01-02", 2, 1, -999)])
    db.execute("UPDATE transactions SET status='VOID' WHERE id=2")
    db.execute("INSERT INTO ledger_entries VALUES ('2026-01-01',1,2,2,1,-999)")
    db.execute("INSERT INTO ledger_entries VALUES ('2026-01-01',1,3,1,2,-999)")
    assert repo.lowest_running_quantity(1, 1) == _window_oracle(db) == (10, "2026-01-01")


def test_seeded_mixed_history_matches_sql_window_at_integer_precision(history):
    db, repo = history
    rng = random.Random(2317)
    rows = [(f"2026-01-{rng.randrange(1, 29):02}", i + 1, 1, rng.randrange(-10**15, 10**15)) for i in range(500)]
    rng.shuffle(rows)
    _add(db, rows)
    assert repo.lowest_running_quantity(1, 1) == _window_oracle(db)


def test_daily_and_row_checks_share_the_walk_without_changing_their_order_policy():
    rows = [("2026-01-01", 10), ("2026-01-02", -12), ("2026-01-02", 5)]
    daily = defaultdict(int)
    for day, quantity in rows:
        daily[day] += quantity
    assert min(s.after for s in running_balances(rows)) == -2
    assert min(s.after for s in running_balances(sorted(daily.items()))) == 3
    assert [(s.before, s.after) for s in running_balances(rows, opening=20)] == [(20, 30), (30, 18), (18, 23)]
