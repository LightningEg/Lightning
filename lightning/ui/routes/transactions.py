from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from lightning.transactions.domain import TxnFilter, TxnStatus

from lightning.core.errors import LightningError
from lightning.core.dates import fmt_date, parse_date
from lightning.core.money import to_decimal
from lightning.core.errors import ValidationError

from . import register
from ..web import container, redirect, render
from ..i18n import translate

router = APIRouter()


@router.get("/transactions/{txn_id:int}/edit-popup")
async def edit_transaction_popup(request: Request, txn_id: int):
    c = container(request)
    txn = c.transactions.get(txn_id)
    if txn.type.value not in {"OUT", "IN", "TRF"} or txn.is_void:
        return redirect(f"/transactions/{txn_id}", "This transaction is edited from its account or investment workflow.")
    cash_lines = [line for line in txn.lines if c.assets.get_asset(line.asset_id).is_cash]
    if not cash_lines:
        return redirect(f"/transactions/{txn_id}", "This transaction has no cash account to edit.")
    if txn.type.value == "TRF":
        source = next((line for line in cash_lines if line.quantity < 0), cash_lines[0])
        target = next((line for line in cash_lines if line.account_id != source.account_id), None)
        kind, category_id, amount = "transfer", "", abs(source.quantity)
    else:
        source = cash_lines[0]
        target = None
        kind = "out" if source.quantity < 0 else "in"
        split_categories = sorted({line.category_id for line in cash_lines if line.category_id})
        is_split = len(cash_lines) > 1
        category_id = "" if is_split else str(source.category_id or "")
        amount = abs(sum((line.quantity for line in cash_lines), start=0)) if is_split else abs(source.quantity)
    owner_id = next((line.owner_id for line in txn.lines if line.owner_id is not None), None)
    values = {"kind": kind, "date": txn.date, "amount": str(amount), "category_id": category_id,
              "counterparty": txn.counterparty or "", "owner_id": str(owner_id or ""),
              "to_account_id": str(target.account_id) if target else "", "notes": txn.notes,
              "return_to": _back(request, f"/accounts/{source.account_id}"), "account_id": str(source.account_id)}
    from .accounts import _transaction_popup_context
    return render(request, "transactions/form_popup.html", **_transaction_popup_context(
        request, c.accounts.get(source.account_id), values, f"/transactions/{txn_id}/edit-popup", txn_id=txn_id,
        split_categories=[c.categories.display_name(category_id) for category_id in split_categories]
        if txn.type.value != "TRF" and is_split else []))


