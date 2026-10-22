from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from lightning.accounts.domain import DEFAULT_CASH_CLASS, OFFERED_TYPES, SIDEBAR_GROUPS, TYPE_LABELS
from lightning.core.dates import fmt_date, parse_date, today
from lightning.core.errors import LightningError, ValidationError
from lightning.core.figures import label
from lightning.core.money import ZERO, fmt, to_decimal

from . import register
from .. import charts, kpis, status as page_status
from ..periods import parse_period
from ..web import container, redirect, render

router = APIRouter(prefix="/accounts")

FIELDS = ("name", "account_type", "institution", "last4", "notes", "opening_balance", "opening_balance_date", "owner_id", "currency")


def _remember_institution(c, text: str) -> None:
    """An institution typed on the form that the list lacks joins the profile's own institutions."""
    # Journal account commands stage the account and institution together. On a
    # replica, a separate command here would stop the route before the account.
    if text.strip() and not getattr(c, "is_journal", False):
        c.institutions.add(text)


def _form_context(request: Request, values: dict, account=None, error: LightningError | None = None):
    c = container(request)
    groups = {t.value: c.assets.get_class_by_code(DEFAULT_CASH_CLASS[t]).name for t in OFFERED_TYPES}
    groups["CASH_AT_HAND"] = c.assets.get_class_by_code("CASH").name
    return dict(
        values=values,
        account=account,
        currencies=c.currencies.list(),
        institution_options=c.institutions.options(),
        institution_hints=c.institutions.form_hints(),
        base=c.base_currency,
        types=sorted(((t.value, TYPE_LABELS[t]) for t in OFFERED_TYPES), key=lambda row: row[1].casefold()),
        # where each type shows up in "What your wealth is made of", in plain words
        groups=groups,
        counterparties=c.counterparties.list_people(),
        error=error.message if error else "",
        error_field=(error.field or "") if error else "",
    )


@router.get("")
async def list_accounts(request: Request):
    c = container(request)
    rows = []
    has_unavailable = False
    for account in c.accounts.list():
        balance = c.reporting.account_value(account.id, today())
        owned = c.reporting.owned_account_value(account.id, today())
        if (account.currency != c.base_currency
                and account.account_type.value in ("CASH", "BANK", "BROKERAGE")):
            cash = c.reporting.valuer.value(c.assets.cash_asset(account.currency),
                                            c.reporting.account_balance(account.id, today()), today())
            if cash.value is None:
                balance = owned = None
                has_unavailable = True
        rows.append((account, balance, owned, c.transactions.count_for_account(account.id)))
    # One row per broker (owner decision 2026-10-16): each currency pocket adds to its broker's row.
    by_id = {row[0].id: i for i, row in enumerate(rows)}
    for account, balance, owned, count in [row for row in rows if row[0].parent_id]:
        i = by_id.get(account.parent_id)
        if i is None:
            continue
        parent, p_balance, p_owned, p_count = rows[i]
        add = lambda a, b: None if a is None or b is None else a + b  # noqa: E731
        rows[i] = (parent, add(p_balance, balance), add(p_owned, owned), p_count + count)
    rows = [row for row in rows if not row[0].parent_id or row[0].parent_id not in by_id]
    net_worth = c.reporting.net_worth(today())
    gross_total = (None if has_unavailable else
                   sum((row[1] for row in rows if row[0].active), start=0))
    recent_rows = c.reporting.register_page(None, "1900-01-01", "9999-12-31", 1, 10)[0]  # the phone shows the latest few
    # Answer first (guideline 3.33): What you own is the Lead, In your accounts and Held for others beside it; the
    # accounts follow in the groups the sidebar uses, each with its total.
    held = c.reporting.money_from_others_total(fmt_date(today()))
    active = [row for row in rows if row[0].active]
    lead = None
    if rows and not net_worth.unvalued:
        lead = kpis.card(label("what_you_own"), net_worth.what_you_own,
                         kpis.compare("is held for others, not yours", fmt(held, 0), "hold") if held
                         else kpis.compare("All of it is yours"), tone="hold", key="own",
                         line_=kpis.line(f"Across {len(active)} account{'s' if len(active) != 1 else ''}"))
    groups: dict[str, dict] = {}
    for row in rows:
        group = groups.setdefault(SIDEBAR_GROUPS[row[0].account_type], {"rows": [], "balance": ZERO, "owned": ZERO})
        group["rows"].append(row)
        if row[0].active:
            group["balance"] = None if group["balance"] is None or row[1] is None else group["balance"] + row[1]
            group["owned"] = None if group["owned"] is None or row[2] is None else group["owned"] + row[2]
    order = list(dict.fromkeys(SIDEBAR_GROUPS.values()))
    return render(request, "accounts/list.html", rows=rows, net_worth=net_worth, gross_total=gross_total,
                  recent_rows=recent_rows, lead=lead, held_total=held,
                  groups=sorted(groups.items(), key=lambda item: order.index(item[0])),
                  status=page_status.accounts(len(active), held))


