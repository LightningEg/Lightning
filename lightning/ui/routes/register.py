"""The register — an account's transactions with a quick-add bar and in-place editing.

One signed Amount (+ money in, − money out). "Counterparty" is the person or account on the other side;
typing or picking one of your own accounts there makes the row a transfer.
Used by one account (/accounts/{id}) and by all accounts (/transactions). Only calls services.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode

from fastapi import Request

from lightning.accounts.domain import AccountType, INVESTMENT_ACCOUNT_TYPES
from lightning.accounts.valuations import OtherAssetValuationRepository
from lightning.categories.domain import Movement
from lightning.assets.catalog import instruments as catalog_instruments
from lightning.core.codes import slug
from lightning.core.dates import fmt_date, parse_date, parse_month, today
from lightning.core.errors import ConflictError, LightningError, ValidationError
from lightning.core.money import ZERO, fmt, to_decimal
from lightning.core.refs import DocType
from lightning.transactions.tags import normalize as normal_tag

from ..web import container, render

ENTRY_FIELDS = ("date", "account_id", "counterparty", "counterparty_choice", "counterparty_typed", "category", "category_choice", "whom", "notes", "amount")
FAR_PAST, FAR_FUTURE = "1900-01-01", "9999-12-31"


def _int(value) -> int | None:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else None


def _cash_account_id(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if not text.isdigit() or int(text) <= 0:
        raise ValidationError("Choose a valid cash account.", "cash_account_id")
    return int(text)


def _lists(request: Request) -> dict:
    """Data for register typeahead pickers."""
    c = container(request)
    # L1 is the group header; an L3 sits indented under its L2 (sorted right after it).
    categories = []
    for cat in c.categories.pickable():
        parent = c.categories.get(cat.parent_id) if cat.parent_id else None
        l2 = parent if cat.depth >= 3 and parent else cat
        l1 = c.categories.get(l2.parent_id) if l2.parent_id else None
        categories.append({"id": cat.id, "name": cat.name, "parent": l1.name if l1 else "",
                           "level": min(cat.depth, 3), "order": f"{l2.name.casefold()}\u0000{cat.name.casefold() if cat.depth >= 3 else ''}",
                           "label": c.categories.display_name(cat.id)})
    categories.sort(key=lambda row: (row["parent"].casefold(), row["order"], row["id"]))
    accounts = c.accounts.list(active_only=True)
    counterparty_options = c.counterparties.search_names()
    counterparty_categories = {}
    usual = c.transactions.usual_categories()
    pickable = {item.id for item in c.categories.pickable()}
    for name in counterparty_options:
        party = c.counterparties.resolve(name)
        # Keep every saved Counterparty available to the register picker. Autofill uses the
        # category set on the counterparty, else the one it is usually filed under.
        counterparty_categories[name] = None
        # A rule on the name alone fills it too; one that also needs the amount decides when the row is saved.
        category_id = c.rules.category_for_name(name)
        if category_id not in pickable:
            category_id = None if c.rules.depends_on_more_than_name(name) else _category_for_party(party, usual, pickable)
        if category_id:
            category = c.categories.get(category_id)
            counterparty_categories[name] = {"id": category.id, "name": category.name}
    return {
        "category_choices": categories,
        "account_options": [a.name for a in accounts],
        "counterparty_options": counterparty_options,
        "counterparty_categories": counterparty_categories,
        "accounts": accounts,
    }


def _counterparty_matches(c, value: str):
    matches = []
    for name, score in c.counterparties.suggestions(value):
        party = c.counterparties.resolve(name)
        if party:
            matches.append({"id": party["id"], "name": name, "score": score})
    return matches


def _category_matches(c, value: str):
    return [{"id": category.id, "name": c.categories.display_name(category.id), "score": score}
            for category, score in c.categories.suggestions(value)]


def _budget_feedback(c, txn) -> str:
    if txn.status.value != "POSTED":
        return ""
    budget_effect_lines = [line for line in txn.lines if line.category_id and line.effect.value == "OUTFLOW"]
    if not budget_effect_lines:
        return ""
    month = txn.date[:7]
    view = c.budgets.month_view(month)
    by_id = {line.category_id: line for section in view.sections for line in section.lines}
    impacts = []
    seen = set()
    for line in budget_effect_lines:
        if not line.category_id or line.category_id not in by_id or line.category_id in seen:
            continue
        seen.add(line.category_id)
        budget_line = by_id[line.category_id]
        shown = budget_line
        if shown.remaining is None and shown.covered:
            parent = c.categories.get(line.category_id).parent_id
            while parent:
                ancestor = by_id.get(parent)
                if ancestor and ancestor.remaining is not None:
                    shown = ancestor
                    break
                parent = c.categories.get(parent).parent_id
        label = budget_line.name if shown is budget_line else f"inside {shown.name}"
        impacts.append(f"{label}: " + (f"{fmt(shown.remaining)} {c.base_currency} left this month"
                                       if shown.remaining is not None else "no covering limit"))
    return "Budget · " + "; ".join(impacts[:2]) if impacts else ""


def _trade_choices(c, account, positions) -> list[dict]:
    """Typeahead choices: bundled stocks/funds plus any custom assets already in this account."""
    if not account or account.account_type not in INVESTMENT_ACCOUNT_TYPES:
        return []
    assets = c.assets.investments(active_only=True)
    by_code = {asset.code: asset for asset in assets}
    held = {position.asset_id: position.quantity for position in positions}
    choices, included_ids = [], set()
    for item in catalog_instruments():
        prefix = "STK" if item["class_code"] == "STOCK" else "FND"
        code = f"{prefix}:{slug(item['ticker'], 20)}"
        asset = by_code.get(code)
        if asset:
            included_ids.add(asset.id)
        choices.append({
            "key": f"asset:{asset.id}" if asset else f"catalog:{item['ticker']}",
            "name": asset.name if asset else item["name"],
            "ticker": item["ticker"],
            "kind": "Stock" if item["class_code"] == "STOCK" else "Fund",
            "holding": str(held.get(asset.id, ZERO)) if asset else "0",
            "unit": asset.unit if asset else ("share" if item["class_code"] == "STOCK" else "unit"),
            "decimals": asset.quantity_decimals if asset else (0 if item["class_code"] == "STOCK" else 4),
        })
    for asset in assets:
        if asset.id in included_ids:
            continue
        ticker = asset.code.split(":", 1)[-1]
        choices.append({"key": f"asset:{asset.id}", "name": asset.name, "ticker": ticker,
                        "kind": c.assets.display_name(asset.asset_class_id),
                        "holding": str(held.get(asset.id, ZERO)), "unit": asset.unit,
                        "decimals": asset.quantity_decimals})
    return sorted(choices, key=lambda item: (item["name"].casefold(), item["ticker"].casefold()))


def page(request: Request, account_id: int | None, entry: dict | None = None, edit_values: dict | None = None,
         error: str = "", error_field: str = "", status_code: int = 200,
         edit_id: int | None = None, edit_acct: int | None = None,
         investment_entry: dict | None = None, investment_error_field: str = ""):

    """Render the register for one account, or all accounts when account_id is None."""
    c = container(request)
    qp = request.query_params
    account = c.accounts.get(account_id) if account_id else None
    q, month = qp.get("q", "").strip(), qp.get("month", "").strip()
    date_from, date_to = FAR_PAST, FAR_FUTURE
    from_query, to_query = qp.get("date_from", "").strip(), qp.get("date_to", "").strip()
    if from_query or to_query:
        try:
            if not from_query or not to_query:
                raise ValidationError("Choose both start and end dates.")
            date_from, date_to = fmt_date(parse_date(from_query)), fmt_date(parse_date(to_query))
            if date_to < date_from:
                raise ValidationError("End date must be on or after the start date.")
        except ValidationError as exc:
            error, from_query, to_query = error or exc.message, "", ""
    elif month:
        try:
            first, last = parse_month(month)
            date_from, date_to = fmt_date(first), fmt_date(last)
        except ValidationError as exc:
            error, month = error or exc.message, ""
    # A tag (#eid, from a note's link or typed in the search) matches exactly: never #eid2026.
    filter_tag = normal_tag(qp.get("tag", "")) or (normal_tag(q) if q.startswith("#") and " " not in q else "")
    matched_ids = c.transactions.search_ids(q) if q and not (filter_tag and q.startswith("#")) else None
    if filter_tag:
        tagged = c.transactions.tag_transaction_ids(filter_tag)
        matched_ids = tagged if matched_ids is None else matched_ids & tagged
    raw_category_id = qp.get("category_id", "")
    filter_category = ""
    if str(raw_category_id).isdigit():
        category = c.categories.get(int(raw_category_id))
        filter_category = c.categories.display_name(category.id)
        tree = c.categories.tree(Movement.OUTFLOW)
        children = {}
        for item in tree:
            if item.parent_id:
                children.setdefault(item.parent_id, []).append(item.id)
        category_ids, pending = {category.id}, [category.id]
        while pending:
            for child in children.get(pending.pop(), []):
                if child not in category_ids:
                    category_ids.add(child); pending.append(child)
        category_txns = c.reporting.category_transaction_ids(category_ids)
        matched_ids = category_txns if matched_ids is None else matched_ids & category_txns
    page_size = 50
    if matched_ids is None:  # read only the page shown; its running balance comes from SQL
        rows, total_rows, page_number = c.reporting.register_page(
            account_id, date_from, date_to, _int(qp.get("page")) or 1, page_size)
    else:  # a search or category filter: no running balance, so filter the rows in Python
        all_rows = c.reporting.register(account_id, date_from, date_to, matched_ids)
        total_rows = len(all_rows)
        page_number = min(max(_int(qp.get("page")) or 1, 1), max(1, -(-total_rows // page_size)))
        rows = all_rows[(page_number - 1) * page_size:page_number * page_size]
    total_pages = max(1, -(-total_rows // page_size))
    tag_flows = c.reporting.money_in_out({row.txn_id for row in all_rows}) if filter_tag else None
    custody_owners = c.money_from_others.transaction_owners(row.txn_id for row in rows)
    edit_id = edit_id or _int(qp.get("edit"))
    edit_acct = edit_acct or _int(qp.get("acct")) or account_id
    if edit_id and edit_values is None:
        row = next((r for r in rows if r.txn_id == edit_id and r.account_id == edit_acct), None)
        if row is not None:
            edit_values = {
                "date": row.date, "account_id": str(row.account_id), "notes": row.notes,
                "counterparty": row.other_account_label if row.type == DocType.TRF else (row.counterparty or ""),
                "category": c.categories.get(row.category_id).name if row.category_id else "",
                "category_choice": str(row.category_id) if row.category_id else "",
                "amount": str(row.amount),
                "whom": custody_owners.get(row.txn_id, ""),
            }
    holdings, account_value, account_owned_value, account_held_value = [], None, None, None
    account_asset_breakdown = []
    if account:
        holdings = c.investments.portfolio(fmt_date(today()), account.id).open
        account_value = c.reporting.account_value(account.id, today())
        account_owned_value = c.reporting.owned_account_value(account.id, today())
        account_held_value = account_value - account_owned_value
        if account.account_type == AccountType.BROKERAGE:
            account_asset_breakdown = c.reporting.account_asset_class_breakdown(account.id, today())
    can_invest = bool(account and account.account_type in INVESTMENT_ACCOUNT_TYPES)
    trade_choices = _trade_choices(c, account, holdings)
    investment_entry = investment_entry or {"date": fmt_date(today()), "instrument_key": "", "units": "",
                                            "total": "", "unit_price": "", "price_basis": "total",
                                            "dividend_basis": "total", "notes": ""}
    if investment_entry.get("instrument_key") and not investment_entry.get("instrument_label"):
        picked = next((item for item in trade_choices if item["key"] == investment_entry["instrument_key"]), None)
        if picked:
            investment_entry["instrument_label"] = f"{picked['name']} · {picked['ticker']}"
    keep = {k: v for k, v in (("q", q), ("tag", "" if q.startswith("#") else filter_tag), ("month", month),
                              ("date_from", from_query), ("date_to", to_query)) if v}
    page_base_qs = urlencode(keep)
    if page_number > 1:
        keep["page"] = page_number
    base_url = (f"/accounts/{account_id}" if account_id else "/transactions")
    return render(
        request, "register.html", status_code=status_code,
        account=account,
        today=fmt_date(today()),
        locked_through=c.reconciliation.locked_through(account.id) if account else "",
        account_balance=c.reporting.account_balance(account.id, today()) if account else None,
        manual_asset_value=OtherAssetValuationRepository(c.db).latest(account.id, fmt_date(today())) if account and account.account_type == AccountType.OTHER_ASSET else None,
        group=c.accounts.reporting_group(account) if account else "",
        account_value=account_value, account_owned_value=account_owned_value,
        account_held_value=account_held_value, account_asset_breakdown=account_asset_breakdown,
        holdings=holdings,
        can_invest=can_invest, trade_choices=trade_choices,
        investment_entry=investment_entry, investment_error_field=investment_error_field,
        cash_accounts=[a for a in c.accounts.list(active_only=True) if account and a.id != account.id]
                      if can_invest and account.account_type.value != "BROKERAGE" else [],
        rows=rows, **_lists(request),
        reserve_suggestions={row.txn_id: c.reserves.suggested_reserves(row.txn_id)
                             for row in rows if row.type == DocType.OUT},
        custody_owners=custody_owners,
        custody_present=any(custody_owners.values()),
        entry=entry or {"date": qp.get("date") or fmt_date(today()), "account_id": qp.get("new_acct", "")},
        edit_id=edit_id if edit_values is not None else None, edit_acct=edit_acct, edit=edit_values or {},
        q=q, month=month, filter_category=filter_category, filter_tag=filter_tag, tag_flows=tag_flows, date_from=from_query, date_to=to_query, base_url=base_url, keep_qs=urlencode(keep),
        page_number=page_number, total_pages=total_pages, total_rows=total_rows, page_base_qs=page_base_qs,
        search_suggestions=c.counterparties.suggestions(q, limit=3) if q else [],
        post_url=(f"/accounts/{account_id}/register" if account_id else "/transactions/register"),
        show_account=account is None, error=error, error_field=error_field,
        counterparty_matches=_counterparty_matches(c, (entry or {}).get("counterparty", "")),
        category_matches=_category_matches(c, (entry or {}).get("category", "")),
        review_mode=("counterparty" if error_field == "counterparty_review" else
                     ("category" if error_field == "category_review" else "")),
    )


def _learn_alias(c, party, typed: str) -> None:
    """You typed a spelling, then picked this counterparty from the list instead: remember the
    spelling as its alias, so it matches straight away next time. Only for a close spelling that
    matches nothing yet; a full alias list never blocks the save."""
    typed = " ".join((typed or "").split())
    if not typed or c.counterparties.resolve(typed):
        return
    if party["name"] not in {name for name, _ in c.counterparties.suggestions(typed, limit=10)}:
        return
    try:
        c.counterparties.add_alias(int(party["id"]), typed)
    except (ValidationError, ConflictError):
        pass


def category_when_empty(c, name: str, notes: str, amount, account_id: int | None, party=None) -> int | None:
    """A row saved with no category: a rule decides first (Rules with conditions), then the counterparty's
    own or usual category. Used by the register and the phone's entry sheet."""
    party = party or (c.counterparties.resolve(name) if name else None)
    pickable = {item.id for item in c.categories.pickable()}
    ruled = c.rules.outcome([name, party["name"] if party else ""], notes, amount, account_id).category_id
    if ruled in pickable:
        return ruled
    return _category_for_party(party, c.transactions.usual_categories(), pickable) if party else None


