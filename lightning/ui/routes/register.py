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
from lightning.market.iso import venue_name
from lightning.core.refs import DocType
from lightning.transactions.tags import normalize as normal_tag

from ..web import container, render
from ..charts import class_tone
from ..i18n import translate

ENTRY_FIELDS = ("date", "account_id", "counterparty", "counterparty_choice", "counterparty_typed", "category", "category_choice", "whom", "notes", "amount")
FAR_PAST, FAR_FUTURE = "1900-01-01", "9999-12-31"



def account_composition(breakdown, value, owned, held):
    """U4: the account's classes as one 100% bar (four, then Other) and, when held for others, an owned/held bar."""
    parts = [row for row in breakdown if row["total"] > 0]
    total = sum((row["total"] for row in parts), ZERO)
    held_bar = None
    if held and held > 0 and value and value > 0:
        yours = max(owned, ZERO)
        held_bar = {"owned": yours, "held": held, "owned_pct": float(yours / value * 100), "held_pct": float(held / value * 100)}
    if (len(parts) < 2 and not held_bar) or not total:
        return None
    segments = [{"name": row["name"], "tone": class_tone(row["code"]), "amount": row["total"]} for row in parts[:4]]
    rest = parts[4:]
    if rest:
        segments.append({"name": "Other", "tone": "other", "amount": sum((row["total"] for row in rest), ZERO)})
    for seg in segments:
        seg["pct"] = float(seg["amount"] / total * 100)
        seg["share"] = int((seg["amount"] / total * 100).quantize(Decimal(1), ROUND_HALF_UP))
    return {"segments": segments if len(parts) >= 2 else [], "held_bar": held_bar}


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
    # A gold account holds things, not cash: money in or out is refused there, so the pickers do not offer it.
    accounts = [a for a in c.accounts.list(active_only=True) if a.account_type != AccountType.PHYSICAL_ASSET]
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
        "owner_options": [row["name"] for row in c.counterparties.list_people()],
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
        if shown.remaining is None:
            state = "no covering limit"
        elif shown.remaining < 0:
            state = f"{fmt(-shown.remaining)} {c.base_currency} over this month"
        else:
            state = f"{fmt(shown.remaining)} {c.base_currency} left this month"
        impacts.append(f"{label}: {state}")
    return "Budget · " + "; ".join(impacts[:2]) if impacts else ""



def _catalog_asset(assets, item):
    """The held asset behind a catalogue row: same ticker on the same exchange (U9)."""
    prefix = "STK" if item["class_code"] == "STOCK" else "FND"
    symbol, mic = slug(item["ticker"], 20), (item.get("mic") or "").upper()
    for asset in assets:
        if asset.code in (f"{prefix}:{symbol}", f"{prefix}:{symbol}-{mic}" if mic else ""):
            if not mic or not asset.mic or asset.mic.upper() == mic:
                return asset
    return None


def _catalog_key(item, duplicated):
    """catalog:TICKER, or catalog:TICKER@MIC when the same ticker is listed on more than one exchange."""
    mic = (item.get("mic") or "").upper()
    return f"catalog:{item['ticker']}@{mic}" if mic and item["ticker"].casefold() in duplicated else f"catalog:{item['ticker']}"


