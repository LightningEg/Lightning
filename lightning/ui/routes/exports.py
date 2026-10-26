"""Download only the records explicitly selected in a list."""

from __future__ import annotations

import csv
from io import StringIO

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from lightning.core.errors import LightningError
from ..web import container, render

router = APIRouter(prefix="/exports")


@router.get("/all")
async def all_data(request: Request):
    from lightning.workflows.data_export import export_all
    chosen = request.query_params.get("format")
    if not chosen:
        return render(request, "exports/all.html", chosen="xlsx")
    try:
        data, filename, media = export_all(container(request), chosen)
    except ValueError as exc:
        return render(request, "exports/all.html", chosen=chosen, error=str(exc), status_code=400)
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"',
                                                  "Cache-Control": "no-store"})


def _selected(form, field: str) -> set[int]:
    values = form.getlist(field)
    if not values or len(values) > 1000 or any(not str(value).isdigit() or int(value) < 1 for value in values):
        raise HTTPException(400, "Select between 1 and 1,000 records to export.")
    return {int(value) for value in values}


def _safe_text(value) -> str:
    value = str(value or "")
    # CSV quoting does not prevent spreadsheet formulas from executing.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value


def _csv(filename: str, headings: tuple[str, ...], rows: list[tuple]) -> Response:
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(headings)
    writer.writerows(rows)
    return Response("\ufeff" + buffer.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "Cache-Control": "no-store"})


@router.post("/transactions")
async def transactions(request: Request):
    c = container(request)
    ids = _selected(await request.form(), "txn_ids")
    rows = []
    for txn_id in sorted(ids):
        txn = c.transactions.get(txn_id)
        for line in sorted(txn.lines, key=lambda item: item.line_no):
            account = c.accounts.get(line.account_id)
            asset = c.assets.get_asset(line.asset_id)
            rows.append((txn.id, txn.ref, txn.date, txn.type.value, txn.status.value, txn.source.value,
                         _safe_text(txn.counterparty), _safe_text(txn.description), _safe_text(txn.notes),
                         line.line_no, account.id, _safe_text(account.name), account.currency,
                         asset.id, _safe_text(asset.name), _safe_text(asset.code),
                         line.category_id or "", _safe_text(c.categories.display_name(line.category_id)) if line.category_id else "",
                         line.effect.value, str(line.quantity), str(line.unit_price), str(line.amount),
                         str(line.fx_rate), str(line.amount_base), c.base_currency,
                         _safe_text(line.memo), line.owner_id or ""))
    return _csv("lightning-transactions.csv", ("transaction_id", "reference", "date", "type", "status", "source",
                "counterparty", "description", "notes", "line_no", "account_id", "account", "account_currency",
                "asset_id", "asset", "asset_code", "category_id", "category", "effect", "quantity",
                "unit_price", "amount", "fx_rate", "amount_base", "base_currency", "line_memo", "owner_id"), rows)


@router.post("/categories")
async def categories(request: Request):
    c = container(request)
    ids = _selected(await request.form(), "category_ids")
    rows = []
    recurring = c.budgets.recurring_income_ids()
    one_offs = c.budgets.one_off_ids(with_children=False)
    for category_id in sorted(ids):
        cat = c.categories.get(category_id)
        parent = c.categories.get(cat.parent_id) if cat.parent_id else None
        rows.append((cat.id, _safe_text(cat.code), _safe_text(cat.name), cat.parent_id or "",
                     _safe_text(parent.name) if parent else "", cat.depth, cat.direction.value,
                     cat.movement.value, cat.scope.value if cat.scope else "",
                     cat.income_class.value if cat.income_class else "",
                     cat.family.value if cat.family else "", "yes" if cat.active else "no",
                     "yes" if cat.is_system else "no", "yes" if cat.default_reimbursable else "no",
                     "yes" if cat.id in recurring else "no", "yes" if cat.id in one_offs else "no"))
    return _csv("lightning-categories.csv", ("category_id", "code", "name", "parent_id", "parent",
                "level", "direction", "movement", "scope", "income_class", "family", "active",
                "system", "default_reimbursable", "recurring_income", "one_off"), rows)