@router.post("/transactions/{txn_id:int}/edit-popup")
async def save_transaction_popup(request: Request, txn_id: int):
    c = container(request)
    form = await request.form()
    values = {key: str(form.get(key, "")) for key in
              ("kind", "date", "amount", "category_id", "counterparty", "owner_id", "to_account_id", "notes", "account_id")}
    values["revision"] = form.get("revision")
    from .accounts import _safe_return, _transaction_popup_context
    txn = c.transactions.get(txn_id)
    account_id = int(values["account_id"]) if values["account_id"].isdigit() else txn.lines[0].account_id
    account = c.accounts.get(account_id)
    values["return_to"] = _safe_return(form.get("return_to"), f"/accounts/{account_id}")
    cash_lines = [line for line in txn.lines if c.assets.get_asset(line.asset_id).is_cash]
    split_categories = {line.category_id for line in cash_lines if line.category_id}
    try:
        with c.db.transaction():
            c.transactions.require_revision(txn_id, values["revision"])
            if txn.type.value == "OUT" and len(cash_lines) > 1:
                from .accounts import _popup_counterparty
                cp = _popup_counterparty(c, values["counterparty"])
                updated = c.transactions.update_metadata(txn_id, values["date"], cp, values["notes"])
                return redirect(values["return_to"], f"Saved {updated.ref}; split amounts are unchanged.")
            if values["kind"] not in {"out", "in", "transfer"}:
                raise ValidationError("Choose a transaction type.", "kind")
            day = fmt_date(parse_date(values["date"], "date"))
            amount = to_decimal(values["amount"], "amount")
            if amount <= 0: raise ValidationError("Enter an amount greater than zero.", "amount")
            owner_id = int(values["owner_id"]) if values["owner_id"].isdigit() else None
            if values["kind"] == "transfer":
                other = int(values["to_account_id"]) if values["to_account_id"].isdigit() else None
                if not other or other == account_id: raise ValidationError("Choose a different destination account.", "to_account_id")
                signed = -amount
                category_id = None
            else:
                category_id = int(values["category_id"]) if values["category_id"].isdigit() else None
                if not category_id: raise ValidationError("Choose a category.", "category")
                if values["kind"] == "out" and c.categories.get(category_id).movement.value != "OUTFLOW":  # in: a refund
                    raise ValidationError("Choose a category that matches this transaction type.", "category")
                other = None
                signed = -amount if values["kind"] == "out" else amount
            from .accounts import _popup_counterparty
            cp = _popup_counterparty(c, values["counterparty"])
            updated = c.transactions.update_in_account(txn_id, account_id, day, signed, category_id, other,
                                                       counterparty=cp, notes=values["notes"], owner_id=owner_id)
            c.reserves.auto_link_transaction(updated.id)
            return redirect(values["return_to"], f"Saved {updated.ref}. {register._budget_feedback(c, updated)}".strip())
    except (LightningError, ValueError) as exc:
        error = exc if isinstance(exc, LightningError) else ValidationError("Choose valid values for this transaction.")
        return render(request, "transactions/form_popup.html", status_code=400,
                      **_transaction_popup_context(request, account, values, f"/transactions/{txn_id}/edit-popup", error,
                                                   txn_id, [c.categories.display_name(category_id)
                                                            for category_id in split_categories]
                                                   if txn.type.value == "OUT" and len(cash_lines) > 1 else []))


@router.get("/transactions/{txn_id:int}/convert/edit")
async def edit_conversion(request: Request, txn_id: int):
    from .accounts import convert_context
    c = container(request)
    txn = c.transactions.get(txn_id)
    described = c.transactions.conversion_of(txn)
    if described is None or txn.is_void:
        return redirect(f"/transactions/{txn_id}", "This is not an active conversion.")
    values = {"date": txn.date, "from_account_id": str(described.src_account_id),
              "to_account_id": str(described.dst_account_id), "sent": str(described.sent),
              "received": str(described.received), "fee": str(described.fee) if described.fee else "",
              "notes": txn.notes, "return_to": f"/transactions/{txn_id}",
              "revision": c.transactions.revision(txn_id)}
    return render(request, "accounts/convert.html",
                  **convert_context(request, values, f"/transactions/{txn_id}/convert/edit", "Edit conversion"))


@router.post("/transactions/{txn_id:int}/convert/edit")
async def save_edited_conversion(request: Request, txn_id: int):
    from .accounts import _account_id, convert_context, convert_values
    c = container(request)
    form = await request.form()
    values = convert_values(form) | {"return_to": f"/transactions/{txn_id}", "revision": form.get("revision")}
    try:
        with c.db.transaction():
            c.transactions.require_revision(txn_id, values["revision"])
            txn = c.transactions.update_conversion(
                txn_id, values["date"], _account_id(values["from_account_id"], "from_account"),
                _account_id(values["to_account_id"], "to_account"), values["sent"], values["received"],
                values["fee"] or None, notes=values["notes"])
    except LightningError as exc:
        return render(request, "accounts/convert.html", status_code=400,
                      **convert_context(request, values, f"/transactions/{txn_id}/convert/edit", "Edit conversion", exc))
    return redirect(f"/transactions/{txn.id}", f"Saved {txn.ref}.")