def _category_for_party(party, usual: dict, pickable: set) -> int | None:
    """The category set on the counterparty, else the one it is usually filed under, if it has one."""
    if not party:
        return None
    chosen = party["default_category_id"] or (usual.get(party["name"]) or {}).get("category_id")
    return int(chosen) if chosen and int(chosen) in pickable else None


def _resolve(request: Request, row_account: int | None, values: dict, allow_missing_category: bool = False):
    """Typed counterparty text -> internal account transfer or external transaction party."""
    c = container(request)
    if row_account is None:
        raise ValidationError("Choose an account.", "account")
    raw = values["counterparty"].strip()
    other = c.accounts.find_by_text(raw)
    if other is not None:
        if other.id == row_account:
            raise ValidationError("That is this same account — pick a different counterparty for a transfer.", "counterparty")
        return other.id, None, ""
    party = c.counterparties.resolve(raw)
    choice = values.get("counterparty_choice", "")
    if not raw:
        canonical = ""
    elif party:
        canonical = party["name"]
        _learn_alias(c, party, values.get("counterparty_typed", ""))
    else:
        guesses = c.counterparties.suggestions(raw)
        if guesses:
            if choice.startswith("existing:"):
                selected_id = _int(choice.split(":", 1)[1])
                selected = c.counterparties.get(selected_id) if selected_id else None
                if not selected or selected["name"] not in {name for name, _ in guesses}:
                    raise ValidationError("Choose one of the suggested counterparties, or explicitly create this name.", "counterparty")
                c.counterparties.add_alias(int(selected["id"]), raw)
                canonical = selected["name"]
            elif choice == "create":
                canonical = raw
                c.counterparties.create(canonical)
            else:
                names = ", ".join(name for name, _ in guesses[:3])
                raise ValidationError(f"Review similar Counterparties before saving: {names}.", "counterparty_review")
        else:
            # Nothing similar exists, so a new name cannot duplicate one: save it without an extra
            # question. Similar spellings above still need a deliberate choice.
            canonical = raw
            c.counterparties.create(canonical)

    category_text = values["category"].strip()
    category_choice = _int(values.get("category_choice"))
    if allow_missing_category and not category_text and category_choice is None:
        return None, None, canonical
    if not category_text and category_choice is None:
        try:
            amount = to_decimal(values.get("amount", ""), "amount")
        except ValidationError:
            amount = None
        category_choice = category_when_empty(c, raw, values.get("notes", ""), amount, row_account, party)
    if category_choice is not None:
        category = c.categories.get(category_choice)
        if category.id not in {item.id for item in c.categories.pickable()}:
            raise ValidationError("Choose one of the suggested broad categories.", "category")
    else:
        exact = [item for item in c.categories.pickable()
                 if category_text.casefold() in {item.name.casefold(), c.categories.display_name(item.id).casefold(),
                                                 item.code.casefold()}]
        if not exact:
            exact = [item for item in c.categories.tree(active_only=False)
                     if not item.is_root and item.depth == 2 and item.code.startswith("EXP.")
                     and category_text.casefold() in {item.name.casefold(), c.categories.display_name(item.id).casefold(),
                                                      item.code.casefold()}]
        if len(exact) == 1:
            category = exact[0]
        elif len(exact) > 1 or c.categories.suggestions(category_text):
            raise ValidationError("Review similar categories and choose the one you mean.", "category_review")
        else:
            try:
                category = c.categories.find_by_text(category_text)
            except ValidationError:
                # System categories are intentionally absent from the picker,
                # but an imported row must be editable without changing its
                # category first.
                system = [item for item in c.categories.tree(active_only=True)
                          if item.is_system and category_text.casefold() in {
                              item.name.casefold(), c.categories.display_name(item.id).casefold(),
                              item.code.casefold()}]
                if len(system) != 1:
                    raise
                category = system[0]
    return None, category.id, canonical


