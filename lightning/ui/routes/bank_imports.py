from __future__ import annotations

import base64
import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from decimal import Decimal, InvalidOperation

from lightning.core.dates import today
from lightning.workflows.market_prices import fill_followed
from lightning.bank_imports import OPTIONAL, REQUIRED, SEPARATE_AMOUNT_FIELDS, decode_csv
from lightning.core.errors import LightningError, ValidationError
from lightning.core.limits import MAX_CSV_MAPPING_REQUEST_BYTES, MAX_IMPORT_REVIEW_REQUEST_BYTES
from lightning.core.money import ZERO, fmt
from lightning.sync.journal.proxy import PendingOnHome
from lightning.workflows.ai_prompts import bank_category_prompt, rejected_csv_prompt

from ..web import container, redirect, render, settled_save

router = APIRouter(prefix="/accounts")

# Journal proposals have a 64 KiB signed-message ceiling and carry CSV bytes as
# base64. Keep the decoded attachment below the command protocol's 40 KiB cap.
MAX_JOURNAL_CSV_COMMAND_BYTES = 40 * 1024


def _budget_import_feedback(c, batch_id: int) -> str:
    _, rows = c.bank_imports.preview(batch_id)
    by_month: dict[str, set[int]] = {}
    for row in rows:
        if row.get("_status") != "POSTED" or not row.get("_transaction_id"):
            continue
        txn = c.transactions.get(int(row["_transaction_id"]))
        for line in txn.lines:
            if line.category_id and line.effect.value == "OUTFLOW":
                by_month.setdefault(txn.date[:7], set()).add(line.category_id)
    impacts = []
    for month, category_ids in by_month.items():
        view = c.budgets.month_view(month, schedule=c.schedules.view())
        budget_lines = {line.category_id: line for section in view.sections for line in section.lines}
        for category_id in category_ids:
            line = budget_lines.get(category_id)
            if line:
                shown = line
                if shown.remaining is None and shown.covered:
                    parent = c.categories.get(category_id).parent_id
                    while parent:
                        ancestor = budget_lines.get(parent)
                        if ancestor and ancestor.remaining is not None:
                            shown = ancestor
                            break
                        parent = c.categories.get(parent).parent_id
                status = (f"{fmt(shown.remaining)} {c.base_currency} left" if shown.remaining is not None
                          else ("inside a group limit" if line.covered else "unplanned"))
                impacts.append(f"{line.name} ({status})")
    return f" Budget · {', '.join(impacts[:3])}." if impacts else ""

def _categories(c):
    return [{"id": cat.id, "name": cat.name,
             "group": c.categories.get(cat.parent_id).name if cat.parent_id else "Other",
             "label": c.categories.display_name(cat.id)} for cat in c.categories.pickable()]


def _ai_reference(c):
    return {"counterparties": [party["name"] for party in c.counterparties.list_active()],
            "categories": _categories(c)}


def _ai_prompt(account, reference):
    cats = "\n".join(f"- {item['label']} (id: {item['id']})" for item in reference["categories"])
    parties = "\n".join(f"- {name}" for name in reference["counterparties"])
    return f'''Prepare an account statement CSV for review and import into Lightning.
Account: {account.name}
Currency: {account.currency}

Return a standard UTF-8 CSV file with a header row, using exactly this canonical schema: Date,Amount,Counterparty,Category,Notes,Reference. Date and Amount are required; the remaining columns are optional and may be blank. Date must use YYYY-MM-DD. If the source only has separate inflow/outflow columns, the importer also accepts Date,Inflow,Outflow instead of Amount; each row must have a value in exactly one of those amount columns, with no Amount column.

Quote CSV fields when needed to preserve commas, quotes, or line breaks. Preserve the source dates and amount values in meaning; do not change currency, round, or infer missing values. Express direction as the account's perspective: money into the account is positive and money out is negative. For separate columns, place nonnegative values in Inflow or Outflow respectively. Keep optional values only when present in the source. Reference is an optional source transaction identifier. Do not add unsupported columns.

Match Category only to the exact pickable category labels below. Match Counterparty only when the source supports a confident match to one of the existing active names below; do not invent matches or create names. Leave unknown or ambiguous categories blank (and leave unknown counterparties unchanged or blank if absent). Do not use category IDs as CSV values.

Existing active counterparties:\n{parties or '- (none)'}

Pickable categories:\n{cats or '- (none)'}

Statements from Egyptian banks and wallets often use Arabic-Indic digits (٠١٢٣٤٥٦٧٨٩) and day-first dates: write digits as 0-9 and dates as YYYY-MM-DD. If a date could be read two ways (05/06/2026), ask me which order the source uses before converting. Keep Arabic names as written. Opening and closing balances, running balances and totals are not transactions: leave them out and tell me which rows you left out. If the source holds more than one account or currency, ask me which one this file is for.

Return only the CSV, then list every row you were unsure about so I can check it in Lightning's review. Review every output row against the source before confirming the import. Do not claim the import is complete.'''