@router.get("/transactions/{txn_id:int}/ownership/edit")
async def edit_ownership_change(request: Request, txn_id: int):
    c = container(request)
    txn = c.transactions.get(txn_id)
    if not c.transactions._is_ownership_transaction(txn) or txn.is_void:
        return redirect(f"/transactions/{txn_id}", "This is not an active ownership entry.")
    cash = [line for line in txn.lines if c.assets.get_asset(line.asset_id).is_cash]
    expense = next((line for line in cash if line.effect.value == "OUTFLOW"), None)
    owner_line = next((line for line in cash if line.owner_id is not None and line.quantity > 0), None)
    if expense:
        mode, amount, from_owner, to_owner = "expense", abs(expense.quantity), "", owner_line.owner_id if owner_line else ""
        category_id = expense.category_id or ""
    else:
        debit = next((line for line in cash if line.quantity < 0), None)
        credit = next((line for line in cash if line.quantity > 0), None)
        mode = "assign"
        amount = abs(debit.quantity) if debit else 0
        from_owner = debit.owner_id if debit and debit.owner_id is not None else ""
        to_owner = credit.owner_id if credit and credit.owner_id is not None else ""
        category_id = ""
    account = c.accounts.get(cash[0].account_id)
    values = {"mode": mode, "date": txn.date, "amount": str(amount),
              "from_owner_id": str(from_owner), "to_owner_id": str(to_owner),
              "category_id": str(category_id), "notes": txn.notes,
              "revision": c.transactions.revision(txn_id)}
    return render(request, "accounts/ownership.html", account=account, values=values,
                  owners=c.counterparties.list_people(),
                  categories=[cat for cat in c.categories.pickable() if cat.movement.value == "OUTFLOW"],
                  action=f"/transactions/{txn_id}/ownership/edit", error="", error_field="", txn_id=txn_id)


@router.post("/transactions/{txn_id:int}/ownership/edit")
async def save_ownership_change(request: Request, txn_id: int):
    c = container(request)
    txn = c.transactions.get(txn_id)
    if not c.transactions._is_ownership_transaction(txn):
        return redirect(f"/transactions/{txn_id}", "This is not an ownership entry.")
    cash = next((line for line in txn.lines if c.assets.get_asset(line.asset_id).is_cash), None)
    account = c.accounts.get(cash.account_id if cash else txn.lines[0].account_id)
    form = await request.form()
    values = {key: str(form.get(key, "")).strip() for key in
              ("mode", "date", "amount", "from_owner_id", "to_owner_id", "category_id", "notes")}
    values["revision"] = form.get("revision")
    action = f"/transactions/{txn_id}/ownership/edit"
    try:
        with c.db.transaction():
            c.transactions.require_revision(txn_id, values["revision"])
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
                                                                   owner_id, category_id, values["notes"], txn_id)
            elif values["mode"] == "assign":
                from_owner_id = int(values["from_owner_id"]) if values["from_owner_id"].isdigit() else None
                to_owner_id = int(values["to_owner_id"]) if values["to_owner_id"].isdigit() else None
                if from_owner_id is None and to_owner_id is None:
                    raise ValidationError("Choose a person to change ownership with.", "to_owner_id")
                txn = c.transactions.change_cash_ownership(values["date"], account.id, values["amount"],
                                                           from_owner_id, to_owner_id, values["notes"], txn_id)
            else:
                raise ValidationError("Choose what happened.", "mode")
            return redirect(f"/accounts/{account.id}", f"Saved {txn.ref}. Ownership is updated.")
    except (LightningError, ValueError) as exc:
        error = exc if isinstance(exc, LightningError) else ValidationError("Check the date, amount, and choices.")
        return render(request, "accounts/ownership.html", status_code=400, account=account, values=values,
                      owners=c.counterparties.list_people(),
                      categories=[cat for cat in c.categories.pickable() if cat.movement.value == "OUTFLOW"],
                      action=action, error=error.message, error_field=error.field or "", txn_id=txn_id)


def _back(request: Request, default: str) -> str:
    back = request.query_params.get("back", "")
    return back if back.startswith("/") and not back.startswith("//") else default