@router.get("/currencies")
async def currency_accounts(request: Request):
    """Foreign money: held, worth, average rate, gains and spread, with one chart (Architecture › FX positions)."""
    c = container(request)
    asked = {"period": "ytd"} | dict(request.query_params)
    period_error = ""
    try:
        period = parse_period(asked, today(), c.reporting.first_activity_date())
    except LightningError as exc:  # say why this year is shown instead of the range asked for
        period, period_error = parse_period({"period": "ytd"}, today()), exc.message
    positions = c.reporting.fx_positions.all(period.start_text, period.end_text)
    # Investments priced in a foreign currency are foreign money too (audit 2026-10-15).
    for p in positions:
        p.investments, p.investments_unpriced = c.position.foreign_holdings(
            period.end_text, c.base_currency).get(p.currency, (None, False))
    shown, other = c.reporting.fx_positions.split(positions)
    chosen = next((p for p in shown if p.currency == request.query_params.get("currency")), shown[0] if shown else None)
    trend = None
    if chosen:
        points = [point for point in chosen.series]
        trend = charts.trend([point.day[:7] for point in points], [
            {"name": "Value of what you hold", "tone": "hold", "values": [point.value for point in points]},
            {"name": "What it cost", "tone": "other", "dashed": True, "values": [point.cost for point in points]}])
    totals = c.reporting.fx_positions.totals(positions)
    return render(request, "accounts/currencies.html", positions=shown, other=other, chosen=chosen, trend=trend,
                  totals=totals, period=period, period_error=period_error)


CONVERT_FIELDS = ("date", "from_account_id", "to_account_id", "sent", "received", "fee", "notes")


def convert_context(request: Request, values: dict, action: str, title: str, error: LightningError | None = None):
    """The Convert form (accounts of two currencies, amounts both ways, an optional fee)."""
    c = container(request)
    choices = [a for a in c.accounts.list(active_only=True) if a.account_type.value in ("CASH", "BANK", "BROKERAGE")]
    return dict(values=values, action=action, title=title, accounts=choices, back=values.get("return_to", "/accounts"),
                error=error.message if error else "", error_field=(error.field or "") if error else "")


def convert_values(form) -> dict:
    return {key: str(form.get(key, "")).strip() for key in CONVERT_FIELDS}


@router.get("/convert/quote")
async def convert_quote(request: Request):
    """The executed rate and, when the market has one for the day, how far it is from it (computed in Python)."""
    c = container(request)
    q = request.query_params
    try:
        answer = c.transactions.conversion_quote(q.get("date") or fmt_date(today()), int(q.get("from") or 0),
                                                 int(q.get("to") or 0), q.get("sent") or "", q.get("received") or "")
    except (LightningError, ValueError):
        answer = None
    return JSONResponse(answer or {})


@router.get("/{account_id:int}/convert")
async def new_conversion(request: Request, account_id: int):
    c = container(request)
    account = c.accounts.require_usable(account_id)
    other = next((a for a in c.accounts.list(active_only=True) if a.currency != account.currency
                  and a.account_type.value in ("CASH", "BANK", "BROKERAGE")), None)
    values = {"date": fmt_date(today()), "from_account_id": str(account.id),
              "to_account_id": str(other.id) if other else "", "sent": "", "received": "", "fee": "", "notes": "",
              "return_to": _safe_return(request.query_params.get("return_to"), f"/accounts/{account_id}")}
    return render(request, "accounts/convert.html",
                  **convert_context(request, values, f"/accounts/{account_id}/convert", "Convert money"))


