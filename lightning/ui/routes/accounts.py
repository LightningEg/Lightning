from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from lightning.accounts.domain import DEFAULT_CASH_CLASS, OFFERED_TYPES, SIDEBAR_GROUPS, TYPE_LABELS
from lightning.core.dates import fmt_date, parse_date, today
from lightning.core.errors import LightningError, ValidationError
from lightning.core.figures import label
from lightning.core.money import ZERO, fmt, to_decimal

from . import register
from .. import charts, kpis, status as page_status
from ..entry import entry_accounts
from ..i18n import translate
from ..periods import parse_period
from ..web import settled_save, container, redirect, render, ui_locale

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


def _phone_groups(groups, base: str) -> list[dict]:
    """The phone's Accounts tab (phone overhaul 2026-10-22): the active accounts under each sidebar group, the group's
    total beside its name, and under each account its type, its bank and, for foreign money, its currency."""
    out = []
    for name, group in groups:
        shown = []
        for account, balance, _owned, _count in group["rows"]:
            if not account.active:
                continue
            kind = account.type_short if account.type_short.casefold() not in account.name.casefold() else ""
            extra = [text for text in (account.institution.strip() if account.institution else "",
                                       account.currency if account.currency != base else "")
                     if text and text.casefold() not in account.name.casefold()]
            shown.append({"id": account.id, "name": account.name, "balance": balance, "kind": kind,
                          "extra": " · ".join(extra)})
        if shown:
            out.append({"name": name, "total": group["balance"], "rows": shown})
    return out


def _hero_line(count: int, held, own, circle=ZERO) -> dict:
    """The one sentence under In your accounts: what part of it is held for others, what a circle still takes from
    it (BV-3AQ: the rows add up to In your accounts, the circle below zero), and so what you own."""
    if not count:
        return page_status.sentence("Add an account to see where your money is.")
    if circle > ZERO and own is not None:
        if held > ZERO:
            return page_status.sentence("Includes {amt} held for others and {owed} you still owe a circle, so you own {own}.",
                                        amt=fmt(held, 0), owed=fmt(circle, 0), own=fmt(own, 0))
        return page_status.sentence("Includes {owed} you still owe a circle, so you own {own}.",
                                    owed=fmt(circle, 0), own=fmt(own, 0))
    if held > ZERO and own is not None:
        return page_status.sentence("Includes {amt} held for others, so you own {own}.", amt=fmt(held, 0), own=fmt(own, 0))
    if held > ZERO:
        return page_status.sentence("{n} accounts. {amt} of it is held for others.", n=count, amt=fmt(held, 0))
    return page_status.sentence("{n} accounts, and all of it is yours.", n=count)


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
    # Answer first (guideline 3.33): What you own is the Lead, In your accounts and Held for others beside it; the
    # accounts follow in the groups the sidebar uses, each with its total.
    held = c.reporting.money_from_others_total(fmt_date(today()))
    circle = c.position.at(today()).gameya_still_to_pay
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
    groups = sorted(groups.items(), key=lambda item: order.index(item[0]))
    return render(request, "accounts/list.html", rows=rows, net_worth=net_worth, gross_total=gross_total,
                  lead=lead, held_total=held, circle_owed=circle, groups=groups,
                  status=page_status.accounts(len(active), held),
                  phone_groups=_phone_groups(groups, c.base_currency),
                  hero_line=_hero_line(len(active), held, None if net_worth.unvalued or gross_total is None
                                       else net_worth.what_you_own, circle))


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
    combined_trend = None
    combined_unavailable = False
    if chosen:
        points = [point for point in chosen.series]
        trend = charts.trend([point.day[:7] for point in points], [
            {"name": "Value of what you hold", "tone": "hold", "values": [point.value for point in points]},
            {"name": "What it cost", "tone": "other", "dashed": True, "values": [point.cost for point in points]}])
        values = []
        for point in points:
            invested, unpriced = c.position.foreign_holdings(point.day, c.base_currency).get(
                chosen.currency, (ZERO, False))
            values.append(None if unpriced or point.value is None else point.value + invested)
        # Never bridge an unknown valuation with a line that suggests a known history.
        combined_unavailable = any(value is None for value in values)
        combined_trend = charts.trend([point.day[:7] for point in points], [
            {"name": translate("Cash and investments", ui_locale()), "tone": "hold", "values": values}])
        if not combined_trend["too_short"]:
            series = combined_trend["series"][0]
            dots, run, lines = iter(series["dots"]), [], []
            for value in values:
                if value is None:
                    if len(run) > 1:
                        lines.append(" ".join(run))
                    run = []
                else:
                    dot = next(dots)
                    run.append(f"{dot['x']:.2f},{dot['y']:.2f}")
            if len(run) > 1:
                lines.append(" ".join(run))
            series["lines"] = lines
    totals = c.reporting.fx_positions.totals(positions)
    return render(request, "accounts/currencies.html", positions=shown, other=other, chosen=chosen, trend=trend,
                  totals=totals, period=period, period_error=period_error,
                  answer=page_status.currencies(len(positions), totals["value"], totals["unrealized"], totals["complete"]),
                  fx_kpis=kpis.currencies(totals, start=period.start_text, end=period.end_text),
                  combined_trend=combined_trend, combined_unavailable=combined_unavailable)


