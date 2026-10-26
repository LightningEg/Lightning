"""7O: the bank-import preview reads the usual categories once, so its queries grow by a fixed number per row."""
from __future__ import annotations


def _stage(c, account_id, rows: int, name: str):
    lines = ["Date,Amount,Counterparty,Notes"] + [f"2026-09-{1 + i % 28:02d},-{10 + i},Shop {i},row {i}"
                                                  for i in range(rows)]
    batch_id, _ = c.bank_imports.stage(account_id, name, ("\n".join(lines) + "\n").encode())
    return batch_id


def _preview(c, batch_id, monkeypatch):
    calls, statements = [], []
    real = c.transactions.usual_categories
    monkeypatch.setattr(c.transactions, "usual_categories", lambda: calls.append(1) or real())
    c.db.conn.set_trace_callback(statements.append)
    try:
        c.bank_imports.preview(batch_id)
    finally:
        c.db.conn.set_trace_callback(None)
        monkeypatch.undo()
    return len(calls), len(statements)


def test_preview_reads_usual_categories_once_and_scales_per_row(c, setup, monkeypatch):
    account_id = setup[0]["cib"].id
    small, large = _stage(c, account_id, 5, "small.csv"), _stage(c, account_id, 25, "large.csv")
    small_calls, small_sql = _preview(c, small, monkeypatch)
    large_calls, large_sql = _preview(c, large, monkeypatch)
    assert small_calls == large_calls == 1
    # 20 extra rows cost the same per row as the first 5 rows beyond the preview's fixed reads.
    per_row = (large_sql - small_sql) / 20
    assert per_row == int(per_row)
    medium = _stage(c, account_id, 15, "medium.csv")
    assert _preview(c, medium, monkeypatch)[1] == small_sql + 10 * per_row