@router.post("/{account_id:int}/convert")
async def save_conversion(request: Request, account_id: int):
    c = container(request)
    form = await request.form()
    values = convert_values(form) | {"return_to": _safe_return(form.get("return_to"), f"/accounts/{account_id}")}
    try:
        txn = c.transactions.record_conversion(
            values["date"], _account_id(values["from_account_id"], "from_account"),
            _account_id(values["to_account_id"], "to_account"), values["sent"], values["received"],
            values["fee"] or None, notes=values["notes"])
    except LightningError as exc:
        return render(request, "accounts/convert.html", status_code=400,
                      **convert_context(request, values, f"/accounts/{account_id}/convert", "Convert money", exc))
    return redirect(values["return_to"], f"Saved {txn.ref}.")


def _account_id(text: str, field: str) -> int:
    if not text.isdigit():
        raise ValidationError("Choose an account.", field)
    return int(text)


@router.get("/add-transaction")
async def pick_account_for_entry(request: Request):
    """The phone's add button on Accounts: choose the account, then its entry sheet (guideline C05.2)."""
    c = container(request)
    accounts = [a for a in c.accounts.list(active_only=True)
                if a.account_type.value not in ("PHYSICAL_ASSET", "OTHER_ASSET")]
    return render(request, "phone/accounts/pick.html", accounts=accounts)


@router.get("/new")
async def new_account(request: Request):
    values = {"account_type": request.query_params.get("type", "BANK"), "opening_balance": "",
              "currency": container(request).base_currency,
              "opening_balance_date": today().isoformat(), "institution": "", "owner_id": ""}
    return render(request, "accounts/form.html", **_form_context(request, values))


@router.post("/new")
async def create_account(request: Request):
    c = container(request)
    form = await request.form()
    values = {k: str(form.get(k, "")) for k in FIELDS}
    try:
        # The internal start date is intentionally not shown: users can enter their first
        # transaction on its real date, including history predating account setup.
        account = c.account_flows.open_account(
            name=values["name"], account_type=values["account_type"],
            opening_date="1900-01-01", opening_balance=values["opening_balance"],
            currency=values.get("currency") or c.base_currency,
            opening_balance_date=values["opening_balance_date"],
            institution=values["institution"], last4=values["last4"], notes=values["notes"],
            owner_id=int(values["owner_id"]) if values["owner_id"].isdigit() else None,
        )
    except LightningError as exc:
        return render(request, "accounts/form.html", status_code=400, **_form_context(request, values, error=exc))
    _remember_institution(c, values["institution"])
    if account.account_type.value == "GAMEYA":  # its terms are the next step (lightning/ui/routes/gameya.py)
        return redirect(f"/gameya/{account.id}", f"Account {account.label} is ready. Enter the circle's terms.")
    return redirect(f"/accounts/{account.id}?welcome=1", f"Account {account.label} is ready.")


@router.get("/{account_id:int}")
async def account_register(request: Request, account_id: int):
    account_type = container(request).accounts.get(account_id).account_type.value
    if account_type == "PHYSICAL_ASSET":
        from . import physical_items
        return physical_items.account_page(request, account_id)
    return register.page(request, account_id)


@router.post("/{account_id:int}/value")
async def update_other_asset_value(request: Request, account_id: int):
    c = container(request)
    account = c.accounts.get(account_id)
    form = await request.form()
    try:
        c.reporting.other_asset_values.save(account, str(form.get("date") or today()),
                                            str(form.get("value") or ""), str(form.get("notes") or ""))
    except LightningError as exc:
        return redirect(f"/accounts/{account_id}", exc.message)
    return redirect(f"/accounts/{account_id}", "Dated estimated value saved.")


