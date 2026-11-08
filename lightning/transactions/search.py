"""Read-only transaction search, tags and capture suggestions.

The facade supplies its existing policy constants on each call. No posting,
revision, submission or save ownership belongs to this module.
"""
from datetime import timedelta

from lightning.categories.domain import Movement
from lightning.core.dates import fmt_date, parse_date, today

from .domain import TxnFilter
from .tags import normalize as normal_tag, tags_in


def tagged_notes(repo) -> list:
    return repo.db.all("SELECT id, notes FROM transactions WHERE status='POSTED' AND instr(notes, '#') > 0")


def tag_transaction_ids(repo, tag: str) -> set[int]:
    """Posted transactions whose notes carry the tag (#eid matches #Eid, never #eid2026)."""
    tag = normal_tag(tag)
    return {int(row["id"]) for row in tagged_notes(repo) if tag and tag in tags_in(row["notes"])}


def tags(repo) -> list[tuple[str, int]]:
    """Every tag in use, with how many posted transactions carry it, most used first."""
    counts: dict[str, int] = {}
    for row in tagged_notes(repo):
        for tag in tags_in(row["notes"]):
            counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def search_ids(repo, counterparties, text: str) -> set[int]:
    """Transaction ids matching a search (posted ones)."""
    clause, params = repo._where(TxnFilter(search=text))
    return {int(row["id"]) for row in repo.db.all(f"SELECT t.id FROM transactions t WHERE {clause}", tuple(params))}


def usual_categories(repo, *, window: int, minimum: int, days: int) -> dict[str, dict]:
    """The category each counterparty is usually filed under, when it has one: picked in at least
    3 of its last 5 transactions in the 180 days before its newest, or in all of them while it has
    2 to 4. {name: {category_id, count, total}}."""
    tally: dict[str, dict[int, list]] = {}
    totals: dict[str, set] = {}
    newest: dict = {}
    for row in repo.recent_categories(window):
        name = row["counterparty"]
        day = parse_date(row["date"])
        newest.setdefault(name, day)  # rows come newest first
        if (newest[name] - day).days > days:
            continue
        seen = tally.setdefault(name, {})
        totals.setdefault(name, set()).add(row["id"])
        entry = seen.setdefault(row["category_id"], [0, (row["date"], row["id"])])
        entry[0] += 1
        entry[1] = max(entry[1], (row["date"], row["id"]))
    usual = {}
    for name, seen in tally.items():
        category_id, (count, _) = max(seen.items(), key=lambda kv: (kv[1][0], kv[1][1]))
        total = len(totals[name])
        if count >= minimum or (2 <= total < window and count == total):
            usual[name] = {"category_id": category_id, "count": count, "total": total}
    return usual


def usual_capture_categories(repo, categories, kind: str, limit: int, *, days: int, hour: int | None = None) -> list[int]:
    """The categories the Add sheet offers first as chips (3AN3): what this person files money of that kind
    under most often in the last 180 days, then the other categories in the tree's own order until there are
    ``limit``. kind is "out" or "in"; transfers have no category. ``hour`` (local, 0-23) puts what was typed by hand in
    the same part of the day first. Ids only; the page names them."""
    if kind not in ("out", "in"):
        return []
    movement = Movement.OUTFLOW if kind == "out" else Movement.INFLOW
    allowed = [c for c in categories.pickable()
               if c.movement == movement and not c.is_system and c.code != "EXP.SYSTEM.CUSTODY"
               and c.code not in ("EXP.UNACCOUNTED", "INC.UNACCOUNTED")]
    by_id = {c.id: c for c in allowed}
    since = fmt_date(today() - timedelta(days=days))
    band = None if hour is None else ((5, 10) if 5 <= hour <= 10 else (11, 16) if 11 <= hour <= 16 else (17, 22) if 17 <= hour <= 22 else None)
    used = [int(row["category_id"]) for row in repo.category_use(movement.value, since, band)]
    chosen = [category_id for category_id in used if category_id in by_id][:limit]
    for category in allowed:  # a thin history: the tree's own order fills the rest
        if len(chosen) >= limit:
            break
        if category.id not in chosen and not category.is_root:
            chosen.append(category.id)
    return chosen


def usual_account(repo, candidates: list[int]) -> int | None:
    """The account Add opens on when none was used last (3AN3): the one that took most of this person's own
    entries in the last 90 days among ``candidates``, else the first of them."""
    if not candidates:
        return None
    since = fmt_date(today() - timedelta(days=90))
    for row in repo.account_use(since):
        if int(row["account_id"]) in candidates:
            return int(row["account_id"])
    return candidates[0]