@router.get("/transactions")
async def all_accounts(request: Request):
    """Every account in one register."""
    return register.page(request, None)


def _view_scope(c, form_or_query):
    raw = str(form_or_query.get("account_id", "") or "").strip()
    if not raw:
        return None
    if not raw.isdigit() or int(raw) < 1:
        raise ValidationError("Choose a valid account.")
    return c.accounts.get(int(raw)).id


@router.post("/transactions/views")
async def save_register_view(request: Request):
    c = container(request)
    form = await request.form()
    try:
        scope = _view_scope(c, form)
        view_id = c.saved_views.save(str(form.get("name", "")), dict(form), scope)
    except LightningError as exc:
        return redirect(f"/accounts/{form.get('account_id')}" if str(form.get("account_id", "")).isdigit()
                        else "/transactions", exc.message)
    target = f"/accounts/{scope}" if scope else "/transactions"
    return redirect(f"{target}?saved_view={view_id}", "Saved view.")


@router.post("/transactions/views/{view_id:int}/delete")
async def delete_register_view(request: Request, view_id: int):
    c = container(request)
    form = await request.form()
    try:
        scope = _view_scope(c, form)
        c.saved_views.delete(view_id, scope)
    except LightningError as exc:
        return redirect(f"/accounts/{scope}" if 'scope' in locals() and scope else "/transactions", exc.message)
    return redirect(f"/accounts/{scope}" if scope else "/transactions", "Deleted saved view.")


@router.get("/transactions/views/{view_id:int}/report")
async def saved_register_view_report(request: Request, view_id: int):
    c = container(request)
    try:
        scope = _view_scope(c, request.query_params)
        view = c.saved_views.get(view_id, scope)
        report = c.saved_views.report(view)
    except LightningError as exc:
        return redirect("/transactions", exc.message)
    return render(request, "saved_view_report.html", view=view, report=report,
                  export_url=f"/exports/views/{view_id}" + (f"?account_id={scope}" if scope else ""),
                  register_url=f"/accounts/{scope}" if scope else "/transactions")


@router.get("/transactions/deleted")
async def deleted_transactions(request: Request):
    c = container(request)
    rows, _ = c.transactions.find(TxnFilter(include_void=True, limit=1000))
    # System revaluations replaced by a recalculation were never deleted by the
    # user and can't be restored, so they stay out of this list.
    replaced = c.transactions.replaced_revaluation_ids()
    deleted = [row for row in rows if row.status == TxnStatus.VOID and row.id not in replaced]
    return render(request, "transactions/deleted.html", rows=deleted)


@router.post("/transactions/register")
async def all_accounts_entry(request: Request):
    result = await register.create(request, None)
    if not isinstance(result, tuple):
        return result
    txn, entry = result
    matched_reserve = container(request).reserves.auto_link_transaction(txn.id)
    feedback = register._budget_feedback(container(request), txn)
    if matched_reserve < 0:
        feedback = (feedback + " Several reserves match; choose beside the transaction in its account list.").strip()
    return redirect(f"/transactions?date={txn.date}&new_acct={entry['account_id']}",
                    f"Saved {txn.ref}. {feedback}".strip())


@router.post("/transactions/register/{txn_id:int}")
async def all_accounts_update(request: Request, txn_id: int):
    result = await register.update(request, None, txn_id)
    if not isinstance(result, tuple):
        return result
    txn, _ = result
    matched_reserve = container(request).reserves.auto_link_transaction(txn.id)
    message = (f"Saved as {txn.ref}. The original transaction is kept in history." if txn.id != txn_id
               else f"Saved {txn.ref}.")
    feedback = register._budget_feedback(container(request), txn)
    if matched_reserve < 0:
        feedback = (feedback + " Several reserves match; choose beside the transaction in its account list.").strip()
    message = f"{message} {feedback}".strip()
    return redirect("/transactions", message)