CONVERT_FIELDS = ("date", "from_account_id", "to_account_id", "sent", "received", "fee", "notes")


def convert_context(request: Request, values: dict, action: str, title: str, error: LightningError | None = None):
    """The Convert form (accounts of two currencies, amounts both ways, an optional fee)."""
    c = container(request)
    choices = [a for a in c.accounts.list(active_only=True) if a.account_type.value in ("CASH", "BANK", "BROKERAGE")]
    return dict(values=values, action=action, title=title, accounts=choices, back=values.get("return_to", "/accounts"),
                error=error.message if error else "", error_field=(error.field or "") if error else "")


def convert_values(form) -> dict:
    return {key: str(form.get(key, "")).strip() for key in CONVERT_FIELDS} | {
        "rate_checked": str(form.get("rate_checked", "")).strip()}


FAR_FROM_MARKET = Decimal("20")  # percent; past it a typo (the two amounts swapped) is likelier than a bank's spread


def check_conversion_rate(c, values: dict) -> None:
    """Ask once before saving a rate far from the day's market rate (5J): saved, its rate values every holding in
    that currency. The second press, with the same rate, saves it as typed."""
    quote = c.transactions.conversion_quote(values["date"] or fmt_date(today()),
                                            _account_id(values["from_account_id"], "from_account"),
                                            _account_id(values["to_account_id"], "to_account"),
                                            values["sent"], values["received"])
    if not quote or "percent" not in quote or Decimal(quote["percent"]) < FAR_FROM_MARKET:
        return
    if values.get("rate_checked") == quote["rate"]:
        return
    values["rate_checked"] = quote["rate"]
    rate = f"1 {quote['base']} = {fmt(Decimal(quote['rate']), 4)} {quote['quote']}"
    market = f"{fmt(Decimal(quote['reference']), 4)} {quote['quote']} on {quote['reference_date']}"
    template = ("{rate} is {percent}% above the market rate ({market}). Check the two amounts are not swapped, then "
                "press Convert again to save it." if quote["direction"] == "above" else
                "{rate} is {percent}% below the market rate ({market}). Check the two amounts are not swapped, then "
                "press Convert again to save it.")
    raise ValidationError(template.format(rate=rate, percent=quote["percent"], market=market), "received")


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
    submission = None if getattr(c, "is_journal", False) else str(form.get("submission", ""))
    payload = {key: value for key, value in values.items() if key not in ("return_to", "rate_checked")}
    try:
        with register.resent_guard(c, form), settled_save(request, c):
            txn = c.transactions.submitted(submission, payload)  # a resent form returns its first save
            if txn is None:
                check_conversion_rate(c, values)
                txn = c.transactions.record_conversion(
                    values["date"], _account_id(values["from_account_id"], "from_account"),
                    _account_id(values["to_account_id"], "to_account"), values["sent"], values["received"],
                    values["fee"] or None, notes=values["notes"])
                c.transactions.remember_submission(submission, payload, txn.id)
    except LightningError as exc:
        return render(request, "accounts/convert.html", status_code=400,
                      **convert_context(request, values, f"/accounts/{account_id}/convert", "Convert money", exc))
    return redirect(values["return_to"], f"Saved {txn.ref}.")


def _account_id(text: str, field: str) -> int:
    if not text.isdigit():
        raise ValidationError("Choose an account.", field)
    return int(text)


LAST_ACCOUNT_COOKIE = "lightning_last_account"  # the account the last entry went to (phone roadmap M2)




