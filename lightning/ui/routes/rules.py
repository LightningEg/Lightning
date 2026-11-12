"""Settings › Rules: rules with conditions (when the counterparty, notes or amount fit, set the category, add a
tag or split it). After saving, the rule's past matches are shown and applied only when asked, with one undo."""
from __future__ import annotations

from fastapi import APIRouter, Request

from lightning.categories.domain import Movement
from lightning.core.errors import LightningError, ValidationError
from lightning.core.plural import counted
from lightning.rules.service import MAX_PARTS

from ..web import container, redirect, render, settled_save

router = APIRouter(prefix="/rules")

FIELDS = ("name", "match", "counterparty_op", "counterparty", "notes", "amount_op", "amount", "amount_to", "account_id",  # not money: field names
          "direction", "category_id", "tag") + tuple(f"part_{k}_{i}" for i in range(1, MAX_PARTS + 1)  # not money: field names
                                                    for k in ("category", "value"))
PAST_SHOWN = 20


def _form(request: Request, c, values: dict, rule=None, error: str = "", error_field: str = "", status_code: int = 200):
    pickable = [cat for cat in c.categories.pickable() if not cat.is_system]
    return render(request, "rules/form.html", status_code=status_code, values=values, rule=rule,
                  categories=[cat.id for cat in pickable],
                  spending=[cat.id for cat in pickable if cat.movement == Movement.OUTFLOW],
                  accounts=c.accounts.list(active_only=True), counterparties=c.counterparties.list_active(),
                  rule_parts=range(1, MAX_PARTS + 1),  # not money: form slots
                  error=error, error_field=error_field)


@router.get("")
async def rules_page(request: Request):
    c = container(request)
    token = str(request.query_params.get("undo", ""))
    rows = [{"rule": rule, **c.rules.describe(rule)} for rule in c.rules.list()]
    return render(request, "rules/index.html", rows=rows, undo=token if c.rules.can_undo(token) else "")


@router.get("/new")
async def new_rule(request: Request):
    c = container(request)
    values = c.rules.form_values()
    for key in FIELDS:
        values[key] = str(request.query_params.get(key, "") or values[key])
    return _form(request, c, values)


@router.post("")
async def create_rule(request: Request):
    c = container(request)
    form = await request.form()
    values = {k: str(form.get(k, "")).strip() for k in FIELDS}
    try:
        with settled_save(request, container(request)):
            rule_id = c.rules.save(values)
    except LightningError as exc:
        return _form(request, c, values, error=exc.message, error_field=exc.field or "", status_code=400)
    return redirect(f"/rules/{rule_id}/past", "Rule saved. It files your next imports and entries.")


@router.get("/{rule_id:int}/edit")
async def edit_rule(request: Request, rule_id: int):
    c = container(request)
    rule = c.rules.get(rule_id)
    return _form(request, c, c.rules.form_values(rule), rule=rule)


@router.post("/{rule_id:int}/edit")
async def update_rule(request: Request, rule_id: int):
    c = container(request)
    rule = c.rules.get(rule_id)
    form = await request.form()
    values = {k: str(form.get(k, "")).strip() for k in FIELDS}
    try:
        with settled_save(request, container(request)):
            c.rules.save(values, rule_id)
    except LightningError as exc:
        return _form(request, c, values, rule=rule, error=exc.message, error_field=exc.field or "", status_code=400)
    return redirect(f"/rules/{rule_id}/past", "Rule saved.")


@router.post("/{rule_id:int}/delete")
async def delete_rule(request: Request, rule_id: int):
    c = container(request)
    with settled_save(request, container(request)):
        c.rules.delete(rule_id)
    return redirect("/rules", "Rule deleted. Transactions it filed keep their category.")


def _safe_back(value) -> str:
    value = str(value or "")
    return value if value.startswith("/") and not value.startswith("//") else "/transactions"


