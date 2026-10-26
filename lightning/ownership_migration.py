"""One-time migration of linked legacy custody records onto ledger lines."""

from lightning.core.dates import now_iso
from lightning.core.dates import parse_date
from lightning.core.ledger import split_line_e6
from lightning.core.refs import DocType, format_ref, ref_prefix
from lightning.transactions.repository import TransactionRepository


def post_cash_owner_adjustment(db, day: str, owner: str, owner_id: int, account_id: int,
                               cash_asset_id: int, amount_e6: int) -> int:
    """Post an ownership-only reallocation; paired lines leave account cash unchanged."""
    repo = TransactionRepository(db)
    date = parse_date(day).isoformat()
    parsed_day = parse_date(date)
    ref = format_ref(DocType.ADJ, parsed_day, repo.next_seq(ref_prefix(DocType.ADJ, parsed_day)))
    stamp = now_iso()
    cursor = db.execute("""INSERT INTO transactions(ref,type,date,description,counterparty,status,source,
                        notes,created_at,updated_at,counterparty_id)
                        VALUES(?,?,?,?,?,'POSTED','SYSTEM','',?,?,?)""",
                        (ref, "ADJ", date, f"Ownership attribution — {owner}", owner, stamp, stamp, owner_id))
    txn_id = int(cursor.lastrowid)
    for line_no, owner_line, quantity in ((1, owner_id, amount_e6), (2, None, -amount_e6)):
        db.execute("""INSERT INTO ledger_entries(transaction_id,line_no,date,account_id,asset_id,quantity_e6,
                     unit_price_e6,amount_e6,fx_rate_e6,amount_base_e6,effect,category_id,memo,cleared,owner_id)
                     VALUES(?,?,?,?,?,?,1000000,?,1000000,?,'INTERNAL',NULL,'Ownership attribution',0,?)""",
                   (txn_id, line_no, date, account_id, cash_asset_id, quantity, quantity, quantity, owner_line))
    return txn_id


def migrate_legacy_ownership(db):
    db.execute("CREATE TABLE IF NOT EXISTS ownership_migration_runs (name TEXT PRIMARY KEY, completed_at TEXT NOT NULL)")
    if db.scalar("SELECT 1 FROM ownership_migration_runs WHERE name='ledger_ownership_v2'"):
        return
    with db.transaction():
        rows = db.all("""SELECT m.transaction_id,m.owner,m.account_id,NULL AS asset_id,m.amount_e6 AS units_e6
                       FROM money_from_others m WHERE m.transaction_id IS NOT NULL
                       UNION ALL
                       SELECT e.transaction_id,e.owner,e.account_id,e.asset_id,e.units_e6
                       FROM investment_custody_events e WHERE e.transaction_id IS NOT NULL""")
        for legacy in rows:
            party = db.one("SELECT id FROM counterparties WHERE lower(name)=lower(?)", (legacy["owner"],))
            if not party:
                continue
            if legacy["asset_id"] is None:
                account = db.one("SELECT currency FROM accounts WHERE id=?", (legacy["account_id"],))
                asset = db.one("SELECT id FROM financial_assets WHERE is_cash=1 AND currency=?", (account["currency"],))
                asset_id = asset["id"] if asset else None
            else:
                asset_id = legacy["asset_id"]
            if asset_id is None:
                continue
            lines = db.all("""SELECT le.* FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id
                            WHERE le.transaction_id=? AND le.account_id=? AND le.asset_id=?
                              AND le.quantity_e6*? > 0 AND (le.owner_id IS NULL OR le.owner_id=?)
                            ORDER BY le.line_no""",
                           (legacy["transaction_id"], legacy["account_id"], asset_id,
                            legacy["units_e6"], party["id"]))
            remaining = abs(legacy["units_e6"])
            for line in lines:
                take = min(remaining, abs(line["quantity_e6"]))
                if not take:
                    continue
                total = abs(line["quantity_e6"])
                owned_amount, owned_base, rest_amount, rest_base = split_line_e6(
                    line["amount_e6"], line["fx_rate_e6"], take, total)
                if take == total:
                    db.execute("UPDATE ledger_entries SET owner_id=? WHERE id=?", (party["id"], line["id"]))
                else:
                    sign = 1 if line["quantity_e6"] > 0 else -1
                    db.execute("UPDATE ledger_entries SET quantity_e6=?,amount_e6=?,amount_base_e6=? WHERE id=?",
                               (line["quantity_e6"] - sign*take, rest_amount, rest_base, line["id"]))
                    db.execute("""INSERT INTO ledger_entries(transaction_id,line_no,date,account_id,asset_id,
                                 quantity_e6,unit_price_e6,amount_e6,fx_rate_e6,amount_base_e6,effect,
                                 category_id,memo,cleared,owner_id)
                                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                               (line["transaction_id"], line["line_no"]+10000, line["date"], line["account_id"],
                                line["asset_id"], sign*take, line["unit_price_e6"], owned_amount, line["fx_rate_e6"],
                                owned_base, line["effect"], line["category_id"], line["memo"], line["cleared"],
                                party["id"]))
                remaining -= take
                if not remaining:
                    break
        # Standalone legacy custody rows represented manual owner reallocation. Convert
        # each one to a zero-sum pair in the main ledger, preserving gross account cash.
        manual = db.all("SELECT * FROM money_from_others WHERE transaction_id IS NULL ORDER BY date,id")
        for row in manual:
            party = db.one("SELECT id FROM counterparties WHERE lower(name)=lower(?)", (row["owner"],))
            if not party:
                from lightning.counterparties import CounterpartyService
                party_id = CounterpartyService(db).create(row["owner"])
                party = {"id": party_id}
            currency = db.scalar("SELECT currency FROM accounts WHERE id=?", (row["account_id"],))
            cash_asset_id = db.scalar("SELECT id FROM financial_assets WHERE is_cash=1 AND currency=?", (currency,))
            if not cash_asset_id:
                continue
            txn_id = post_cash_owner_adjustment(db, row["date"], row["owner"], party["id"], row["account_id"],
                                                cash_asset_id, row["amount_e6"])
            db.execute("UPDATE money_from_others SET transaction_id=? WHERE id=?", (txn_id, row["id"]))
        db.execute("INSERT INTO ownership_migration_runs(name,completed_at) VALUES('ledger_ownership_v2',datetime('now'))")