@router.get("/add-transaction")
async def pick_account_for_entry(request: Request):
    """The phone's Add button (guideline C05.2): the sheet opens on the amount with an account already chosen, the one
    used last, else the one this person uses most (3AN3). No list of accounts first; the sheet's From chip changes it.
    ?pick=1, or no account yet, is the phone router's account list (3AY18); here the PC goes to Accounts."""
    c = container(request)
    accounts = entry_accounts(c)
    if not request.query_params.get("pick") and accounts:
        remembered = str(request.cookies.get(LAST_ACCOUNT_COOKIE, ""))
        ids = [a.id for a in accounts]
        if remembered.isdigit() and int(remembered) in ids:
            chosen = int(remembered)
        else:
            cashy = [a.id for a in accounts if a.account_type.value in ("CASH", "BANK") and not a.parent_id]
            chosen = c.transactions.usual_account(cashy or ids)
        return await new_transaction_popup(request, chosen)
    return redirect("/accounts")


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
        with settled_save(request, container(request)):
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
        with settled_save(request, container(request)):
            c.accounts.save_other_asset_value(account, str(form.get("date") or today()),
                                           str(form.get("value") or ""), str(form.get("notes") or ""))
    except LightningError as exc:
        return redirect(f"/accounts/{account_id}", exc.message)
    return redirect(f"/accounts/{account_id}", "Dated estimated value saved.")


@router.post("/{account_id:int}/details")
async def update_other_asset_details(request: Request, account_id: int):
    c = container(request)
    account = c.accounts.get(account_id)
    form = await request.form()
    try:
        with settled_save(request, container(request)):
            c.accounts.save_other_asset_details(account, str(form.get("kind") or "other"),
                                                str(form.get("purchase_date") or ""), str(form.get("purchase_price") or ""),
                                                str(form.get("loan_item_id") or ""))
    except LightningError as exc:
        return redirect(f"/accounts/{account_id}", exc.message)
    return redirect(f"/accounts/{account_id}", "Details saved.")


def _transaction_popup_context(request, account, values, action, error=None, txn_id=None, split_categories=None):
    c = container(request)
    counterparties = c.counterparties.list_active()
    return dict(account=account, values=values, action=action, txn_id=txn_id, hide_global_error=True,
                title="Edit transaction" if txn_id else "Add transaction",
                revision=values.get("revision", c.transactions.revision(txn_id)) if txn_id else "",
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
    asked = request.query_params
    kind = str(asked.get("kind", ""))
    amount = str(asked.get("amount", "")).strip()[:20]
    day = str(asked.get("date", ""))
    values = {"kind": kind if kind in ("out", "in", "transfer") else "out",
              "date": day if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) else fmt_date(today()),
              "amount": amount if re.fullmatch(r"[\d,.]*", amount) else "",
              "category_id": _category_id(request), "counterparty": str(asked.get("counterparty", ""))[:80],
              # HO-1: Held for others' Give back and Spend for them open this sheet with the person chosen
              "owner_id": str(asked.get("owner_id", "")) if str(asked.get("owner_id", "")).isdigit() else "",
              "to_account_id": "", "notes": str(asked.get("notes", ""))[:200],
              "sms_fp": str(asked.get("sms_fp", "")) if re.fullmatch(r"[0-9a-f]{32}", str(asked.get("sms_fp", ""))) else "",
              "sms_ending": str(asked.get("sms_ending", "")) if re.fullmatch(r"\d{4}|salary", str(asked.get("sms_ending", ""))) else "",
              "return_to": _safe_return(asked.get("return_to"), f"/accounts/{account_id}")}
    return render(request, "transactions/form_popup.html",
                  **_transaction_popup_context(request, account, values, f"/accounts/{account_id}/transaction/new"))


