"""Attach a home-local undo recorder to accepted journal actions."""
from __future__ import annotations


_ACTION_LABELS = {
    "transactions.record_inflow_described": "Record income",
    "transactions.record_outflow_described": "Record expense",
    "accounts.open": "Open account", "transactions.record_in_account": "Record transaction",
    "transactions.record_outflow": "Record expense", "transactions.record_inflow": "Record income",
    "transactions.record_transfer": "Record transfer", "transactions.record_conversion": "Exchange currency",
    "planning.create_purchase": "Create installment purchase",
    "planning.record_early_payment": "Record early payment", "salary_setup.set_up_salary": "Set up salary",
}


def action_label(command_name: str) -> str:
    """A short, user-facing history label without service namespaces."""
    return _ACTION_LABELS.get(command_name, command_name.rsplit(".", 1)[-1].replace("_", " ").capitalize())


def _validate_financial_history(container, records):
    """Keep undo from leaving an invalid posting, holding, owner balance, or reconciliation."""
    import json
    from types import SimpleNamespace

    from lightning.core.errors import ValidationError
    from lightning.core.ledger import PostingLine, validate_posting
    from lightning.core.money import from_e6

    db, transactions, assets, accounts = (container.db, container.transactions,
                                           container.assets, container.accounts)
    transaction_ids, affected, days = set(), {}, []
    for record in records:
        if record["table_name"] not in {"transactions", "ledger_entries"}:
            continue
        for field in ("before_json", "after_json"):
            row = json.loads(record[field]) if record[field] else {}
            identity = row.get("transaction_id") if record["table_name"] == "ledger_entries" else row.get("id")
            if identity is not None:
                transaction_ids.add(identity)
            if record["table_name"] == "ledger_entries" and row:
                affected[(row["account_id"], row["asset_id"], row.get("owner_id"))] = row
                days.append(row["date"])

    lines = []
    for transaction_id in transaction_ids:
        txn = transactions.repo.get(transaction_id)
        if txn and not txn.is_void:
            postings = [PostingLine(
                account_id=line.account_id, asset_id=line.asset_id, quantity=line.quantity,
                effect=line.effect, unit_price=line.unit_price, fx_rate=line.fx_rate,
                category_id=line.category_id, memo=line.memo, amount=line.amount,
                amount_base=line.amount_base, is_cash=assets.get_asset(line.asset_id).is_cash,
                owner_id=line.owner_id,
            ) for line in txn.lines]
            validate_posting(postings)
            lines.extend(txn.lines)
    if lines:
        transactions._check_holdings(lines)

    surviving, owner_keys = [], set()
    for (account_id, asset_id, owner_id), _row in affected.items():
        if not db.scalar("SELECT 1 FROM financial_assets WHERE id=?", (asset_id,)):
            continue
        if not db.scalar("SELECT 1 FROM accounts WHERE id=?", (account_id,)):
            continue
        surviving.append(SimpleNamespace(account_id=account_id, asset_id=asset_id))
        asset = assets.get_asset(asset_id)
        if not asset.is_cash or owner_id is not None:
            owner_keys.add((account_id, asset_id, owner_id))
        if owner_id is not None or accounts.get(account_id).account_type.value == "BROKERAGE":
            owner_keys.add((account_id, asset_id, None))
    if surviving:
        transactions._check_holdings(surviving)
    if owner_keys and days:
        transactions._validate_owner_balances([], min(days), extra_keys=owner_keys, ignore_before_day=True)
    for checked in db.all("SELECT * FROM reconciled_through"):
        if container.reconciliation.balance(checked["account_id"], checked["date"]) != from_e6(checked["bank_balance_e6"]):
            raise ValidationError("The balance changed. Check it against the bank again before closing.")


def attach_home_history(container, adapter):
    """Enable home-only history without attaching it to ``db.undo`` transactions.

    The adapter owns the narrow confirmation scope. Its temporary triggers cover
    only synchronized tables and start only while an accepted user action runs.
    """
    if adapter.store.config.get("role") != "home":
        container.undo = None
        return None
    from lightning.undo import UndoService

    service = UndoService(container.db, container.audit)
    service.journal_fingerprint = adapter.fingerprint
    service.validate = lambda records: _validate_financial_history(container, records)
    adapter.attach_history(service)
    return service