def _trade_choices(c, account, positions) -> list[dict]:
    """Typeahead choices: bundled stocks/funds plus any custom assets already in this account."""
    if not account or account.account_type not in INVESTMENT_ACCOUNT_TYPES:
        return []
    assets = c.assets.investments(active_only=True)
    held = {position.asset_id: position.quantity for position in positions}
    choices, included_ids = [], set()
    accounts_in = {a.currency for a in c.accounts.list(active_only=True)}

    def currency_note(currency: str) -> str:
        """One line when a foreign listing cannot be paid for yet: its currency needs an account and a rate."""
        if currency == c.base_currency:
            return ""
        broker = account.account_type == AccountType.BROKERAGE  # a broker holds it in a pocket (2026-10-16)
        missing = [what for ok, what in ((broker or currency in accounts_in, f"a {currency} account"),
                                         (c.reporting.valuer.fx(currency, fmt_date(today())) is not None,
                                          f"a {currency} rate")) if not ok]
        if missing:
            return translate(f"Priced in {currency}: add {' and '.join(missing)} first.", c.settings.get("locale") or "en")
        if account.currency != currency and broker:
            return translate(f"Priced in {currency}: held in this broker's {currency} pocket.",
                             c.settings.get("locale") or "en")
        if account.currency != currency:
            return translate(f"Priced in {currency}: buy it from a {currency} account.", c.settings.get("locale") or "en")
        return ""

    catalogue = catalog_instruments()
    seen, duplicated = set(), set()
    for item in catalogue:
        name = item["ticker"].casefold()
        (duplicated if name in seen else seen).add(name)
    for item in catalogue:
        asset = _catalog_asset(assets, item)
        if asset:
            included_ids.add(asset.id)
        choices.append({
            "key": f"asset:{asset.id}" if asset else _catalog_key(item, duplicated),
            "name": asset.name if asset else item["name"],
            "ticker": item["ticker"],
            "kind": "Stock" if item["class_code"] == "STOCK" else "Fund",
            "holding": str(held.get(asset.id, ZERO)) if asset else "0",
            "unit": asset.unit if asset else ("share" if item["class_code"] == "STOCK" else "unit"),
            "decimals": asset.quantity_decimals if asset else (0 if item["class_code"] == "STOCK" else 4),
            "exchange": venue_name(item.get("mic")) if item.get("mic") else "",
            "currency": asset.currency if asset else item.get("currency", ""),
            "note": currency_note(asset.currency if asset else item.get("currency", "")),
        })
    for asset in assets:
        if asset.id in included_ids:
            continue
        ticker = asset.code.split(":", 1)[-1]
        choices.append({"key": f"asset:{asset.id}", "name": asset.name, "ticker": ticker,
                        "kind": c.assets.display_name(asset.asset_class_id),
                        "holding": str(held.get(asset.id, ZERO)), "unit": asset.unit,
                        "decimals": asset.quantity_decimals, "exchange": venue_name(asset.mic) if asset.mic else "",
                        "currency": asset.currency, "note": currency_note(asset.currency)})
    return sorted(choices, key=lambda item: (item["name"].casefold(), item["ticker"].casefold()))


