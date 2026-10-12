"""Settings › Rules: rules with conditions (when the counterparty, notes or amount fit, set the category, add a
tag or split it). After saving, the rule's past matches are shown and applied only when asked, with one undo."""
from __future__ import annotations

from fastapi import APIRouter, Request

from lightning.categories.domain import Movement
from lightning.core.errors import LightningError
from lightning.rules.engine import TEXT_OPS
from lightning.rules.service import MAX_PARTS

from ..web import container, redirect, render

router = APIRouter(prefix="/rules")

FIELDS = ("match", "counterparty_op", "counterparty", "notes", "amount_op", "amount", "amount_to", "account_id",
          "direction", "category_id", "tag") + tuple(f"part_{k}_{i}" for i in range(1, MAX_PARTS + 1)
                                                    for k in ("category", "value"))
PAST_SHOWN = 20


def _form(request: Request, c, values: dict, rule=None, error: str = "", error_field: str = "", status_code: int = 200):
    pickable = [cat for cat in c.categories.pickable() if not cat.is_system]
    return render(request, "rules/form.html", status_code=status_code, values=values, rule=rule,
                  categories=[cat.id for cat in pickable],
                  spending=[cat.id for cat in pickable if cat.movement == Movement.OUTFLOW],
                  accounts=c.accounts.list(active_only=True), counterparties=c.counterparties.list_active(),
                  parts=range(1, MAX_PARTS + 1),
                  error=error, error_field=error_field)


@router.get("")
async def rules_page(request: Request):
    c = container(request)
    token = str(request.query_params.get("undo", ""))
    rows = [{"rule": rule, **c.rules.describe(rule)} for rule in c.rules.list()]
    return render(request, "rules/index.html", rows=rows, undo=token if c.rules.can_undo(token) else "",
                  suggestions=c.rules.suggestions())


@router.get("/new")
async def new_rule(request: Request):
    c = container(request)
    values = c.rules.form_values()
    for key in ("counterparty", "category_id"):
        values[key] = str(request.query_params.get(key, "") or values[key])
    if request.query_params.get("counterparty_op") in TEXT_OPS:  # a suggestion names the counterparty exactly
        values["counterparty_op"] = request.query_params["counterparty_op"]
    return _form(request, c, values)


@router.post("/suggestions/dismiss")
async def dismiss_suggestion(request: Request):
    c = container(request)
    form = await request.form()
    c.rules.dismiss_suggestion(str(form.get("name", "")))
    return redirect("/rules", "Suggestion dismissed. It will not come back.")


@router.post("")
async def create_rule(request: Request):
    c = container(request)
    form = await request.form()
    values = {k: str(form.get(k, "")).strip() for k in FIELDS}
    try:
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
        c.rules.save(values, rule_id)
    except LightningError as exc:
        return _form(request, c, values, rule=rule, error=exc.message, error_field=exc.field or "", status_code=400)
    return redirect(f"/rules/{rule_id}/past", "Rule saved.")


@router.post("/{rule_id:int}/delete")
async def delete_rule(request: Request, rule_id: int):
    c = container(request)
    c.rules.delete(rule_id)
    return redirect("/rules", "Rule deleted. Transactions it filed keep their category.")


@router.get("/{rule_id:int}/past")
async def past_matches(request: Request, rule_id: int):
    c = container(request)
    rule = c.rules.get(rule_id)
    changes = c.rules.past(rule_id)
    if not changes:
        return redirect("/rules", request.query_params.get("msg", "") or "Rule saved.")
    return render(request, "rules/past.html", rule=rule, words=c.rules.describe(rule), changes=changes[:PAST_SHOWN],
                  total=len(changes), more=max(len(changes) - PAST_SHOWN, 0))


@router.post("/{rule_id:int}/apply")
async def apply_to_past(request: Request, rule_id: int):
    c = container(request)
    count, token = c.rules.apply_past(rule_id)
    if not count:
        return redirect("/rules", "Nothing in the past to change.")
    return redirect(f"/rules?undo={token}", f"{count} past transaction{'s' if count != 1 else ''} refiled.")


@router.post("/undo")
async def undo_apply(request: Request):
    c = container(request)
    form = await request.form()
    try:
        count = c.rules.undo(str(form.get("token", "")))
    except LightningError as exc:
        return redirect("/rules", exc.message)
    return redirect("/rules", f"Undone: {count} transaction{'s' if count != 1 else ''} back as they were.")
