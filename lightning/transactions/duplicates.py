"""Possible duplicates (IV-3AY8): two active money-in, money-out or transfer entries with the same cash effect (same
accounts, assets, amounts and owners) dated at most three days apart, that the merge would accept, and that came in a way
a payment recorded twice does: one typed and one imported, two different imports, or typed twice the same day within
the hour. The same coffee bought on two days by hand is not offered. Each entry is in one
pair at most; a pair the person chose to keep (Keep both) is not offered again. The merge itself stays MergeService's,
preview first, so nothing here changes money."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from lightning.core.errors import LightningError

WINDOW_DAYS = 3          # a bank posts a card payment a day or two after it was typed in by hand
KEPT = "duplicates_kept"
TYPED_TWICE_SECONDS = 3600  # pairs answered Keep both, as "low-high" ids


def _kept(c) -> set[str]:
    try:
        value = json.loads(c.settings.get(KEPT) or "[]")
    except (TypeError, ValueError):
        return set()
    return {str(v) for v in value} if isinstance(value, list) else set()


def _twice(a: tuple, b: tuple, gap: int) -> bool:
    """Whether two entries came in as one payment recorded twice would: (source, import batch, created at)."""
    if a[0] != b[0]:
        return True                                   # typed by hand and imported (bank file or message)
    if a[0] == "IMPORT":
        return a[1] != b[1]                           # the same payment in two imports
    try:
        apart = abs((datetime.fromisoformat(a[2]) - datetime.fromisoformat(b[2])).total_seconds())
    except (TypeError, ValueError):
        return False
    return gap == 0 and apart <= TYPED_TWICE_SECONDS  # typed twice by mistake


def pair_key(a: int, b: int) -> str:
    low, high = sorted((int(a), int(b)))
    return f"{low}-{high}"


def possible_duplicates(c, since: date, until: date, limit: int = 10) -> list[tuple[int, int]]:
    """Pairs (keep, drop), the entry recorded first kept, newest pairs first. Only pairs MergeService would merge."""
    from .merge import MergeService
    rows = c.db.all(
        "SELECT t.id, t.date, t.source, COALESCE((SELECT MIN(b.batch_id) FROM bank_import_rows b WHERE b.transaction_id=t.id), 0) AS batch, t.created_at, le.account_id, le.asset_id, le.quantity_e6, le.effect, COALESCE(le.owner_id, 0) AS owner, "
        "fa.is_cash FROM transactions t JOIN ledger_entries le ON le.transaction_id=t.id "
        "JOIN financial_assets fa ON fa.id=le.asset_id "
        "WHERE t.status<>'VOID' AND t.type IN ('IN','OUT','TRF') AND t.date BETWEEN ? AND ? ORDER BY t.id",
        (since.isoformat(), until.isoformat()))
    lines: dict[int, list] = {}
    dated: dict[int, str] = {}
    cash: dict[int, bool] = {}
    origin: dict[int, tuple] = {}
    for r in rows:
        origin[r["id"]] = (r["source"], int(r["batch"]), r["created_at"])
        lines.setdefault(r["id"], []).append((int(r["account_id"]), int(r["asset_id"]), int(r["quantity_e6"]),
                                               r["effect"], int(r["owner"])))
        dated[r["id"]] = r["date"]
        cash[r["id"]] = cash.get(r["id"], True) and bool(r["is_cash"])
    by_effect: dict[tuple, list[int]] = {}
    for txn_id, parts in lines.items():
        if cash[txn_id]:
            by_effect.setdefault(tuple(sorted(parts)), []).append(txn_id)
    kept, merge, used = _kept(c), MergeService(c.transactions), set()
    found: list[tuple[str, int, int]] = []
    for ids in by_effect.values():
        for i, keep in enumerate(ids):
            for drop in ids[i + 1:]:
                if keep in used or drop in used or pair_key(keep, drop) in kept:
                    continue
                gap = abs((date.fromisoformat(dated[keep]) - date.fromisoformat(dated[drop])).days)
                if gap > WINDOW_DAYS or not _twice(origin[keep], origin[drop], gap):
                    continue
                try:
                    keep_txn, drop_txn = merge._validate_pair(keep, drop)
                except LightningError:
                    continue
                used.update((keep, drop))
                found.append((max(dated[keep], dated[drop]), keep_txn.id, drop_txn.id))
    found.sort(key=lambda f: (f[0], f[2]), reverse=True)
    return [(keep, drop) for _, keep, drop in found[:limit]]


def keep_both(c, keep_id: int, drop_id: int, on: date) -> None:
    """Keep both: the pair is not offered again. Only a pair still offered can be answered."""
    from lightning.core.errors import ValidationError
    if (keep_id, drop_id) not in possible_duplicates(c, on - timedelta(days=90), on, limit=1000):  # not money
        raise ValidationError("These two are no longer offered as possible duplicates.")
    with c.db.transaction(undo_label="Keep both"):
        c.settings.set(KEPT, json.dumps(sorted(_kept(c) | {pair_key(keep_id, drop_id)})))