@router.get("/transactions/{txn_id:int}")
async def transaction_detail(request: Request, txn_id: int):
    c = container(request)
    txn = c.transactions.get(txn_id)
    lines = []
    cash_effects = []
    for line in txn.lines:
        asset = c.assets.get_asset(line.asset_id)
        account = c.accounts.get(line.account_id)
        lines.append(dict(
            ref=txn.line_ref(line), account=account.label, account_id=line.account_id,
            asset=asset.code, quantity=line.quantity, amount_base=line.amount_base,
            effect=line.effect.value, category=c.categories.get(line.category_id).label if line.category_id else "",
            memo=line.memo, owner_id=line.owner_id,
            owner_name=c.counterparties.get(line.owner_id)["name"] if line.owner_id else "",
        ))
        if asset.is_cash and line.quantity:
            cash_effects.append({"account": account.label, "quantity": line.quantity, "currency": account.currency,
                                 "owner": c.counterparties.get(line.owner_id)["name"] if line.owner_id else "you"})
    can_split = txn.type.value == "OUT" and bool(txn.lines) and all(
        c.assets.get_asset(line.asset_id).is_cash for line in txn.lines)
    expense_categories = [{"id": cat.id, "label": c.categories.display_name(cat.id)}
                          for cat in c.categories.pickable() if cat.movement.value == "OUTFLOW"]
    split_lines = [{"category_id": line.category_id, "amount": -line.quantity}
                   for line in txn.lines if line.category_id is not None]
    budget_impacts = []
    expense_lines = [line for line in txn.lines if line.category_id and line.effect.value == "OUTFLOW"]
    if expense_lines and not txn.is_void:
        budget_month = c.budgets.month_view(txn.date[:7])
        budget_by_id = {line.category_id: line for section in budget_month.sections for line in section.lines}
        seen_categories = set()
        for posting in expense_lines:
            if posting.category_id in seen_categories:
                continue
            seen_categories.add(posting.category_id)
            budget_line = budget_by_id.get(posting.category_id)
            if budget_line:
                shown = budget_line
                if shown.remaining is None and shown.covered:
                    parent = c.categories.get(posting.category_id).parent_id
                    while parent:
                        ancestor = budget_by_id.get(parent)
                        if ancestor and ancestor.remaining is not None:
                            shown = ancestor
                            break
                        parent = c.categories.get(parent).parent_id
                budget_impacts.append({"name": budget_line.name, "remaining": budget_line.remaining,
                                       "covered_by": shown.name if shown is not budget_line else "",
                                       "covered_remaining": shown.remaining if shown is not budget_line else None,
                                       "month": txn.date[:7]})
    return render(request, "transactions/detail.html", txn=txn, summary=c.transactions.summarize(txn),
                  is_ownership=c.transactions._is_ownership_transaction(txn),
                  conversion=c.transactions.conversion_of(txn), conversion_spread=c.transactions.conversion_spread(txn),
                  replaced_revaluation=txn.id in c.transactions.replaced_revaluation_ids(),
                  lines=lines, history=c.transactions.history(txn_id), can_split=can_split, revision=c.transactions.revision(txn_id),
                  cash_effects=cash_effects,
                  expense_categories=expense_categories, split_lines=split_lines,
                  budget_impacts=budget_impacts,
                  reserve_links=c.reserves.links_for_transaction(txn_id), reserves=c.reserves.list_active())


@router.post("/transactions/{txn_id:int}/split")
async def update_transaction_split(request: Request, txn_id: int):
    c = container(request)
    form = await request.form()
    category_ids, amounts = form.getlist("split_category_id"), form.getlist("split_amount")
    allocations = []
    try:
        for category_id, amount in zip(category_ids, amounts):
            if not str(category_id).strip() and not str(amount).strip():
                continue
            if not str(category_id).strip() or not str(amount).strip():
                raise LightningError("Choose a category and amount for every split row.")
            allocations.append((int(category_id), str(amount)))
        with c.db.transaction():
            c.transactions.require_revision(txn_id, form.get("revision"))
            txn = c.transactions.update_expense_split(txn_id, allocations)
    except (ValueError, LightningError) as exc:
        msg = exc.message if isinstance(exc, LightningError) else "Choose a valid category for each split row."
        return redirect(f"/transactions/{txn_id}", msg)
    return redirect(f"/transactions/{txn_id}", f"Updated {txn.ref} category split.")