def _transaction_popup_context(request, account, values, action, error=None, txn_id=None, split_categories=None):
    c = container(request)
    counterparties = c.counterparties.list_active()
    return dict(account=account, values=values, action=action, txn_id=txn_id,
                title="Edit transaction" if txn_id else "Add transaction",
                accounts=c.accounts.list(active_only=True),
                categories=[cat for cat in c.categories.pickable()],
                category_names={cat.id: c.categories.display_name(cat.id) for cat in c.categories.pickable()},
                category_parent_names={cat.id: cat.name for cat in c.categories.tree() if cat.depth == 1},
                counterparties=counterparties,
                counterparty_categories=register.counterparty_category_map(c, [row["name"] for row in counterparties]),
                owners=c.counterparties.list_owners(),
                split_categories=split_categories or [],
                return_to=str(values.get("return_to") or f"/accounts/{account.id}"),
                error=error.message if error else "", error_field=error.field if error else "")


def _category_id(request) -> str:
    """A category to start the entry with (Zakat's Record payment opens it with the Zakat category)."""
    text = str(request.query_params.get("category_id", ""))
    return text if text.isdigit() else ""


def _safe_return(value, fallback):
    value = str(value or "")
    return value if value.startswith("/") and not value.startswith("//") else fallback


@router.get("/{account_id:int}/transaction/new")
async def new_transaction_popup(request: Request, account_id: int):
    account = container(request).accounts.get(account_id)
    values = {"kind": "out", "date": fmt_date(today()), "amount": "", "category_id": _category_id(request),
              "counterparty": "", "owner_id": "", "to_account_id": "",
              "notes": "", "return_to": _safe_return(request.query_params.get("return_to"), f"/accounts/{account_id}")}
    return render(request, "transactions/form_popup.html",
                  **_transaction_popup_context(request, account, values, f"/accounts/{account_id}/transaction/new"))


@router.post("/{account_id:int}/transaction/new")
async def save_transaction_popup(request: Request, account_id: int):
    c = container(request)
    account = c.accounts.require_usable(account_id)
    form = await request.form()
    values = {key: str(form.get(key, "")) for key in
              ("kind", "date", "amount", "category_id", "counterparty", "owner_id", "to_account_id", "notes")}
    values["return_to"] = _safe_return(form.get("return_to"), f"/accounts/{account_id}")
    try:
        kind = values["kind"]
        if kind not in {"out", "in", "transfer"}:
            raise ValidationError("Choose Money out, Money in, or Transfer.", "kind")
        day = fmt_date(parse_date(values["date"], "date"))
        amount = to_decimal(values["amount"], "amount")
        if amount <= 0:
            raise ValidationError("Enter an amount greater than zero.", "amount")
        owner_id = int(values["owner_id"]) if values["owner_id"].isdigit() else None
        if owner_id is not None:
            party = c.counterparties.get(owner_id)
            if not party or not party["active"]:
                raise ValidationError("Choose an active owner.", "owner_id")
        if kind == "transfer":
            to_account = int(values["to_account_id"]) if values["to_account_id"].isdigit() else None
            if not to_account or to_account == account_id:
                raise ValidationError("Choose a different destination account.", "to_account_id")
            txn = c.transactions.record_transfer(day, account_id, to_account, amount,
                                                 notes=values["notes"], owner_id=owner_id)
        else:
            category_id = int(values["category_id"]) if values["category_id"].isdigit() else None
            if not category_id and values["counterparty"].strip():
                # Left empty: a rule decides first, then the counterparty's usual category, as in the register.
                category_id = register.category_when_empty(c, values["counterparty"].strip(), values["notes"],
                                                           -amount if kind == "out" else amount, account_id)
            if not category_id:
                raise ValidationError("Choose a category.", "category")
            category = c.categories.get(category_id)
            if kind == "out" and category.movement.value != "OUTFLOW":  # money in to an expense is a refund
                raise ValidationError("Choose a category that matches this transaction type.", "category")
            counterparty = _popup_counterparty(c, values["counterparty"])
            if counterparty and any(a.name.casefold() == counterparty.casefold()
                                    for a in c.accounts.list(active_only=True)):
                raise ValidationError("Choose Transfer and select the destination account explicitly.", "counterparty")
            if kind == "out":
                txn = c.transactions.record_outflow(day, account_id, amount, category_id,
                                                   counterparty=counterparty, notes=values["notes"], owner_id=owner_id)
            else:
                txn = c.transactions.record_inflow(day, account_id, amount, category_id,
                                                  counterparty=counterparty, notes=values["notes"], owner_id=owner_id)
        matched_reserve = c.reserves.auto_link_transaction(txn.id)
        feedback = register._budget_feedback(c, txn)
        if matched_reserve < 0:
            feedback = (feedback + " Several reserves match; choose beside the transaction in its account list.").strip()
        return redirect(values["return_to"], f"Saved {txn.ref}. {feedback}".strip())
    except (LightningError, ValueError) as exc:
        error = exc if isinstance(exc, LightningError) else ValidationError("Choose valid values for this transaction.")
        return render(request, "transactions/form_popup.html", status_code=400,
                      **_transaction_popup_context(request, account, values,
                                                   f"/accounts/{account_id}/transaction/new", error))