def _first_import_prompt(c, account):
    """On the first import into an account: map the bank's own category words to the person's categories."""
    if c.bank_imports.has_posted_import(account.id):
        return ""
    return bank_category_prompt(account.institution or account.name, account.currency,
                                [item["label"] for item in _categories(c)])


def _rejected_prompt(account, headers, problems, failing=0):
    """A statement that did not read: its header, what failed on which line, and the schema. No values from any row."""
    return rejected_csv_prompt(account.name, account.currency, headers, problems, failing)


def _review_form_max_fields(row_count: int) -> int:
    # Each row submits about twelve fields (date, counterparty and its pick, category, held for and its pick,
    # notes, amount, skip, match, remember); leave room for form metadata.
    return max(1_000, row_count * 12 + 100)


@router.get("/{account_id:int}/import")
async def import_page(request: Request, account_id: int):
    c = container(request)
    return _render_upload(request, c, account_id)


def _waiting_imports(c, account_id: int) -> list[dict]:
    return c.bank_imports.waiting(account_id)


def _render_upload(request, c, account_id, *, error="", status_code=200):
    from lightning.workflows.ai_prompts import pdf_to_csv_prompt
    account = c.accounts.get(account_id)
    return render(request, "bank_import_upload.html", account=account, waiting=_waiting_imports(c, account_id),
                  pdf_prompt=pdf_to_csv_prompt(account.currency), ai_prompt=_ai_prompt(account, _ai_reference(c)), category_prompt=_first_import_prompt(c, account),
                  error=error, status_code=status_code)


@router.get("/{account_id:int}/import/ai-reference.json")
async def ai_reference(request: Request, account_id: int):
    c = container(request)
    account = c.accounts.get(account_id)
    return JSONResponse({"account": account.name, "currency": account.currency, **_ai_reference(c)},
                        headers={"Content-Disposition": 'attachment; filename="lightning-import-reference.json"',
                                 "Cache-Control": "no-store"})