@router.post("/reevaluations")
async def reevaluations(request: Request):
    c = container(request)
    ids = _selected(await request.form(), "entry_ids")
    selected = c.reevaluations.history(limit=len(ids), entry_ids=ids)
    if len(selected) != len(ids):
        raise HTTPException(400, "One or more selected reevaluations no longer exist. Refresh the page and select again.")
    rows = [(row["id"], row["date"], row["reason"], row["status"], row["account_id"],
             _safe_text(row["account_name"]), row["asset_id"], _safe_text(row["asset_name"]),
             row["owner_id"] or "", _safe_text(row["owner_name"]),
             *(str(row[key]) if row[key] is not None else "" for key in
               ("units_e6", "price_e6", "value_base_e6", "return_base_e6")),
             row["currency"], c.base_currency, _safe_text(row["price_source"]), "yes" if row["needs_price"] else "no",
             row["journal_transaction_id"] or "", _safe_text(row["ref"])) for row in selected]
    return _csv("lightning-reevaluations.csv", ("entry_id", "date", "reason", "status", "account_id",
                "account", "asset_id", "asset", "owner_id", "held_for", "units", "price", "value_base",
                "return_base", "currency", "base_currency", "price_source", "needs_price", "journal_transaction_id",
                "journal_reference"), rows)


@router.get("/views/{view_id:int}")
async def saved_view(request: Request, view_id: int):
    c = container(request)
    try:
        raw_scope = request.query_params.get("account_id", "").strip()
        if raw_scope and (not raw_scope.isdigit() or int(raw_scope) < 1):
            raise ValueError("Choose a valid account.")
        scope = c.accounts.get(int(raw_scope)).id if raw_scope else None
        view = c.saved_views.get(view_id, scope)
        report = c.saved_views.report(view)
    except LightningError as exc:
        return Response(exc.message, status_code=404, media_type="text/plain")
    except ValueError as exc:
        return Response(str(exc), status_code=400, media_type="text/plain")
    rows = [(row.date, row.ref, row.type, _safe_text(row.account_label),
             _safe_text(row.counterparty or row.description), _safe_text(row.category_label),
             _safe_text(row.notes), str(row.amount), row.currency, str(row.amount_base))
            for row in report["rows"]]
    return _csv(f"lightning-view-{view_id}.csv",
                ("date", "reference", "type", "account", "counterparty", "category", "notes",
                 "amount", "currency", "amount_base"), rows)


@router.get('/import')
async def import_workbook_page(request: Request):
    from lightning.workflows.workbook_import import SETUP_PROMPT
    return render(request, 'exports/import.html', setup_prompt=SETUP_PROMPT)


@router.get('/import/template')
async def import_workbook_template(request: Request):
    from lightning.workflows.data_export import export_all
    from lightning.workflows.workbook_import import _unused
    c = container(request)
    try:
        _unused(c)
        data, _, media = export_all(c, 'xlsx')
    except ValueError:
        return Response('Download the template from a new, empty profile.', status_code=400, media_type='text/plain')
    return Response(data, media_type=media, headers={'Content-Disposition': 'attachment; filename="lightning-onboarding-template.xlsx"', 'Cache-Control': 'no-store'})


@router.post('/import')
async def preview_workbook_import(request: Request):
    import base64
    import hashlib
    import secrets
    import time
    from lightning.workflows.workbook_import import MAX_UPLOAD, SETUP_PROMPT, prepare_import, confirm_import
    c = container(request)
    try:
        form = await request.form(max_part_size=MAX_UPLOAD * 2)
        action = form.get('action', 'preview')
        pending = getattr(request.app.state, 'workbook_import_tokens', {})
        pending = {key: value for key, value in pending.items() if value[1] > time.monotonic()}
        request.app.state.workbook_import_tokens = pending
        if action == 'confirm':
            try:
                data = base64.b64decode(str(form.get('payload', '')), validate=True)
            except ValueError:
                raise ValueError('The preview expired. Upload the workbook again.') from None
            token = str(form.get('token', ''))
            saved = pending.pop(token, None)
            if not saved or saved[0] != hashlib.sha256(data).hexdigest() or saved[2] != id(c.db):
                raise ValueError('The preview expired or the file changed. Upload the workbook again.')
            count = confirm_import(c, data)
            return render(request, 'exports/import.html', setup_prompt=SETUP_PROMPT, imported=count)
        upload = form.get('workbook')
        if upload is None or not hasattr(upload, 'read'):
            raise ValueError('Choose an Excel .xlsx workbook.')
        data = await upload.read(MAX_UPLOAD + 1)
        tables = prepare_import(c, data)
        if len(pending) >= 8:
            pending.pop(next(iter(pending)))
        token = secrets.token_urlsafe(32)
        pending[token] = (hashlib.sha256(data).hexdigest(), time.monotonic() + 900, id(c.db))
        return render(request, 'exports/import.html', setup_prompt=SETUP_PROMPT,
                      preview=[(name, len(rows)) for name, (_, rows) in tables.items()],
                      token=token, payload=base64.b64encode(data).decode('ascii'))
    except ValueError as exc:
        return render(request, 'exports/import.html', setup_prompt=SETUP_PROMPT, error=str(exc), status_code=400)