async def create(request: Request, account_id: int | None):
    """Save the quick-add row; come back ready for the next one."""
    c = container(request)
    form = await request.form()
    entry = {k: str(form.get(k, "")) for k in ENTRY_FIELDS}
    row_account = account_id or _int(entry["account_id"])
    try:
        with c.db.transaction():
            other_id, category_id, counterparty = _resolve(request, row_account, entry)
            category = c.categories.get(category_id) if category_id else None
            owner_name = (_transfer_custody_owner(c, entry) if other_id else _custody_owner(c, entry, category))
            owner_party = c.counterparties.resolve(owner_name) if owner_name else None
            txn = c.transactions.record_in_account(row_account, entry["date"], entry["amount"], category_id, other_id,
                                                   counterparty, entry["notes"], owner_id=owner_party["id"] if owner_party else None)
            amount = to_decimal(entry["amount"], "amount")
            if other_id:
                source, target = (other_id, row_account) if amount > ZERO else (row_account, other_id)
                owner = _transfer_custody_owner(c, entry)
                c.money_from_others.sync_transfer(txn.id, txn.date, owner, source, target, abs(amount), entry["notes"])
            else:
                owner = _custody_owner(c, entry, category)
                c.money_from_others.sync_transaction(txn.id, txn.date, owner, row_account, amount, entry["notes"])
    except LightningError as exc:
        return page(request, account_id, entry=entry, error=exc.message, error_field=exc.field or "",
                    status_code=400)
    return txn, entry