@router.get("/{account_id:int}/ownership/new")
async def new_ownership_change(request: Request, account_id: int):
    c = container(request)
    account = c.accounts.require_usable(account_id)
    values = {"mode": "assign", "date": today().isoformat(), "amount": "", "from_owner_id": "",
              "to_owner_id": "", "category_id": "", "notes": ""}
    return render(request, "accounts/ownership.html", account=account, values=values,
                  owners=c.counterparties.list_people(),
                  categories=[cat for cat in c.categories.pickable() if cat.movement.value == "OUTFLOW"],
                  action=f"/accounts/{account_id}/ownership/new", error="", error_field="")


@router.post("/{account_id:int}/ownership/new")
async def save_ownership_change(request: Request, account_id: int):
    c = container(request)
    account = c.accounts.require_usable(account_id)
    form = await request.form()
    values = {key: str(form.get(key, "")).strip() for key in
              ("mode", "date", "amount", "from_owner_id", "to_owner_id", "category_id", "notes")}
    action = f"/accounts/{account_id}/ownership/new"
    try:
        if values["mode"] == "expense":
            if values["from_owner_id"]:
                raise ValidationError("For an expense someone paid, set From to You.", "from_owner_id")
            owner_id = int(values["to_owner_id"]) if values["to_owner_id"].isdigit() else None
            category_id = int(values["category_id"]) if values["category_id"].isdigit() else None
            if owner_id is None:
                raise ValidationError("Choose the person who paid.", "to_owner_id")
            if category_id is None:
                raise ValidationError("Choose the expense category.", "category_id")
            txn = c.transactions.record_expense_paid_by_person(values["date"], account.id, values["amount"],
                                                               owner_id, category_id, values["notes"])
            c.planning.match_payments(today())
            c.reserves.auto_link_transaction(txn.id)
        elif values["mode"] == "assign":
            from_owner_id = int(values["from_owner_id"]) if values["from_owner_id"].isdigit() else None
            to_owner_id = int(values["to_owner_id"]) if values["to_owner_id"].isdigit() else None
            if from_owner_id is None and to_owner_id is None:
                raise ValidationError("Choose a person to change ownership with.", "to_owner_id")
            txn = c.transactions.change_cash_ownership(values["date"], account.id, values["amount"],
                                                       from_owner_id, to_owner_id, values["notes"])
        else:
            raise ValidationError("Choose what happened.", "mode")
    except (LightningError, ValueError) as exc:
        error = exc if isinstance(exc, LightningError) else ValidationError("Check the date, amount, and choices.")
        return render(request, "accounts/ownership.html", status_code=400, account=account, values=values,
                      owners=c.counterparties.list_people(),
                      categories=[cat for cat in c.categories.pickable() if cat.movement.value == "OUTFLOW"],
                      action=action, error=error.message, error_field=error.field or "")
    return redirect(f"/transactions/{txn.id}", f"Saved {txn.ref}. Ownership in {account.label} is updated.")


def _popup_counterparty(c, raw_value):
    raw = str(raw_value or "").strip()
    if not raw:
        return ""
    party = c.counterparties.resolve(raw)
    if party:
        if not party["active"]:
            raise ValidationError("That Counterparty is archived. Activate it before using it.", "counterparty")
        return party["name"]
    suggestions = c.counterparties.suggestions(raw)
    if suggestions:
        names = ", ".join(name for name, _ in suggestions)
        raise ValidationError(f"This name resembles a saved Counterparty ({names}). Choose that name from the list or review it first.", "counterparty")
    return raw