@router.get("/{account_id:int}/import/ai-template.csv")
async def ai_template(request: Request, account_id: int):
    container(request).accounts.get(account_id)
    return PlainTextResponse("Date,Amount,Counterparty,Category,Notes,Reference\r\n",
                             media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="lightning-import-template.csv"'})


def _lightning_columns(headers: list[str]) -> bool:
    """The file uses Lightning's own column names, so its columns need no matching."""
    return "Date" in headers and "Amount" in headers and set(headers) <= {*REQUIRED, *OPTIONAL}


@router.post("/{account_id:int}/import")
async def upload(request: Request, account_id: int):
    c = container(request)
    form = await request.form()
    upload_files = [item for item in form.getlist("file") if getattr(item, "filename", "")]
    if not upload_files:
        return _render_upload(request, c, account_id, error="Choose at least one statement file.", status_code=400)
    try:
        prepared = []
        needs_mapping = None
        for upload_file in upload_files:
            from lightning.statement_files import MAX_FILE_BYTES, read_statement
            data = await upload_file.read(MAX_FILE_BYTES + 1)
            data = read_statement(upload_file.filename, data, c.accounts.get(account_id).currency)
            if getattr(c, "is_journal", False) and len(data) > MAX_JOURNAL_CSV_COMMAND_BYTES:
                return _render_upload(request, c, account_id,
                                      error="This file is too large to synchronize; split it into smaller files.",
                                      status_code=400)
            headers, sample_rows = decode_csv(data)
            mapping = c.bank_imports.suggested_mapping(account_id, headers, sample_rows)
            saved_mapping = c.bank_imports.saved_mapping(account_id, headers)
            if not saved_mapping and _lightning_columns(headers):
                saved_mapping = {"amount_model": "SINGLE"} | {key: key for key in headers}
            if not saved_mapping:
                needs_mapping = needs_mapping or (headers, mapping)
                if headers != needs_mapping[0]:
                    return _render_upload(request, c, account_id,
                                          error="Group files with the same columns together, or match each file separately.",
                                          status_code=400)
                saved_mapping = None
            prepared.append((upload_file.filename, data, saved_mapping, mapping, headers))
        if needs_mapping:
            if any(item[4] != needs_mapping[0] for item in prepared):
                return _render_upload(request, c, account_id,
                                      error="Group files with the same columns together, or match each file separately.",
                                      status_code=400)
            bundle = [{"filename": name, "payload": base64.b64encode(data).decode("ascii")}
                      for name, data, _, _, _ in prepared]
            total_bytes = sum(len(item["payload"]) for item in bundle)
            if total_bytes > MAX_CSV_MAPPING_REQUEST_BYTES:
                return _render_upload(request, c, account_id,
                                      error="These files are too large to map together. Choose fewer files, or match them one at a time.",
                                      status_code=413)
            headers, mapping = needs_mapping
            first = bundle[0]
            return render(request, "bank_import_map.html", account=c.accounts.get(account_id), headers=headers,
                          payload=first["payload"], filename=first["filename"], bundle=bundle,
                          required=REQUIRED, optional=OPTIONAL, amount_fields=SEPARATE_AMOUNT_FIELDS,
                          suggested_amount_model=mapping.get("amount_model", "SINGLE"), mapping=mapping,
                          invert_amount=mapping.get("amount_sign") == "invert")
        batches = []
        waiting = None
        for filename, data, saved_mapping, _, _ in prepared:
            mapping = saved_mapping
            try:
                with settled_save(request, container(request)):
                    batch_id, repeated = c.bank_imports.stage(account_id, filename, data, mapping,
                                                               invert_amount=mapping.get("amount_sign") == "invert")
            except PendingOnHome as pending:
                waiting = pending
                continue
            batches.append((batch_id, repeated))
        if waiting is not None:
            raise waiting
        batch_id, repeated = batches[0]
        message = ("Imported files are ready for review." if len(batches) > 1 else "")
        if repeated and len(batches) == 1:
            message = "This exact file was already imported."
        return redirect(f"/accounts/{account_id}/import/{batch_id}", message)
    except LightningError as exc:
        return _render_upload(request, c, account_id, error=exc.message, status_code=400)


@router.post("/{account_id:int}/import/map")
async def map_columns(request: Request, account_id: int):
    c = container(request)
    form = await request.form(max_files=0, max_fields=2_000,
                              max_part_size=MAX_CSV_MAPPING_REQUEST_BYTES)
    headers = []
    data = b""
    mapping = {}
    bundle = []
    filename = str(form.get("filename", "statement.csv"))
    try:
        data = base64.b64decode(str(form.get("payload", "")), validate=True)
        headers, _ = decode_csv(data)
        amount_model = str(form.get("amount_model", "SINGLE"))
        mapping = {"amount_model": amount_model}
        selected_amount_fields = REQUIRED if amount_model == "SINGLE" else ("Date", *SEPARATE_AMOUNT_FIELDS)
        mapping.update({key: str(form.get(f"map_{key}", "")) for key in (*selected_amount_fields, *OPTIONAL)})
        mapping = {key: value for key, value in mapping.items() if value}
        bundle = json.loads(str(form.get("bundle") or "[]"))
        if not bundle:
            bundle = [{"filename": filename, "payload": str(form.get("payload", ""))}]
        batches = []
        waiting = None
        for item in bundle:
            file_data = base64.b64decode(item["payload"], validate=True)
            file_headers, _ = decode_csv(file_data)
            if file_headers != headers:
                raise ValidationError("All selected files must use the same columns.", "mapping")
            try:
                with settled_save(request, container(request)):
                    batch_id, repeated = c.bank_imports.stage(account_id, str(item["filename"]), file_data, mapping,
                                                               invert_amount=form.get("amount_sign") == "invert")
            except PendingOnHome as pending:
                waiting = pending
                continue
            batches.append((batch_id, repeated))
        if waiting is not None:
            raise waiting
    except (ValueError, LightningError) as exc:
        if isinstance(exc, ValidationError) and exc.field == "mapping":
            return render(request, "bank_import_map.html", account=c.accounts.get(account_id), headers=headers,
                          payload=base64.b64encode(data).decode("ascii"), filename=filename,
                          bundle=bundle,
                          required=REQUIRED, optional=OPTIONAL, amount_fields=SEPARATE_AMOUNT_FIELDS,
                          suggested_amount_model=mapping.get("amount_model", "SINGLE"), mapping=mapping,
                          invert_amount=form.get("amount_sign") == "invert", error=exc.message, status_code=400,
                          reject_prompt=_rejected_prompt(c.accounts.get(account_id), headers, [("1", exc.message)]))
        msg = exc.message if isinstance(exc, LightningError) else "The uploaded statement could not be read. Upload it again."
        return _render_upload(request, c, account_id, error=msg, status_code=400)
    batch_id, repeated = batches[0]
    message = "Files are ready for review." if len(batches) > 1 else "This exact file was already imported." if repeated else ""
    return redirect(f"/accounts/{account_id}/import/{batch_id}", message)


def _amount(row) -> Decimal:
    try:
        return Decimal(str(row.get("Amount", "")).replace(",", "").replace("−", "-"))
    except (InvalidOperation, ValueError):
        return ZERO


def _row_status(row: dict) -> str:
    """The row's own state, worst first: to fix, needs you, possible duplicate, ready."""
    if row.get("_row_error") or row.get("_errors"):
        return "err"
    if row.get("_possible_duplicate"):
        return "dup"
    return "ready" if row.get("_ready") else "needs"


_STATUS_ORDER = {"err": 0, "needs": 1, "dup": 2, "ready": 3}


def _row_ui(row: dict, form=None) -> dict:
    """What each well of a row shows: the user's own choices after a failed post, else the suggestions."""
    rid = row["_import_row_id"]
    if form is not None and f"counterparty_{rid}" in form:
        own = lambda name, default="": str(form.get(f"{name}_{rid}", default))
        return {"cp": own("counterparty"), "cp_pick": own("counterparty_pick"), "cat": own("category"),
                "whom": own("whom"), "whom_pick": own("whom_pick"),
                "remember": form.get(f"remember_{rid}") == "on", "skip": form.get(f"skip_{rid}") == "on",
                "match": own("match"), "fee": own("fee"), "conversion_amount": own("conversion_amount")}
    cp_pick = (f"account:{row['_transfer_account_id']}" if row.get("_transfer_account_id")
               else f"counterparty:{row['_counterparty_id']}" if row.get("_counterparty_id") else "")
    if row.get("_identity_ambiguous"):
        cp_pick = ""
    custody = row.get("_is_custody") and row.get("_whom") and row.get("_counterparty_id")
    return {"cp": row.get("Counterparty") or "", "cp_pick": cp_pick,
            "cat": str(row.get("_category_id") or "") if not row.get("_transfer_account_id") else "",
            "whom": row["_whom"] if custody else "",
            "whom_pick": f"counterparty:{row['_counterparty_id']}" if custody else "",
            "remember": bool(row.get("_remember_category")), "skip": bool(row.get("_skip") or row.get("_balance_row")),
            "match": str(row.get("_match") or row.get("_default_match") or ""), "fee": "", "conversion_amount": ""}


def _suggestions_json(c, row: dict, account_ids: dict[str, int], party_ids: dict[str, int]) -> str:
    """The row's suggested counterparty spellings and transfer account, shown first in its picker."""
    picks = []
    target = row.get("_transfer_target_suggestion")
    if target and target in account_ids and not row.get("_transfer_account_id"):
        picks.append({"v": target, "p": f"account:{account_ids[target]}"})
    for name, _score in row.get("_suggestions") or []:
        if name in party_ids:
            picks.append({"v": name, "p": f"counterparty:{party_ids[name]}"})
    return json.dumps(picks, ensure_ascii=False) if picks else ""


def _review_groups(c, rows: list[dict], form=None) -> list[dict]:
    """Rows grouped by imported name (a header with its total and state, the rows under it). Every row keeps its
    own counterparty, category, held-for, notes and amount; a group is only a place to fold and to tick."""
    all_accounts = c.accounts.list(active_only=True)
    accounts = {a.name: a.id for a in all_accounts if sum(b.name == a.name for b in all_accounts) == 1}
    parties = {p["name"]: p["id"] for p in c.counterparties.list_active()}
    by_key: dict[str, list[dict]] = {}
    for row in rows:
        key = " ".join(str(row.get("Counterparty") or "").casefold().split())
        by_key.setdefault(key or f"__line_{row['_line']}", []).append(row)
    groups = []
    for index, (key, members) in enumerate(by_key.items()):
        for row in members:
            row["_ui"] = _row_ui(row, form)
            row["_state"] = _row_status(row)
            row["_suggest"] = _suggestions_json(c, row, accounts, parties)
        status = min((r["_state"] for r in members), key=_STATUS_ORDER.get)
        groups.append({
            "i": index, "key": key, "rows": members, "count": len(members), "status": status,
            "name": members[0].get("Counterparty") or "No counterparty",
            "total": sum((_amount(r) for r in members), ZERO),
            "errors": sum(1 for r in members if r["_state"] == "err"),
            "duplicates": sum(1 for r in members if r["_state"] == "dup"),
        })
    return sorted(groups, key=lambda g: (_STATUS_ORDER[g["status"]], int(g["rows"][0]["_line"])))


def _render_review(request, c, account_id: int, batch, rows, *, summary, form=None, msg="", error="", status_code=200):
    account = c.accounts.get(account_id)
    groups = _review_groups(c, rows, form)
    counts = {"all": len(groups)} | {key: sum(1 for g in groups if g["status"] == key) for key in _STATUS_ORDER}
    accounts_here = [a for a in c.accounts.list(active_only=True) if a.id != account_id and (a.currency == account.currency or a.account_type.value in ("BANK", "CASH", "BROKERAGE"))]
    failing = [r for r in rows if _row_status(r) == "err"]
    reject_prompt = ""
    if failing and batch["status"] != "POSTED":
        reject_prompt = _rejected_prompt(
            account, c.bank_imports.source_header(batch["id"]),
            [(str(r["_line"]), str(r.get("_row_error") or " ".join(r.get("_errors") or []))) for r in failing], len(failing))
    labels: dict[str, int] = {}
    for row in rows:
        if row.get("_status") == "REVIEW" and row.get("_file_label"):
            labels[row["_file_label"]] = labels.get(row["_file_label"], 0) + 1
    file_labels = sorted(labels.items(), key=lambda item: (-item[1], item[0].casefold()))
    return render(request, "bank_import_preview.html", account=account, batch=batch, rows=rows,
                  groups=groups, counts=counts, categories=_categories(c), file_labels=file_labels,
                  counterparties=c.counterparties.list_active(), owners=c.counterparties.list_people(), account_choices=accounts_here,
                  summary=summary, msg=msg, error=error, reject_prompt=reject_prompt, status_code=status_code)


@router.post("/{account_id:int}/import/counterparty")
async def create_counterparty_now(request: Request, account_id: int):
    """"+ New counterparty" on the review page saves the name at once, so every other row's list offers it and the
    rows that carry the same statement name take it, instead of waiting for "Post ready rows". A name that already
    matches a saved counterparty is used, never doubled. In "Held for" the name is a person."""
    c = container(request)
    form = await request.form()
    name = " ".join(str(form.get("name", "")).split())
    try:
        if not name:
            raise ValidationError("Enter a counterparty name.", "counterparty")
        with settled_save(request, container(request)):
            if str(form.get("kind", "")).upper() == "PERSON":
                party_id = c.counterparties.ensure_person(name)
            else:
                found = c.counterparties.resolve(name)
                party_id = int(found["id"]) if found else c.counterparties.create(name)
        party = c.counterparties.get(party_id)
        if not party["active"]:
            raise ValidationError(f"{party['name']} is archived. Turn it on in Counterparties first.", "counterparty")
    except LightningError as exc:
        return JSONResponse({"error": exc.message}, status_code=400)
    return JSONResponse({"id": party_id, "name": party["name"], "pick": f"counterparty:{party_id}"})


@router.get("/{account_id:int}/import/{batch_id:int}")
async def preview(request: Request, account_id: int, batch_id: int):
    c = container(request)
    batch, rows = c.bank_imports.preview(batch_id)
    if batch["account_id"] != account_id:
        return redirect(f"/accounts/{account_id}", "Import batch not found for this account.")
    return _render_review(request, c, account_id, batch, rows, summary=c.bank_imports.summary(batch_id))


@router.post("/{account_id:int}/import/{batch_id:int}/discard")
async def discard(request: Request, account_id: int, batch_id: int):
    c = container(request)
    batch, _ = c.bank_imports.preview(batch_id)
    if batch["account_id"] != account_id:
        return redirect(f"/accounts/{account_id}", "Import batch not found for this account.")
    try:
        with settled_save(request, container(request)):
            count = c.bank_imports.discard(batch_id)
    except LightningError as exc:
        return redirect(f"/accounts/{account_id}/import/{batch_id}", exc.message)
    if str(batch["file_name"]).startswith("SMS "):  # messages read from bank SMS go back to From SMS (IV-3AU)
        return redirect("/sms", "Discarded: nothing from these messages was posted.")
    return redirect(f"/accounts/{account_id}",
                    f"Import discarded: {count} row{'s' if count != 1 else ''} from {batch['file_name']} were not posted.")


def _decision(form, row) -> dict:
    """One row's decision, from that row's own wells: counterparty (text, and what it was picked as), category,
    held for (text and pick), notes, amount, skip, the duplicate choice, and remember. Older posts that send
    counterparty_choice_<row>, owner_choice_<row> or transfer_account_id_<row> keep working."""
    row_id = row["_import_row_id"]
    own = lambda name, default="": str(form.get(f"{name}_{row_id}", default))
    category_choice = own("category")
    typed = own("counterparty", row["Counterparty"])
    decision = {"category_id": category_choice if category_choice and category_choice != "__uncategorized__" else None,
                "force_uncategorized": category_choice == "__uncategorized__",
                "skip": form.get(f"skip_{row_id}") == "on",
                "match": own("match"),
                "date": form.get(f"date_{row_id}", row["Date"]),
                "counterparty": typed,
                "alias_text": row["Counterparty"],
                "amount": form.get(f"amount_{row_id}", row["Amount"]),
                "notes": form.get(f"notes_{row_id}", row["Notes"]),
                "whom": own("whom"),
                "owner_choice": own("owner_choice"),
                "counterparty_choice": own("counterparty_choice"),
                "remember_category": (form.get(f"remember_{row_id}") or form.get(f"remember_category_{row_id}")) == "on",
                "transfer_account_id": own("transfer_account_id"),
                "fee": own("fee"), "conversion_amount": own("conversion_amount")}
    pick = own("counterparty_pick")
    if pick.startswith("account:"):          # one of your accounts: a transfer to or from it
        decision["transfer_account_id"] = pick.split(":", 1)[1]
        decision["counterparty_choice"] = "unlinked"
    elif pick.startswith("counterparty:"):   # a saved counterparty
        decision["counterparty_choice"] = "existing:" + pick.split(":", 1)[1]
    elif pick.startswith("new:"):            # made on posting, once for the batch, with the statement's text as alias
        decision["counterparty_choice"] = "new"
        decision["new_counterparty"] = pick[4:]
    elif not decision["counterparty_choice"]:  # typed and not picked: kept as written, unlinked
        decision["counterparty_choice"] = "typed"
    selected = decision["counterparty_choice"]
    if selected.startswith("existing:"):
        decision["counterparty_id"] = int(selected.split(":", 1)[1])
    elif selected == "new" and "new_counterparty" not in decision:
        decision["new_counterparty"] = typed
    whom_pick = own("whom_pick")
    if whom_pick == "self" or decision["whom"].strip().casefold() in {"you", "self"}:
        decision["owner_choice"], decision["whom"] = "self", ""
    elif whom_pick.startswith("counterparty:"):
        decision["owner_choice"] = "existing:" + whom_pick.split(":", 1)[1]
    elif whom_pick.startswith("new:"):
        decision["owner_choice"] = "new:" + whom_pick[4:]
    return decision


def _keep_typed(form, rows) -> None:
    """After a failed post, show each row with what the user typed."""
    for row in rows:
        decision = _decision(form, row)
        row["Date"], row["Amount"], row["Notes"] = str(decision["date"]), str(decision["amount"]), str(decision["notes"])
        row["Counterparty"] = str(row["Counterparty"])
        row["_skip"] = decision["skip"]
        row["_match"] = decision["match"]


def _ready_decision(form, row, decision, account_names) -> bool:
    """Only submit resolved review rows; the service also supports explicit fallback imports."""
    if row["_status"] != "REVIEW":
        return False
    match = decision["match"]
    if decision["skip"] or match == "skip" or match.startswith("link:"):
        return True
    if row.get("_possible_duplicate") and match != "new":
        return False
    if row.get("_identity_ambiguous") and not decision.get("transfer_account_id") and not (
            decision.get("counterparty_id") or decision.get("counterparty_choice", "").startswith("existing:")
            or decision.get("counterparty_choice") == "new"):
        return False
    category_key = f"category_{row['_import_row_id']}"
    if decision["category_id"] or decision["force_uncategorized"]:
        return True
    if category_key not in form and row.get("_category_id"):
        return True
    if decision["transfer_account_id"] or decision["counterparty"].strip().casefold() in account_names:
        return True
    owner = str(decision["owner_choice"])
    whom = str(decision["whom"]).strip().casefold()
    held_for = owner.startswith(("existing:", "new:")) or (not owner and whom and whom not in
                                                             {"you", "self", "me", "my money", "my own money"})
    return bool(held_for and _amount({"Amount": decision["amount"]}) > ZERO)


@router.post("/{account_id:int}/import/{batch_id:int}/confirm")
async def confirm(request: Request, account_id: int, batch_id: int):
    c = container(request)
    batch, rows = c.bank_imports.preview(batch_id)
    if batch["account_id"] != account_id:
        return redirect(f"/accounts/{account_id}", "Import batch not found for this account.")
    # Starlette defaults to 1,000 form fields. The review has several editable
    # controls per imported row, so size the parser budget to this staged batch.
    form = await request.form(max_fields=_review_form_max_fields(len(rows)),
                              max_part_size=MAX_IMPORT_REVIEW_REQUEST_BYTES)
    account_names = {a.name.casefold() for a in c.accounts.list(active_only=True) if a.id != account_id}
    decisions = {}
    for row in rows:
        decision = _decision(form, row)
        if _ready_decision(form, row, decision, account_names):
            decisions[row["_import_row_id"]] = decision
    try:
        with settled_save(request, c):
            count = c.bank_imports.confirm(batch_id, decisions)
    except LightningError as exc:
        batch, rows = c.bank_imports.preview(batch_id)
        _keep_typed(form, rows)
        return _render_review(request, c, account_id, batch, rows, summary=c.bank_imports.summary(batch_id),
                              form=form, error=exc.message, status_code=400)
    if count.get("errors"):
        batch, review_rows = c.bank_imports.preview(batch_id)
        _keep_typed(form, review_rows)
        for row in review_rows:
            row["_row_error"] = count["errors"].get(int(row["_import_row_id"]))
        problems = len(count["errors"])
        msg = (f"Nothing was imported yet: {problems} row{'s' if problems != 1 else ''} need{'' if problems != 1 else 's'} "
               "attention. Fix them below; your other choices are kept.")
        return _render_review(request, c, account_id, batch, review_rows, summary=c.bank_imports.summary(batch_id),
                              form=form, msg=msg)
    feedback = _budget_import_feedback(c, batch_id)
    if count.get("posted") and c.accounts.get(account_id).account_type.value == "BROKERAGE":
        # A brokerage statement brings holdings: give each the month-end prices it needs from the price files.
        try:
            report = fill_followed(c, today())
        except LightningError:
            report = None
        if report is not None and (report.added or report.missing):
            feedback += f" {report.summary()}"
    if count.get("ambiguous_reserves"):
        feedback += f" {count['ambiguous_reserves']} row(s) could match multiple reserves; choose beside each transaction in its account list."
    batch, result_rows = c.bank_imports.preview(batch_id)
    remaining = sum(row["_status"] == "REVIEW" for row in result_rows)
    if remaining:
        _keep_typed(form, result_rows)
    settled = c.planning.settled_bill_names({row["_transaction_id"] for row in result_rows
                                           if row.get("_transaction_id")})
    if settled:
        feedback += " Settled bills: " + ", ".join(settled) + "."
    return _render_review(request, c, account_id, batch, result_rows, summary=count, form=form if remaining else None,
                          msg=f"Import {'updated' if remaining else 'complete'}: {count['posted']} posted, "
                              + (f"{count['linked']} linked to entries you already had, " if count.get("linked") else "")
                              + f"{count['skipped']} skipped, {count['duplicates']} duplicates."
                              + (" Some rows still need review." if remaining else "") + feedback)