async def update(request: Request, account_id: int | None, txn_id: int):
    """Save an edited row in place."""
    c = container(request)
    form = await request.form()
    values = {k: str(form.get(k, "")) for k in ENTRY_FIELDS}
    row_account = account_id or _int(values["account_id"])
    try:
        with c.db.transaction():
            existing = c.transactions.get(txn_id)
            cash_lines = [line for line in existing.lines if c.assets.get_asset(line.asset_id).is_cash]
            is_split = existing.type.value == "OUT" and len(cash_lines) > 1
            other_id, category_id, counterparty = _resolve(
                request, row_account, values, allow_missing_category=is_split)
            category = c.categories.get(category_id) if category_id else None
            owner_name = (_transfer_custody_owner(c, values) if other_id else _custody_owner(c, values, category))
            owner_party = c.counterparties.resolve(owner_name) if owner_name else None
            txn = c.transactions.update_in_account(txn_id, row_account, values["date"], values["amount"], category_id,
                                                   other_id, counterparty, values["notes"], owner_party["id"] if owner_party else None)
            if txn.id != txn_id:
                c.money_from_others.sync_transaction(txn_id, values["date"], None, row_account, ZERO, "")
            amount = to_decimal(values["amount"], "amount")
            if other_id:
                source, target = (other_id, row_account) if amount > ZERO else (row_account, other_id)
                owner = _transfer_custody_owner(c, values)
                c.money_from_others.sync_transfer(txn.id, txn.date, owner, source, target, abs(amount), values["notes"])
            else:
                owner = _custody_owner(c, values, category)
                c.money_from_others.sync_transaction(txn.id, txn.date, owner, row_account, amount, values["notes"])
    except LightningError as exc:
        return page(request, account_id, edit_values=values, error=exc.message, error_field=exc.field or "",
                    status_code=400, edit_id=txn_id, edit_acct=row_account)
    return txn, values