def _save_popup_transaction(c, account_id: int, values: dict):
    kind = values["kind"]
    if kind not in {"out", "in", "transfer"}:
        raise ValidationError("Choose Money out, Money in, or Transfer.", "kind")
    day = fmt_date(parse_date(values["date"], "date"))
    amount = to_decimal(values["amount"], "amount")
    if amount <= 0:
        raise ValidationError("Enter an amount greater than zero.", "amount")
    register.check_before_opening(c, account_id, day, values)
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
        unsorted = not category_id
        if unsorted:
            # NF-7AN: save now, sort later. With only an amount the entry waits as To sort (filed Unaccounted, a
            # system category that is spending or income with no category yet); Home's To do and the phone's To
            # sort list ask for it.
            category_id = c.categories.get_by_code("EXP.UNACCOUNTED" if kind == "out" else "INC.UNACCOUNTED").id
        category = c.categories.get(category_id)
        if kind == "out" and category.movement.value != "OUTFLOW":  # money in to an expense is a refund
            raise ValidationError("Choose a category that matches this transaction type.", "category")
        counterparty = _popup_counterparty(c, values["counterparty"])
        if counterparty and any(a.name.casefold() == counterparty.casefold()
                                for a in c.accounts.list(active_only=True)):
            raise ValidationError("Choose Transfer and select the destination account explicitly.", "counterparty")
        if kind == "out":
            txn = c.transactions.record_outflow(day, account_id, amount, category_id,
                                               counterparty=counterparty, notes=values["notes"], owner_id=owner_id,
                                               allow_system_category=unsorted)
        else:
            txn = c.transactions.record_inflow(day, account_id, amount, category_id,
                                              counterparty=counterparty, notes=values["notes"], owner_id=owner_id,
                                              allow_system_category=unsorted)
    return txn


@router.post("/quick-add")
async def quick_add(request: Request):
    """One tap from the phone's Quick Add (backend roadmap B5): saves one entry and answers in
    JSON. The account is the form's, else the last one used; `submission` makes a double tap or a resend return
    the first save instead of a second entry."""
    c = container(request)
    form = await request.form()
    raw = str(form.get("account_id", "") or request.cookies.get(LAST_ACCOUNT_COOKIE, ""))
    if not raw.isdigit():
        return JSONResponse({"ok": False, "error": "Choose an account."}, 422)
    account_id = int(raw)
    values = {key: str(form.get(key, "")) for key in
              ("kind", "date", "amount", "category_id", "counterparty", "owner_id", "to_account_id", "notes")}
    values["kind"] = values["kind"] or "out"
    values["date"] = values["date"] or fmt_date(today())
    values["early_checked"] = values["date"]  # Quick Add has no second press: a date before opening is kept as typed (2E)
    submission = None if getattr(c, "is_journal", False) else str(form.get("submission", ""))
    payload = values | {"account": account_id}
    try:
        account = c.accounts.require_usable(account_id)
        with register.resent_guard(c, form), settled_save(request, c):
            earlier = c.transactions.submitted(submission, payload)
            txn = earlier or _save_popup_transaction(c, account_id, values)
            if earlier is None:
                c.transactions.remember_submission(submission, payload, txn.id)
                c.reserves.auto_link_transaction(txn.id)
    except (LightningError, ValueError) as exc:
        message = exc.message if isinstance(exc, LightningError) else "Choose valid values for this transaction."
        return JSONResponse({"ok": False, "error": message}, 422)
    response = JSONResponse({"ok": True, "id": txn.id, "ref": txn.ref, "account_id": account_id,
                             "repeat": earlier is not None})
    response.set_cookie(LAST_ACCOUNT_COOKIE, str(int(account.id)), max_age=365 * 24 * 3600, httponly=True, samesite="lax")
    return response


def _remember_sms(c, form, account_id: int) -> None:
    """A sheet filled from a pasted bank SMS (3AN5): when its card ending was not known, the account the person saved it
    to is the answer, remembered once; the message is marked read so the phone's inbox does not offer it again."""
    ending, fingerprint = str(form.get("sms_ending", "")), str(form.get("sms_fp", ""))
    if ending:
        try:
            c.sms_imports.assign(ending, account_id)
        except LightningError:
            pass  # not an EGP account: the entry is saved all the same; the ending is asked again next time
    if fingerprint:
        c.sms_imports.mark_seen(fingerprint)


