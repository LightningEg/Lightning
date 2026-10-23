"""The ledger check that runs before Undo or Redo replays a saved action (moved out of bootstrap, 9K)."""

from __future__ import annotations

import json
from types import SimpleNamespace

from lightning.core.errors import ValidationError
from lightning.core.ledger import PostingLine, validate_posting
from lightning.core.money import from_e6


def validate_replay(records, *, db, transactions, assets, accounts, reconciliation) -> None:
    """Refuse a replay that would leave an invalid posting, units or cash below zero, or a checked month changed.
    ``records`` are the undo rows the replay wrote; ``reconciliation`` is passed in because it sits above this layer."""
    ids = set()
    affected, days = {}, []
    for record in records:
        if record['table_name'] not in {'transactions', 'ledger_entries'}:
            continue
        for key in ('before_json', 'after_json'):
            row = json.loads(record[key]) if record[key] else {}
            value = row.get('transaction_id') if record['table_name'] == 'ledger_entries' else row.get('id')
            if value is not None:
                ids.add(value)
            if record['table_name'] == 'ledger_entries' and row:
                affected[(row['account_id'], row['asset_id'], row.get('owner_id'))] = row
                days.append(row['date'])
    lines = []
    for txn_id in ids:
        txn = transactions.repo.get(txn_id)
        if txn and not txn.is_void:
            postings = [PostingLine(
                account_id=line.account_id, asset_id=line.asset_id, quantity=line.quantity,
                effect=line.effect, unit_price=line.unit_price, fx_rate=line.fx_rate,
                category_id=line.category_id, memo=line.memo, amount=line.amount,
                amount_base=line.amount_base, is_cash=assets.get_asset(line.asset_id).is_cash,
                owner_id=line.owner_id) for line in txn.lines]
            validate_posting(postings)
            transactions._validate_linked_loan_amount(txn)
            lines.extend(txn.lines)
    if lines:
        transactions._check_holdings(lines)
    surviving, owner_keys = [], set()
    for (account_id, asset_id, owner_id), row in affected.items():
        if not db.scalar("SELECT 1 FROM financial_assets WHERE id=?", (asset_id,)):
            continue
        if not db.scalar("SELECT 1 FROM accounts WHERE id=?", (account_id,)):
            continue
        surviving.append(SimpleNamespace(account_id=account_id, asset_id=asset_id))
        asset = assets.get_asset(asset_id)
        if not asset.is_cash or owner_id is not None:
            owner_keys.add((account_id, asset_id, owner_id))
        if owner_id is not None or accounts.get(account_id).account_type.value == 'BROKERAGE':
            owner_keys.add((account_id, asset_id, None))
    if surviving:
        transactions._check_holdings(surviving)
    if owner_keys:
        transactions._validate_owner_balances([], min(days), extra_keys=owner_keys, ignore_before_day=True)
    for checked in db.all("SELECT * FROM reconciled_through"):
        if reconciliation.balance(checked["account_id"], checked["date"]) != from_e6(checked["bank_balance_e6"]):
            raise ValidationError("The balance changed. Check it against the bank again before closing.")