def _custody_owner(c, values: dict, category) -> str | None:
    if not category or category.code != "EXP.SYSTEM.CUSTODY":
        return None
    name = values.get("whom", "").strip()
    party = c.counterparties.resolve(name)
    if not party:
        raise ValidationError("Choose a saved Counterparty in Whom. Add a new person from the Counterparties tab first.",
                              "whom")
    if not party["active"]:
        raise ValidationError("That Counterparty is archived. Activate it before using it as Whom.", "whom")
    return party["name"]


def _transfer_custody_owner(c, values: dict) -> str | None:
    """Transfer custody only when the user explicitly identifies its owner."""
    name = values.get("whom", "").strip()
    if name.casefold() in {"self", "me", "my money", "my own money"}:
        return None
    if name:
        party = c.counterparties.resolve(name)
        if not party or not party["active"]:
            raise ValidationError("Choose an active saved Counterparty in Whom.", "whom")
        return party["name"]
    return None


async def create_investment_entry(request: Request, account_id: int):
    """Record a buy, sell, or dividend from the account's inline transaction row."""
    c = container(request)
    account = c.accounts.get(account_id)
    form = await request.form()
    values = {key: str(form.get(key, "")).strip() for key in
              ("date", "instrument_key", "trade_action", "units", "total", "dividend_basis", "unit_price", "price_basis", "fees",
               "fees_included", "cash_account_id", "notes", "whom")}
    values["instrument_label"] = str(form.get("instrument_label", ""))
    values["is_others"] = "1" if form.get("is_others") else ""
    try:
        if account.account_type not in INVESTMENT_ACCOUNT_TYPES:
            raise ValidationError("Investment entries can only be added to an investment account.")
        key = values["instrument_key"]
        if not key:
            raise ValidationError("Type a stock or fund and choose it from the results.", "instrument")
        action = values["trade_action"] or "buy"
        if action not in {"buy", "sell", "dividend"}:
            raise ValidationError("Choose Buy, Sell, or Dividend.", "trade_action")
        units = to_decimal(values["units"], "units") if values["units"] and action != "dividend" else None
        if units is not None and units < ZERO:
            raise ValidationError("Enter units as a positive quantity; choose Sell for a sale.", "units")
        if units is not None and action == "sell":
            units = -units
        signed_units = units or ZERO
        total = values["total"]
        unit_price = values["unit_price"]
        if (action == "dividend" or units is None) and not total:
            raise ValidationError("Enter a dividend amount, or add units for a buy or sell.", "total")
        if units == ZERO:
            raise ValidationError("Units must be greater than zero.", "units")
        ticker_row = None
        asset = None
        cash_account_id = _cash_account_id(values["cash_account_id"])
        with c.db.transaction():
            if key.startswith("asset:") and key[6:].isdigit():
                asset = c.assets.get_asset(int(key[6:]))
                if asset.is_cash or not asset.active:
                    raise ValidationError("Choose an active investment.", "instrument")
            elif key.startswith("catalog:"):
                ticker = key[8:]
                ticker_row = next((row for row in catalog_instruments() if row["ticker"].casefold() == ticker.casefold()), None)
                if ticker_row is None:
                    raise ValidationError("That instrument is not in the local catalogue. Search and choose a result.",
                                          "instrument")
                prefix = "STK" if ticker_row["class_code"] == "STOCK" else "FND"
                code = f"{prefix}:{slug(ticker_row['ticker'], 20)}"
                asset = next((item for item in c.assets.investments() if item.code == code), None)
                if asset is None:
                    if units is not None and units < ZERO:
                        raise ValidationError(f"You do not hold {ticker_row['name']} in this account yet.", "units")
                    asset = c.assets.create_investment(ticker_row["name"], ticker_row["class_code"],
                                                       ticker_row["ticker"])
            else:
                raise ValidationError("Choose an investment from the results.", "instrument")
            owner = None
            owner_id = None
            if values["is_others"]:
                party = c.counterparties.resolve(values["whom"])
                if not party or not party["active"]:
                    raise ValidationError("Choose an active saved Counterparty in Whom.", "whom")
                owner, owner_id = party["name"], party["id"]
            if units is None and action != "dividend":
                # Bought or sold by amount (typical for a money market fund): units = amount ÷ price,
                # using the price typed here or the fund's latest price.
                price = to_decimal(unit_price, "unit_price") if unit_price else (
                    c.reporting.value_of(asset.id, Decimal(1),
                                         fmt_date(parse_date(values["date"], "date")) if values["date"] else fmt_date(today())).price)
                if not price or not total:
                    raise ValidationError("Enter the number of units, or a price per unit so they can be worked out.",
                                          "units")
                amount = to_decimal(total, "total")
                fee = to_decimal(values["fees"], "fees") if values["fees"] else ZERO
                gross = amount - fee if values["fees_included"] != "0" else amount
                units = (gross / price).quantize(Decimal("0.0001"))
                if units <= ZERO:
                    raise ValidationError("The amount is too small for one unit at that price.", "total")
                if action == "sell":
                    units = -units
                signed_units = units
                values["price_basis"] = "total"
            if units is None:
                if not total:
                    raise ValidationError("Enter the dividend amount.", "total")
                if values["dividend_basis"] not in {"", "total", "per_share"}:
                    raise ValidationError("Choose total dividend or dividend per share.", "dividend_basis")
                dividend_amount = to_decimal(total, "total")
                if values["dividend_basis"] == "per_share":
                    held_units = c.investments.holding_for_owner(
                        account.id, asset.id, fmt_date(parse_date(values["date"], "date")), owner_id)
                    if held_units <= ZERO:
                        who = owner or "you"
                        raise ValidationError(f"{who.capitalize()} must hold shares of this investment on that date to receive a dividend.", "instrument")
                    dividend_amount = (dividend_amount * held_units).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                txn = c.investments.dividend(values["date"], account.id, asset.id, dividend_amount,
                                             values["notes"], owner_id=owner_id)
            elif units > ZERO:
                basis = values["price_basis"]
                if basis == "unit_price" or (unit_price and not total):
                    if not unit_price:
                        raise ValidationError("Enter a price per unit or the total paid.", "unit_price")
                    txn = c.investments.buy(values["date"], account.id, asset.id, units, unit_price,
                                            fees=values["fees"],
                                            cash_account_id=cash_account_id,
                                            notes=values["notes"], owner_id=owner_id)
                else:
                    if not total:
                        raise ValidationError("Enter the total paid or a price per unit.", "total")
                    txn = c.investments.buy_total(values["date"], account.id, asset.id, units, total,
                                                  fees=values["fees"], fees_included=values["fees_included"] != "0",
                                                  cash_account_id=cash_account_id,
                                                  notes=values["notes"], owner_id=owner_id)
            else:
                units = -units
                basis = values["price_basis"]
                if basis == "unit_price" or (unit_price and not total):
                    if not unit_price:
                        raise ValidationError("Enter a price per unit or the total received.", "unit_price")
                    txn = c.investments.sell(values["date"], account.id, asset.id, units, unit_price,
                                             fees=values["fees"],
                                             cash_account_id=cash_account_id,
                                             notes=values["notes"], owner_id=owner_id)
                else:
                    if not total:
                        raise ValidationError("Enter the total received or a price per unit.", "total")
                    txn = c.investments.sell_total(values["date"], account.id, asset.id, units, total,
                                                   fees=values["fees"], fees_included=values["fees_included"] != "0",
                                                   cash_account_id=cash_account_id,
                                                   notes=values["notes"], owner_id=owner_id)
            c.money_from_others.sync_investment(txn.id, txn.date, owner, account.id, asset.id, signed_units)
            if owner:
                cash_line = next((line for line in txn.lines if c.assets.get_asset(line.asset_id).is_cash), None)
                if cash_line:
                    cash_amount = cash_line.quantity
                    c.money_from_others.sync_transaction(txn.id, txn.date, owner, cash_line.account_id,
                                                         cash_amount, values["notes"])
    except LightningError as exc:
        return page(request, account_id, investment_entry=values, error=exc.message,
                    investment_error_field=exc.field or "", status_code=400)
    return txn, values
