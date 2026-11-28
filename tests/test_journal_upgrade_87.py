import pytest

from lightning.sync.journal.codec import JournalError, canonical
from lightning.sync.journal.upgrades import _upgrade_87_hashes
from test_journal_finance import devices  # noqa: F401


def test_upgrading_hashes_requires_matching_old_contents_and_can_resume(devices):
    home, _ = devices
    db = home.store.db
    rows = home.adapter.rows
    # Use a real planned item, including the schema 95 nullable rate columns.
    from lightning.planning.domain import PlanKind, Frequency
    with home.adapter.writing():
        home.c.planning.create(kind=PlanKind.BILL, name="Rent", amount="50",
                            frequency=Frequency.MONTHLY, start_date="2026-01-01")
    table = rows.tables["planned_items"]
    row = db.one("SELECT * FROM planned_items LIMIT 1")
    key = rows.identity(table, row)
    values = rows.encode(table, row)
    slot = "planned_items:" + canonical(key).decode()
    previous = dict(values)
    del previous["interest_rate_e6"], previous["rate_kind"]
    db.execute("INSERT OR REPLACE INTO journal_fp VALUES(?,?)", (slot, "0" * 64))
    with pytest.raises(JournalError, match="differs"):
        _upgrade_87_hashes(rows)
    db.execute("UPDATE journal_fp SET hash=? WHERE uuid=?", (rows.row_hash(table.name, key, previous), slot))
    _upgrade_87_hashes(rows)
    _upgrade_87_hashes(rows)
    assert db.scalar("SELECT hash FROM journal_fp WHERE uuid=?", (slot,)) == rows.row_hash(table.name, key, values)