@router.get("/offer")
async def offer_rule(request: Request):
    """After the same counterparty was filed the same way twice: offer a rule with its past rows (NF-3AZ3)."""
    c = container(request)
    back = _safe_back(request.query_params.get("return_to"))
    name = str(request.query_params.get("counterparty", ""))
    category = str(request.query_params.get("category_id", ""))
    offer = c.rules.suggestion(name, int(category) if category.isdigit() else None)
    if offer is None:
        return redirect(back, "")
    return render(request, "rules/offer.html", offer=offer, changes=offer["past"][:PAST_SHOWN],
                  more=max(len(offer["past"]) - PAST_SHOWN, 0), back=back)  # not money: counts


@router.post("/offer")
async def accept_offer(request: Request):
    c = container(request)
    form = await request.form()
    back = _safe_back(form.get("return_to"))
    name, category = str(form.get("counterparty", "")), str(form.get("category_id", ""))
    if form.get("decision") == "no":
        with settled_save(request, c):
            c.rules.clear_corrections(name)
        return redirect(back, "No rule made. Lightning will ask again only after two more corrections.")
    try:
        if not category.isdigit():
            raise ValidationError("Choose a category.")
        offer = c.rules.suggestion(name, int(category))
        if offer is None or offer["token"] != str(form.get("token", "")):
            raise ValidationError("The offer changed. Review it again before saving the rule.")
        count, token = 0, ""
        with settled_save(request, c, undo_label="Save rule from repeated correction"):
            rule_id = c.rules.save({"counterparty_op": "is", "counterparty": name, "category_id": category})
            c.rules.clear_corrections(name)
            if form.get("scope") == "past" and offer["past"]:
                count, token = c.rules.apply_past(rule_id, [change.id for change in offer["past"]],
                                                  c.rules.past_token(rule_id))
    except LightningError as exc:
        return redirect(back, exc.message)
    if token:
        return redirect(f"/rules?undo={token}", f"Rule saved and {counted(count, 'past transaction', 'past transactions')} refiled.")
    return redirect(back, "Rule saved. It files your next imports and entries.")


@router.get("/{rule_id:int}/past")
async def past_matches(request: Request, rule_id: int):
    c = container(request)
    rule = c.rules.get(rule_id)
    changes = c.rules.past(rule_id)
    if not changes:
        return redirect("/rules", request.query_params.get("msg", "") or "Rule saved.")
    return render(request, "rules/past.html", rule=rule, words=c.rules.describe(rule), changes=changes[:PAST_SHOWN],
                  total=len(changes), more=max(len(changes) - PAST_SHOWN, 0), fingerprint=c.rules.past_token(rule_id, changes))  # not money: counts


@router.post("/{rule_id:int}/apply")
async def apply_to_past(request: Request, rule_id: int):
    c = container(request)
    form = await request.form()
    selected = form.getlist("transaction_id")
    if not selected:
        return redirect(f"/rules/{rule_id}/past", "No selected transactions to change.")
    try:
        if len(selected) > 1000 or any(not str(value).isdigit() for value in selected):
            raise ValueError
        with settled_save(request, container(request)):
            count, token = c.rules.apply_past(rule_id, {int(value) for value in selected}, str(form.get("fingerprint", "")))
    except (LightningError, ValueError) as exc:
        return redirect(f"/rules/{rule_id}/past", getattr(exc, "message", "Choose valid transactions."))
    if not count:
        return redirect("/rules", "Nothing in the past to change.")
    return redirect(f"/rules?undo={token}", f"{counted(count, 'past transaction', 'past transactions')} refiled.")


@router.post("/undo")
async def undo_apply(request: Request):
    c = container(request)
    form = await request.form()
    try:
        with settled_save(request, container(request)):
            count = c.rules.undo(str(form.get("token", "")))
    except LightningError as exc:
        return redirect("/rules", exc.message)
    return redirect("/rules", f"Undone: {counted(count, 'transaction', 'transactions')} back as they were.")