@router.post("/transactions/{txn_id:int}/reserve")
async def link_transaction_reserve(request: Request, txn_id: int):
    c = container(request)
    form = await request.form()
    action = str(form.get("action", "link"))
    try:
        reserve_id = int(str(form.get("reserve_id", "")))
        if action == "unlink":
            c.reserves.unlink_expense(reserve_id, txn_id)
            return redirect(f"/transactions/{txn_id}", "Removed the payment from its reserve.")
        if action != "link":
            raise LightningError("Choose a valid reserve action.")
        c.reserves.set_expense_link(reserve_id, txn_id, str(form.get("amount", "")))
    except (ValueError, LightningError) as exc:
        msg = exc.message if isinstance(exc, LightningError) else "Choose a reserve."
        return redirect(_back(request, f"/transactions/{txn_id}"), msg)
    return redirect(_back(request, f"/transactions/{txn_id}"), "Assigned this payment to its reserve.")


@router.post("/transactions/{txn_id:int}/void")
async def void_transaction(request: Request, txn_id: int):
    try:
        txn = container(request).transactions.void(txn_id)
    except LightningError as exc:
        return redirect(_back(request, f"/transactions/{txn_id}"), exc.message)
    return redirect(_back(request, f"/transactions/{txn.id}"), f"{txn.ref} is void — it no longer counts.")


@router.post("/transactions/{txn_id:int}/delete")
async def delete_transaction(request: Request, txn_id: int):
    c = container(request)
    try:
        reevaluation = c.transactions.get(txn_id).type.value == "VAL"
        c.transactions.delete_many([txn_id])
        if reevaluation:
            c.reevaluations.process_due()
    except LightningError as exc:
        if request.headers.get("x-requested-with") == "fetch":  # the phone's swipe shows a refusal as is
            return PlainTextResponse(exc.message, 409)
        return redirect(_back(request, f"/transactions/{txn_id}"), exc.message)
    if request.headers.get("x-requested-with") == "fetch":
        return PlainTextResponse("Deleted.")
    return redirect(_back(request, "/transactions"), "Transaction deleted. You can restore it from its history page.")


@router.post("/transactions/bulk-delete")
async def delete_transactions(request: Request):
    c = container(request)
    form = await request.form()
    ids = [int(value) for value in form.getlist("txn_ids") if str(value).isdigit()]
    back = str(form.get("back", ""))
    destination = back if back.startswith("/") and not back.startswith("//") else "/transactions"
    if not ids:
        return redirect(destination, "Choose at least one transaction.")
    try:
        reevaluation = any(c.transactions.get(txn_id).type.value == "VAL" for txn_id in ids)
        count = c.transactions.delete_many(ids)
        if reevaluation:
            c.reevaluations.process_due()
    except LightningError as exc:
        return redirect(destination, exc.message)
    return redirect(destination, f"Deleted {count} transaction(s). You can restore them from history.")


@router.post("/transactions/bulk-category")
async def categorize_transactions(request: Request):
    """Bulk edit: one category for every selected money-in or money-out row."""
    c = container(request)
    form = await request.form()
    ids = [int(value) for value in form.getlist("txn_ids") if str(value).isdigit()]
    back = str(form.get("back", ""))
    destination = back if back.startswith("/") and not back.startswith("//") else "/transactions"
    if not ids:
        return redirect(destination, "Choose at least one transaction.")
    if not str(form.get("category_id", "")).isdigit():
        return redirect(destination, "Choose a category to give the selected rows.")
    try:
        category_id = int(str(form.get("category_id")))
        changed, skipped = c.transactions.set_category(ids, category_id)
    except LightningError as exc:
        return redirect(destination, exc.message)
    name = c.categories.get(category_id).name
    message = f"{name} is now the category of {len(changed)} row{'s' if len(changed) != 1 else ''}."
    if skipped:
        message += (f" {len(skipped)} left as {'they were' if len(skipped) != 1 else 'it was'}: transfers, investment rows, "
                    "split expenses and rows going the other way keep their own category.")
    return redirect(destination, message)