@router.post("/{account_id:int}/transaction/new")
async def save_transaction_popup(request: Request, account_id: int):
    c = container(request)
    account = c.accounts.require_usable(account_id)
    form = await request.form()
    values = {key: str(form.get(key, "")) for key in
              ("kind", "date", "amount", "category_id", "counterparty", "owner_id", "to_account_id", "notes", "early_checked")}
    values["return_to"] = _safe_return(form.get("return_to"), f"/accounts/{account_id}")
    submission = None if getattr(c, "is_journal", False) else str(form.get("submission", ""))
    payload = {key: value for key, value in values.items() if key != "return_to"} | {"account": account_id}
    try:
        with register.resent_guard(c, form), settled_save(request, c):
            earlier = c.transactions.submitted(submission, payload)  # a resent form returns its first save (2J)
            txn = earlier or _save_popup_transaction(c, account_id, values)
            if earlier is None:
                c.transactions.remember_submission(submission, payload, txn.id)
                matched_reserve = c.reserves.auto_link_transaction(txn.id)
                _remember_sms(c, form, account_id)
        if earlier is not None:
            return redirect(values["return_to"], "Saved.")
        feedback = register._budget_feedback(c, txn)
        if matched_reserve < 0:
            feedback = (feedback + " Several reserves match; choose beside the transaction in its account list.").strip()
        response = redirect(values["return_to"], f"Saved. {feedback}".strip())
        response.set_cookie(LAST_ACCOUNT_COOKIE, str(int(account.id)), max_age=365 * 24 * 3600,  # the stored id
                            httponly=True, samesite="lax")
        return response
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


def _save_ownership(c, account, values):
    """One ownership change (an expense someone else paid, or cash assigned between people): its transaction."""
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
    return txn


@router.post("/{account_id:int}/ownership/new")
async def save_ownership_change(request: Request, account_id: int):
    c = container(request)
    account = c.accounts.require_usable(account_id)
    form = await request.form()
    values = {key: str(form.get(key, "")).strip() for key in
              ("mode", "date", "amount", "from_owner_id", "to_owner_id", "category_id", "notes")}
    action = f"/accounts/{account_id}/ownership/new"
    submission = None if getattr(c, "is_journal", False) else str(form.get("submission", ""))
    payload = values | {"account": account_id}
    try:
        with settled_save(request, c):
            txn = c.transactions.submitted(submission, payload)  # a resent form returns its first save (2AD)
            if txn is None:
                txn = _save_ownership(c, account, values)
                c.transactions.remember_submission(submission, payload, txn.id)
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
        with settled_save(request, container(request)):
            c.reconciliation.close(account_id, str(form.get("date", "")), str(form.get("balance", "")))
    except LightningError as exc:
        return redirect(f"/accounts/{account_id}/reconcile", exc.message)
    back = str(form.get("return_to", ""))   # the account page's "Yes, it matches" comes back to it
    if back != f"/accounts/{account_id}":
        back = f"/accounts/{account_id}/reconcile"
    return redirect(back, "Checked history is now protected. Unlock it before making corrections.")


@router.post("/{account_id:int}/reconcile/unlock")
async def unlock_checked_history(request: Request, account_id: int):
    with settled_save(request, container(request)):
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
        with settled_save(request, container(request)):
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
    feedback = register._budget_feedback(container(request), txn)
    return redirect(f"/accounts/{account_id}?date={txn.date}", f"Saved. {feedback}".strip())


@router.post("/{account_id:int}/register")
async def register_entry(request: Request, account_id: int):
    """Save one row typed into the register, then come back ready for the next one."""
    result = await register.create(request, account_id)
    if not isinstance(result, tuple):
        return result  # the page again, with the error
    txn, _ = result
    feedback = register._budget_feedback(container(request), txn)
    return redirect(f"/accounts/{account_id}?date={txn.date}", f"Saved. {feedback}".strip())


@router.post("/{account_id:int}/register/{txn_id:int}")
async def register_update(request: Request, account_id: int, txn_id: int):
    result = await register.update(request, account_id, txn_id)
    if not isinstance(result, tuple):
        return result
    txn, values = result
    message = f"Saved as {txn.ref}. The original transaction is kept in history." if txn.id != txn_id else "Saved."
    message = f"{message} {register._budget_feedback(container(request), txn)} {values.get('_notice', '')}".strip()
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
        with settled_save(request, container(request)):
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
        with settled_save(request, container(request)):
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
        with settled_save(request, container(request)):
            pocket = c.accounts.add_pocket(account_id, str(form.get("currency", "")))
    except LightningError as exc:
        return redirect(f"/accounts/{account_id}", exc.message)
    return redirect(f"/accounts/{account_id}", f"{c.accounts.get(account_id).name} now holds {pocket.currency}.")


BROKER_KINDS = {"buy": "Bought", "sell": "Sold", "convert": "Converted", "dividend": "Dividend", "interest": "Interest",
                "fee": "Fee", "deposit": "Money in", "withdrawal": "Money out"}
