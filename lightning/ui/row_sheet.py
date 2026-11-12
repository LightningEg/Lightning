"""A transaction's own sheet: what it shows, and the To sort list it walks. Shared by the routes that file a row and
the phone router that opens the sheet (3AY11), so the phone layer never imports the PC routes."""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import Request

from lightning.core.refs import DOC_LABELS
from lightning.transactions.figures import cash_amount

FAR_PAST, FAR_FUTURE = "1900-01-01", "9999-12-31"


SORT_KEYS = ("sort", "sa", "sf", "st")  # the To sort list a sheet was opened from: its account and days (3AN3)


def sort_args(source) -> dict:
    """The To sort queue a sheet belongs to, from the query or the form: {} when the row was not opened from it."""
    if not str(source.get("sort", "")):
        return {}
    return {"sort": "1", "sa": str(source.get("sa", ""))[:12], "sf": str(source.get("sf", ""))[:10],
            "st": str(source.get("st", ""))[:10]}


def sort_queue(c, args: dict) -> list[int]:
    """The rows still to sort in that list, newest first."""
    account = int(args["sa"]) if args.get("sa", "").isdigit() else None
    day = lambda text, fallback: text if len(text) == 10 else fallback  # noqa: E731
    return c.reporting.unsorted_in_order(account, day(args.get("sf", ""), FAR_PAST), day(args.get("st", ""), FAR_FUTURE))


def next_in_queue(queue: list[int], current: int) -> int | None:
    """The row after this one in the queue (older), else the first one left: the sheet walks the list and wraps."""
    older = [txn_id for txn_id in queue if txn_id < current and txn_id != current]
    others = [txn_id for txn_id in queue if txn_id != current]
    return (older or others or [None])[0]


def return_to(value) -> str:
    """Where a sheet goes back to: a page of this app, else the Transactions list."""
    value = str(value or "")
    return value if value.startswith("/") and not value.startswith("//") else "/transactions"


def category_for_party(party, usual: dict, pickable: set) -> int | None:
    """The category set on the counterparty, else the one it is usually filed under, if it has one."""
    if not party:
        return None
    chosen = party["default_category_id"] or (usual.get(party["name"]) or {}).get("category_id")
    return int(chosen) if chosen and int(chosen) in pickable else None


def sheet_context(request: Request, c, txn) -> dict:
    """What a transaction's own sheet shows (3AD2): who, how much, when and where, its category with the plan left, the
    note; for a row nobody has sorted, the usual categories to pick from. Figures come from the services."""
    cash = [line for line in txn.lines if c.assets.get_asset(line.asset_id).is_cash]
    transfer = txn.type.value == "TRF"
    source = next((line for line in cash if line.quantity < 0), cash[0])
    account = c.accounts.get(source.account_id)
    target = next((c.accounts.get(line.account_id) for line in cash if line.account_id != source.account_id), None) \
        if transfer else None
    amount = abs(source.quantity) if transfer else cash_amount(cash)
    category_ids = sorted({line.category_id for line in cash if line.category_id})
    category = c.categories.get(category_ids[0]) if len(category_ids) == 1 else None
    unsorted = not transfer and (not category_ids or (category is not None and category.code.endswith("UNACCOUNTED")))
    kind = "move" if transfer else "out" if source.quantity < 0 else "in"
    plan = None
    if kind == "out" and category is not None and not unsorted:
        plan = c.budgets.plan_left(category.id, txn.date[:7], schedule=c.schedules.view())
    chips, other = [], []
    if unsorted or request.query_params.get("change"):
        movement = "out" if kind == "out" else "in"
        usual = c.transactions.usual_capture_categories(movement, 5)
        party = c.counterparties.resolve(txn.counterparty) if txn.counterparty else None
        pickable = {item.id for item in c.categories.pickable()}
        learned = category_for_party(party, c.transactions.usual_categories(), pickable)
        if learned and c.categories.get(learned).movement.value == ("OUTFLOW" if movement == "out" else "INFLOW"):
            usual = [learned] + [item for item in usual if item != learned]  # not money: list glue
        chips = [{"id": item, "label": c.categories.get(item).name} for item in usual[:5]]
        other = [item for item in c.categories.pickable()
                 if item.movement.value == ("OUTFLOW" if movement == "out" else "INFLOW") and not item.is_system]
    repeat = {"kind": "transfer" if transfer else kind, "amount": str(amount), "counterparty": txn.counterparty or "",
              "category_id": category.id if category is not None and not transfer else "",
              "to_account_id": target.id if target is not None else "", "repeat": 1}
    repeat_url = f"/accounts/{account.id}/transaction/new?" + urlencode({k: v for k, v in repeat.items() if v != ""})
    args = sort_args(request.query_params)
    queue = sort_queue(c, args) if args else []
    skip = next_in_queue(queue, txn.id) if queue else None
    return dict(txn=txn, kind=kind, account=account, target=target, repeat_url=repeat_url, amount=amount, currency=account.currency,
                category=category, unsorted=unsorted, plan=plan, chips=chips, other=other, sort=args, hide_global_error=True,
                sort_query=urlencode(args), skip=skip, split=txn.type.value == "OUT" and len(cash) == 1 and not unsorted,
                return_to=return_to(request.query_params.get("return_to")), who=txn.counterparty or txn.description or "", label=DOC_LABELS.get(txn.type, "Transaction"))


def sheetable(c, txn) -> bool:
    """Money out, money in or a move of cash that still stands: the rows that have a sheet. Anything else (a trade, a
    value update, a void row) opens its full page."""
    return (txn.type.value in {"OUT", "IN", "TRF"} and not txn.is_void
            and any(c.assets.get_asset(line.asset_id).is_cash for line in txn.lines))