@router.post("/transactions/bulk-edit")
async def bulk_edit_transactions(request: Request):
    """Edit many rows at once with only the fields the user changed on the edited row (U2)."""
    c = container(request)
    form = await request.form()
    ids = [int(value) for value in form.getlist("txn_ids") if str(value).isdigit()]
    back = str(form.get("back", ""))
    destination = back if back.startswith("/") and not back.startswith("//") else "/transactions"
    def respond(message, *, error=False):
        response = redirect(destination, message)
        if request.headers.get("X-Requested-With") == "fetch":
            if error:
                return JSONResponse({"error": translate(message, c.settings.get("locale"))}, status_code=400)
            return JSONResponse({"location": response.headers["location"]})
        return response
    if not ids:
        return respond("Choose at least one transaction.", error=True)
    changes: dict = {}
    try:
        for key in ("date", "notes"):
            if key in form:
                changes[key] = str(form.get(key, "")).strip()
        if "counterparty" in form:
            name = str(form.get("counterparty", "")).strip()
            if c.accounts.find_by_text(name) is not None:
                raise ValidationError("Turn a row into a transfer one row at a time.", "counterparty")
            changes["counterparty"] = name
        if "category" in form or "category_choice" in form:
            choice = str(form.get("category_choice", "")).strip()
            category = c.categories.get(int(choice)) if choice.isdigit() else c.categories.find_by_text(str(form.get("category", "")))
            changes["category_id"] = category.id
        if "whom" in form:
            party = c.counterparties.resolve(str(form.get("whom", "")).strip())
            if not party or not party["active"]:
                raise ValidationError("Choose a saved Counterparty in Held for.", "whom")
            changes["owner_id"] = party["id"]
        if not changes:
            return respond("Nothing changed on the selected rows.", error=True)
        with c.db.transaction():
            changed, skipped = c.transactions.bulk_update(ids, changes)
            if "owner_id" in changes:
                for txn_id in changed:
                    txn = c.transactions.get(txn_id)
                    cash = next((ln for ln in txn.lines if c.assets.get_asset(ln.asset_id).is_cash), None)
                    if cash:
                        c.money_from_others.sync_transaction(txn.id, txn.date, str(form.get("whom")).strip(),
                                                             cash.account_id, cash.quantity, txn.notes)
    except LightningError as exc:
        return respond(exc.message, error=True)
    message = f"Changed {len(changed)} row{'s' if len(changed) != 1 else ''}."
    if skipped:
        message += (f" {len(skipped)} left as {'they were' if len(skipped) != 1 else 'it was'}: transfers, investment rows, "
                    "split expenses and rows going the other way keep their own values.")
    return respond(message)


@router.post("/transactions/{txn_id:int}/restore")
async def restore_transaction(request: Request, txn_id: int):
    try:
        c = container(request)
        txn = c.transactions.restore(txn_id)
        if txn.type.value == "VAL":
            c.reevaluations.process_due()
    except LightningError as exc:
        if request.headers.get("x-requested-with") == "fetch":
            return PlainTextResponse(exc.message, 409)
        return redirect(f"/transactions/{txn_id}", exc.message)
    if request.headers.get("x-requested-with") == "fetch":
        return PlainTextResponse(f"{txn.ref} restored.")
    return redirect(_back(request, f"/transactions/{txn.id}"), f"{txn.ref} restored.")


@router.get("/t/{ref}")
async def by_ref(request: Request, ref: str):
    txn = container(request).transactions.get_by_ref(ref)
    return redirect(f"/transactions/{txn.id}")