BROKER_STATUS = {"new": "To record", "imported": "Already imported", "listed": "Not recorded here",
                 "posted": "Recorded", "problem": "Not recorded"}


def _broker_import_page(request: Request, account_id: int, **values):
    c = container(request)
    return render(request, "broker_import.html", account=c.accounts.get(account_id), kinds=BROKER_KINDS,
                  statuses=BROKER_STATUS, **{"result": None, "posted": False, "error": "", **values})


@router.get("/{account_id:int}/broker-import")
async def broker_import_page(request: Request, account_id: int):
    """NF-5G5: import an Interactive Brokers activity statement into this broker."""
    return _broker_import_page(request, account_id)


@router.post("/{account_id:int}/broker-import")
async def broker_import(request: Request, account_id: int):
    """Preview a statement, or record it once confirmed (the statement travels in the form, so nothing is staged)."""
    import base64
    from lightning.investments.broker_import import BrokerImport, read_ibkr
    c = container(request)
    form = await request.form()
    upload = form.get("file")
    try:
        if upload is not None and hasattr(upload, "read"):
            data = await upload.read()
        else:
            data = base64.b64decode(str(form.get("statement", "")), validate=True)
        if len(data) > 5 * 1024 * 1024:
            raise ValidationError("Statements up to 5 MB are supported.", "file")
        statement = read_ibkr(data)
        work = BrokerImport(c)
        if not form.get("confirm"):
            preview = work.preview(account_id, statement)
            return _broker_import_page(request, account_id, result=preview, new_instruments=preview.new_instruments,
                                       statement_b64=base64.b64encode(data).decode("ascii"))
        with settled_save(request, c):
            done = work.post(account_id, statement)
        positions = work.check_positions(account_id, statement)
    except (LightningError, ValueError) as exc:
        return _broker_import_page(request, account_id, error=getattr(exc, "message", "That file could not be read."),
                                   status_code=400)
    return _broker_import_page(request, account_id, result=done, posted=True, positions=positions,
                               period_end=statement.period_end)


@router.post("/{account_id:int}/make-pocket")
async def make_pocket(request: Request, account_id: int):
    """Move a separate foreign-currency brokerage into a broker as its pocket in that currency (5G3)."""
    c = container(request)
    form = await request.form()
    try:
        with settled_save(request, container(request)):
            pocket = c.accounts.make_pocket(account_id, int(str(form.get("broker_id", "0")) or 0))
    except (LightningError, ValueError) as exc:
        return redirect(f"/accounts/{account_id}", getattr(exc, "message", "Choose a broker."))
    broker = c.accounts.get(pocket.parent_id)
    return redirect(f"/accounts/{pocket.id}", f"{broker.name} now holds your {pocket.currency} account as a pocket.")


@router.post("/{account_id:int}/spendable")
async def set_spendable(request: Request, account_id: int):
    """Count this account's cash as spendable or keep it apart (Free cash, Safe to spend, payday)."""
    c = container(request)
    form = await request.form()
    choice = {"yes": True, "no": False}.get(str(form.get("spendable", "")))
    account = c.accounts.get(account_id)
    if choice is not None and choice == replace(account, spendable=None).counts_as_spendable(c.base_currency):
        choice = None  # the default: store no override
    with settled_save(request, container(request)):
        account = c.accounts.set_spendable(account_id, choice)
    spendable = account.counts_as_spendable(c.base_currency)
    return redirect(f"/accounts/{account.id}",
                    "Its cash now counts as spendable." if spendable else "Its cash is now kept apart from spendable cash.")


@router.post("/{account_id:int}/cost-method")
async def set_cost_method(request: Request, account_id: int):
    """Choose average cost or oldest first for the sales of a brokerage account (NF-5B3)."""
    c = container(request)
    form = await request.form()
    try:
        with settled_save(request, c):
            account = c.accounts.set_cost_method(account_id, str(form.get("method", "")))
    except LightningError as exc:
        return redirect(f"/accounts/{account_id}", exc.message)
    return redirect(f"/accounts/{account.id}", "Sales now use the oldest purchase first." if account.cost_method == "fifo"
                    else "Sales now use the average cost.")


@router.post("/{account_id:int}/reactivate")
async def reactivate(request: Request, account_id: int):
    with settled_save(request, container(request)):
        account = container(request).account_flows.reactivate(account_id)
    return redirect(f"/accounts/{account.id}", f"{account.label} is active again.")