def _bank_check_page(request, c, account_id: int, through: str, raw_balance: str, error: str = "", status_code=200):
    """What does your bank say? The account's balance against the bank's, on one date."""
    account = c.accounts.get(account_id)
    check = None
    try:
        through = c.reconciliation.validate_date(through.strip() or today().isoformat())
        if raw_balance.strip():
            check = c.reconciliation.check(account_id, through, c.reconciliation.parse_bank_balance(raw_balance))
    except LightningError as exc:
        error = exc.message
    dated = len(through) == 10 and through[4] == "-"
    return render(request, "accounts/reconcile.html", account=account, through=through, balance_input=raw_balance,
                  lightning_balance=c.reconciliation.balance(account_id, through) if dated else None,
                  check=check, checked_through=c.reconciliation.checked_through(account_id), error=error,
                  month_start=through[:8] + "01" if dated else "", status_code=status_code)


@router.post("/{account_id:int}/reconcile/close")
async def close_checked_history(request: Request, account_id: int):
    c = container(request)
    form = await request.form()
    try:
        c.reconciliation.close(account_id, str(form.get("date", "")), str(form.get("balance", "")))
    except LightningError as exc:
        return redirect(f"/accounts/{account_id}/reconcile", exc.message)
    return redirect(f"/accounts/{account_id}/reconcile", "Checked history is now protected. Unlock it before making corrections.")


@router.post("/{account_id:int}/reconcile/unlock")
async def unlock_checked_history(request: Request, account_id: int):
    container(request).reconciliation.unlock(account_id)
    return redirect(f"/accounts/{account_id}/reconcile", "Checked history unlocked.")


@router.get("/{account_id:int}/reconcile")
async def reconcile_account(request: Request, account_id: int):
    qp = request.query_params
    return _bank_check_page(request, container(request), account_id, str(qp.get("date", "")), str(qp.get("balance", "")))


@router.post("/{account_id:int}/reconcile")
async def adjust_to_bank(request: Request, account_id: int):
    """Post the small difference as one balance adjustment."""
    c = container(request)
    form = await request.form()
    raw_date, raw_balance = str(form.get("date", "")), str(form.get("balance", ""))
    try:
        through = c.reconciliation.validate_date(raw_date)
        txn = c.reconciliation.adjust(account_id, through, c.reconciliation.parse_bank_balance(raw_balance))
    except LightningError as exc:
        return _bank_check_page(request, c, account_id, raw_date, raw_balance, exc.message, status_code=400)
    return redirect(f"/accounts/{account_id}", f"Balance adjustment {txn.ref} posted. The account now matches your bank.")


@router.post("/{account_id:int}/investment-entry")
async def investment_entry(request: Request, account_id: int):
    """Add a stock/fund trade or dividend inline from this account's register."""
    result = await register.create_investment_entry(request, account_id)
    if not isinstance(result, tuple):
        return result
    txn, _ = result
    c = container(request)
    c.reserves.auto_link_transaction(txn.id)
    feedback = register._budget_feedback(container(request), txn)
    return redirect(f"/accounts/{account_id}?date={txn.date}", f"Saved {txn.ref}. {feedback}".strip())


@router.post("/{account_id:int}/register")
async def register_entry(request: Request, account_id: int):
    """Save one row typed into the register, then come back ready for the next one."""
    result = await register.create(request, account_id)
    if not isinstance(result, tuple):
        return result  # the page again, with the error
    txn, _ = result
    feedback = register._budget_feedback(container(request), txn)
    return redirect(f"/accounts/{account_id}?date={txn.date}", f"Saved {txn.ref}. {feedback}".strip())


@router.post("/{account_id:int}/register/{txn_id:int}")
async def register_update(request: Request, account_id: int, txn_id: int):
    result = await register.update(request, account_id, txn_id)
    if not isinstance(result, tuple):
        return result
    txn, _ = result
    c = container(request)
    c.reserves.auto_link_transaction(txn.id)
    message = f"Saved as {txn.ref}. The original transaction is kept in history." if txn.id != txn_id else f"Saved {txn.ref}."
    message = f"{message} {register._budget_feedback(container(request), txn)}".strip()
    return redirect(f"/accounts/{account_id}", message)