def base_url_for(account_id: int | None) -> str:
    return f"/accounts/{account_id}" if account_id else "/transactions"


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
    preset = qp.get("preset", "").strip()
    active_view = None
    if qp.get("saved_view", "").strip():
        try:
            active_view = c.saved_views.get(qp.get("saved_view"), account_id)
            q, preset, from_query, to_query = (active_view[k] or "" for k in ("q", "preset", "date_from", "date_to"))
            month = ""
        except LightningError as exc:
            error = error or exc.message
    if preset == "custom" and not (from_query and to_query):
        # Let the user choose the range after selecting the custom option.
        date_from, date_to = FAR_PAST, FAR_FUTURE
        month = ""
    elif preset:
        try:
            definition = c.saved_views.normalize({"preset": preset, "date_from": from_query,
                                                 "date_to": to_query, "q": q, "tag": qp.get("tag", ""),
                                                 "category_id": qp.get("category_id", "")}, account_id=account_id)
            date_from, date_to = c.saved_views.dates(definition)
            from_query, to_query = date_from, date_to
            month = ""
        except LightningError as exc:
            error, preset, from_query, to_query = error or exc.message, "", "", ""
    elif from_query or to_query:
        try:
            if not from_query or not to_query:
                raise ValidationError("Choose both start and end dates.")
            date_from, date_to = fmt_date(parse_date(from_query)), fmt_date(parse_date(to_query))
            if date_to < date_from:
                raise ValidationError("End date must be on or after the start date.")
            preset = "custom"
        except ValidationError as exc:
            error, from_query, to_query = error or exc.message, "", ""
    elif month:
        try:
            first, last = parse_month(month)
            date_from, date_to = fmt_date(first), fmt_date(last)
            from_query, to_query, preset = date_from, date_to, ""
        except ValidationError as exc:
            error, month = error or exc.message, ""
    # A tag (#eid, from a note's link or typed in the search) matches exactly: never #eid2026.
    filter_tag = normal_tag(active_view["tag"] if active_view else qp.get("tag", "")) or (normal_tag(q) if q.startswith("#") and " " not in q else "")
    matched_ids = c.transactions.search_ids(q) if q and q.casefold() != ("#" + filter_tag).casefold() else None
    if filter_tag:
        tagged = c.transactions.tag_transaction_ids(filter_tag)
        matched_ids = tagged if matched_ids is None else matched_ids & tagged
    raw_category_id = active_view["category_id"] if active_view else qp.get("category_id", "")
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
    show_val = qp.get("val") == "1"
    val_count = c.reporting.register_value_updates(account_id, date_from, date_to)
    if matched_ids is None and not (val_count and not show_val):
        # read only the page shown; its running balance comes from SQL
        rows, total_rows, page_number = c.reporting.register_page(
            account_id, date_from, date_to, _int(qp.get("page")) or 1, page_size)
    else:  # a search or category filter, or value updates folded: filter in Python; balances stay per row
        all_rows = c.reporting.register(account_id, date_from, date_to, matched_ids)
        if val_count and not show_val:
            all_rows = [row for row in all_rows if row.type != DocType.VAL]
        total_rows = len(all_rows)
        page_number = min(max(_int(qp.get("page")) or 1, 1), max(1, -(-total_rows // page_size)))
        rows = all_rows[(page_number - 1) * page_size:page_number * page_size]
    total_pages = max(1, -(-total_rows // page_size))
    tag_flows = c.reporting.money_in_out({row.txn_id for row in all_rows}) if filter_tag else None
    custody_owners = c.money_from_others.transaction_owners(row.txn_id for row in rows)
    conversions = {row.txn_id: c.transactions.conversion_of(c.transactions.get(row.txn_id))
                   for row in rows if row.type == DocType.CNV}
    edit_id = edit_id or _int(qp.get("edit"))
    edit_acct = edit_acct or _int(qp.get("acct")) or account_id
    edit_original = {}
    if edit_id:
        row = next((r for r in rows if r.txn_id == edit_id and r.account_id == edit_acct), None)
        if row is not None:
            edit_original = {
                "date": row.date, "account_id": str(row.account_id), "notes": row.notes,
                "counterparty": row.other_account_label if row.type == DocType.TRF else (row.counterparty or ""),
                "category": c.categories.get(row.category_id).name if row.category_id else "",
                "category_choice": str(row.category_id) if row.category_id else "",
                "amount": str(row.amount),
                "whom": custody_owners.get(row.txn_id, ""),
            }
            if edit_values is None:
                edit_values = dict(edit_original)
    holdings, account_value, account_owned_value, account_held_value = [], None, None, None
    account_asset_breakdown = []
    if account:
        holdings = c.investments.portfolio(fmt_date(today()), account.id).open
        account_value = c.reporting.account_value(account.id, today())
        account_owned_value = c.reporting.owned_account_value(account.id, today())
        account_held_value = account_value - account_owned_value
        if account.account_type == AccountType.BROKERAGE:
            account_asset_breakdown = c.reporting.account_asset_class_breakdown(account.id, today())
        # One row per broker: its currency pockets add to the page's total and holdings (owner 2026-10-16).
        for pocket in c.accounts.pockets(account.id):
            holdings = list(holdings) + list(c.investments.portfolio(fmt_date(today()), pocket.id).open)
            account_value += c.reporting.account_value(pocket.id, today())
            account_owned_value += c.reporting.owned_account_value(pocket.id, today())
        account_held_value = account_value - account_owned_value
    can_invest = bool(account and account.account_type in INVESTMENT_ACCOUNT_TYPES)
    trade_choices = _trade_choices(c, account, holdings)
    investment_entry = investment_entry or {"date": fmt_date(today()), "instrument_key": "", "units": "",
                                            "total": "", "unit_price": "", "price_basis": "total",
                                            "dividend_basis": "total", "notes": ""}
    if investment_entry.get("instrument_key") and not investment_entry.get("instrument_label"):
        picked = next((item for item in trade_choices if item["key"] == investment_entry["instrument_key"]), None)
        if picked:
            investment_entry["instrument_label"] = f"{picked['name']} · {picked['ticker']}" + (f" · {picked['exchange']}" if picked.get("exchange") else "")
    keep = {k: v for k, v in (("q", q), ("tag", "" if q.startswith("#") else filter_tag), ("month", month),
                              ("preset", preset), ("date_from", from_query), ("date_to", to_query),
                              ("category_id", str(raw_category_id) if raw_category_id else ""),
                              ("val", "1" if show_val else "")) if v}
    page_base_qs = urlencode(keep)
    val_toggle_url = base_url_for(account_id) + "?" + urlencode({**{k: v for k, v in keep.items() if k != "val"},
                                                                 **({} if show_val else {"val": "1"})})
    if page_number > 1:
        keep["page"] = page_number
    base_url = base_url_for(account_id)
    reserve_rows = [row.txn_id for row in rows if row.type == DocType.OUT]
    reserve_suggestions = c.reserves.suggested_reserves_for_transactions(reserve_rows)
    return render(
        request, "register.html", status_code=status_code,
        account=account,
        account_spendable=account.counts_as_spendable(c.base_currency) if account else None,
        pocket_cash=_pocket_cash(c, account),
        broker=c.accounts.broker_of(account) if account and account.parent_id else None,
        today=fmt_date(today()),
        account_balance=c.reporting.account_balance(account.id, today()) if account else None,
        manual_asset_value=OtherAssetValuationRepository(c.db).latest(account.id, fmt_date(today())) if account and account.account_type == AccountType.OTHER_ASSET else None,
        group=c.accounts.reporting_group(account) if account else "",
        account_value=account_value, account_owned_value=account_owned_value,
        account_native_value=_native_value(c, account, account_value),
        account_held_value=account_held_value, account_asset_breakdown=account_asset_breakdown,
        holdings=holdings,
        composition=account_composition(account_asset_breakdown, account_value, account_owned_value, account_held_value) if account_asset_breakdown else None,
        can_invest=can_invest, trade_choices=trade_choices,
        move_targets=[a for a in c.accounts.list(active_only=True)
                      if account and a.id != account.id and a.account_type == AccountType.BROKERAGE
                      and a.currency == account.currency] if can_invest and account.account_type == AccountType.BROKERAGE else [],
        investment_entry=investment_entry, investment_error_field=investment_error_field,
        cash_accounts=[a for a in c.accounts.list(active_only=True) if account and a.id != account.id]
                      if can_invest and account.account_type.value != "BROKERAGE" else [],
        rows=rows, **_lists(request),
        reserve_suggestions=reserve_suggestions,
        custody_owners=custody_owners,
        conversions=conversions,
        custody_present=any(custody_owners.values()),
        entry=entry or {"date": qp.get("date") or fmt_date(today()), "account_id": qp.get("new_acct", "")},
        edit_id=edit_id if edit_values is not None else None, edit_acct=edit_acct, edit=edit_values or {}, edit_original=edit_original,
        q=q, month=month, preset=preset, active_view=active_view, show_val=show_val, val_count=val_count, val_toggle_url=val_toggle_url,
        saved_views=c.saved_views.list(account_id), view_account_id=account_id or "",
        filter_category=filter_category, filter_tag=filter_tag, tag_flows=tag_flows,
        date_from=from_query, date_to=to_query, base_url=base_url, keep_qs=urlencode(keep),
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
    party = c.counterparties.get(c.counterparties.ensure_person(name))
    if not party["active"]:
        raise ValidationError("That Counterparty is archived. Activate it before using it as Whom.", "whom")
    return party["name"]


def _transfer_custody_owner(c, values: dict) -> str | None:
    """Transfer custody only when the user explicitly identifies its owner."""
    name = values.get("whom", "").strip()
    if name.casefold() in {"self", "me", "my money", "my own money"}:
        return None
    if name:
        party = c.counterparties.get(c.counterparties.ensure_person(name))
        if not party["active"]:
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
               "fees_included", "cash_account_id", "notes", "whom", "paid_from", "tax_withheld", "to_account_id")}
    values["instrument_label"] = str(form.get("instrument_label", ""))
    values["is_others"] = "1" if (form.get("is_others") or values.get("whom")) else ""
    try:
        if account.account_type not in INVESTMENT_ACCOUNT_TYPES:
            raise ValidationError("Investment entries can only be added to an investment account.")
        action = values["trade_action"] or "buy"
        if action not in {"buy", "sell", "dividend", "fee", "interest", "move"}:
            raise ValidationError("Choose Buy, Sell, Dividend, Fee, Interest or Move.", "trade_action")
        if action in {"fee", "interest"}:  # the broker's own cash: no instrument
            day = fmt_date(parse_date(values["date"], "date"))
            with c.db.transaction():
                txn = (c.investments.broker_fee if action == "fee" else c.investments.broker_interest)(
                    day, account.id, values["total"], values["notes"])
            return txn, values
        key = values["instrument_key"]
        if not key:
            raise ValidationError("Type a stock or fund and choose it from the results.", "instrument")
        if action == "move":
            if not values["to_account_id"].isdigit():
                raise ValidationError("Choose the broker to move the shares to.", "to_account")
            if not values["units"]:
                raise ValidationError("Enter how many units to move.", "units")
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
                ticker, _, wanted_mic = key[8:].partition("@")
                ticker_row = next((row for row in catalog_instruments() if row["ticker"].casefold() == ticker.casefold()
                                   and (not wanted_mic or (row.get("mic") or "").upper() == wanted_mic.upper())), None)
                if ticker_row is None:
                    raise ValidationError("That instrument is not in the local catalogue. Search and choose a result.",
                                          "instrument")
                prefix = "STK" if ticker_row["class_code"] == "STOCK" else "FND"
                asset = _catalog_asset(c.assets.investments(), ticker_row)
                if asset is None:
                    if units is not None and units < ZERO:
                        raise ValidationError(f"You do not hold {ticker_row['name']} in this account yet.", "units")
                    asset = c.assets.create_investment(ticker_row["name"], ticker_row["class_code"],
                                                       ticker_row["ticker"], mic=ticker_row.get("mic", ""),
                                                       currency=ticker_row.get("currency", ""))
            else:
                raise ValidationError("Choose an investment from the results.", "instrument")
            if asset.currency != account.currency and account.account_type != AccountType.BROKERAGE:
                raise ValidationError(f"{asset.name} is priced in {asset.currency}; this account is in {account.currency}. "
                                      f"Use a {asset.currency} account.", "instrument")
            if action == "move":
                source_id, _ = c.investments.route(account.id, asset.id)  # a foreign listing sits in a pocket
                target_id, _ = c.investments.route(int(values["to_account_id"]), asset.id)
                txn = c.investments.move_units(values["date"], source_id, target_id, asset.id,
                                               values["units"], values["notes"])
                return txn, values
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
                                             values["notes"], owner_id=owner_id, tax=values["tax_withheld"])
            elif units > ZERO and values["paid_from"] and asset.currency != c.accounts.broker_of(account).currency:
                # Convert, then buy (owner decision 2026-10-16): the broker's own cash pays, the pocket buys.
                if not total and unit_price:
                    total = str(units * to_decimal(unit_price, "unit_price"))
                if not total:
                    raise ValidationError(f"Enter the total in {asset.currency}.", "total")
                txn = c.investments.buy_converting(values["date"], account.id, asset.id, units, total,
                                                   values["paid_from"], notes=values["notes"], fees=values["fees"],
                                                   fees_included=values["fees_included"] != "0", owner_id=owner_id)
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
            held_in = next((line.account_id for line in txn.lines if line.asset_id == asset.id), account.id)  # a pocket
            c.money_from_others.sync_investment(txn.id, txn.date, owner, held_in, asset.id, signed_units)
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


def _native_value(c, account, value):
    """A foreign account's value in its own currency (audit 2026-10-15): "2,211 USD" beside "≈ 114,211 EGP"."""
    if not account or value is None or account.currency == c.base_currency:
        return None
    rate = c.reporting.valuer.fx(account.currency, fmt_date(today()))
    return value / rate.rate if rate and rate.rate else None


def _pocket_cash(c, account):
    """A broker's cash in each currency it holds, its own first (one row per broker, owner 2026-10-16)."""
    if not account or account.account_type != AccountType.BROKERAGE or account.parent_id:
        return []
    pockets = c.accounts.pockets(account.id)
    if not pockets:
        return []
    return [{"id": a.id, "currency": a.currency, "cash": c.reporting.account_balance(a.id, today())} for a in [account, *pockets]]