@router.get("/{account_id:int}/edit")
async def edit_account(request: Request, account_id: int):
    c = container(request)
    a = c.accounts.get(account_id)
    opening_id = c.transactions.opening_txn_id(account_id)
    opening_txn = c.transactions.get(opening_id) if opening_id else None
    first_activity = c.transactions.earliest_activity(account_id)
    values = {
        "name": a.name, "account_type": "CASH_AT_HAND" if a.cash_at_hand else a.account_type.value,
        "opening_date": a.opening_date, "opening_balance": str(c.account_flows.opening_of(a)),
        "opening_balance_date": opening_txn.date if opening_txn else (first_activity or today().isoformat()),
        "institution": a.institution or "",
        "last4": a.last4 or "",
        "notes": a.notes,
        "owner_id": str(next((line.owner_id for line in opening_txn.lines if line.owner_id is not None), ""))
        if opening_txn else "",
    }
    return render(request, "accounts/form.html", **_form_context(request, values, account=a))


@router.post("/{account_id:int}/edit")
async def update_account(request: Request, account_id: int):
    c = container(request)
    account = c.accounts.get(account_id)
    form = await request.form()
    values = {k: str(form.get(k, "")) for k in FIELDS}
    if "last4" not in form:  # the form no longer shows it: keep what is stored
        values["last4"] = account.last4 or ""
    try:
        account = c.account_flows.update_account(
            account_id, name=values["name"], account_type=values["account_type"],
            opening_date=account.opening_date, opening_balance=str(c.account_flows.opening_of(account)),
            institution=values["institution"], last4=values["last4"], notes=values["notes"],
            opening_balance_date=values["opening_balance_date"],
            owner_id=int(values["owner_id"]) if values["owner_id"].isdigit() else None,
        )
    except LightningError as exc:
        return render(request, "accounts/form.html", status_code=400,
                      **_form_context(request, values, account=account, error=exc))
    _remember_institution(c, values["institution"])
    return redirect(f"/accounts/{account.id}", "Account saved.")


@router.post("/{account_id:int}/deactivate")
async def deactivate(request: Request, account_id: int):
    c = container(request)
    try:
        account = c.account_flows.deactivate(account_id)
    except LightningError as exc:
        return redirect(f"/accounts/{account_id}", exc.message)
    return redirect(f"/accounts/{account.id}", f"{account.label} is now inactive.")


@router.post("/{account_id:int}/pockets")
async def add_pocket(request: Request, account_id: int):
    """Add a currency to a broker: a cash pocket shown inside the broker's one row (owner decision 2026-10-16)."""
    c = container(request)
    form = await request.form()
    try:
        pocket = c.accounts.add_pocket(account_id, str(form.get("currency", "")))
    except LightningError as exc:
        return redirect(f"/accounts/{account_id}", exc.message)
    return redirect(f"/accounts/{account_id}", f"{c.accounts.get(account_id).name} now holds {pocket.currency}.")


@router.post("/{account_id:int}/spendable")
async def set_spendable(request: Request, account_id: int):
    """Count this account's cash as spendable or keep it apart (Free cash, Safe to spend, payday)."""
    c = container(request)
    form = await request.form()
    choice = {"yes": True, "no": False}.get(str(form.get("spendable", "")))
    account = c.accounts.get(account_id)
    if choice is not None and choice == replace(account, spendable=None).counts_as_spendable(c.base_currency):
        choice = None  # the default: store no override
    account = c.accounts.set_spendable(account_id, choice)
    spendable = account.counts_as_spendable(c.base_currency)
    return redirect(f"/accounts/{account.id}",
                    "Its cash now counts as spendable." if spendable else "Its cash is now kept apart from spendable cash.")


@router.post("/{account_id:int}/reactivate")
async def reactivate(request: Request, account_id: int):
    account = container(request).account_flows.reactivate(account_id)
    return redirect(f"/accounts/{account.id}", f"{account.label} is active again.")
