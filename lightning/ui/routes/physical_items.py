from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Request, Response

from lightning.accounts.domain import AccountType
from lightning.core.dates import fmt_date, today
from lightning.core.errors import LightningError
from lightning.core.money import ZERO, from_e6, to_decimal

from ..web import container, redirect, render

router = APIRouter()


def _int(value):
    text = str(value or "").strip()
    return int(text) if text.isdigit() else None


def _references(c, account, karat=None):
    if karat not in (None, ""):
        try:
            karat = int(karat)
        except (TypeError, ValueError):
            return []
    rows = [asset for asset in c.assets.investments(active_only=True)
            if asset.exposure.value == "GOLD" and asset.currency == account.currency and asset.purity is not None
            and (karat is None or asset.purity == Decimal(karat) / Decimal(24))]
    seen, unique = set(), []
    for asset in rows:
        key = (asset.purity, asset.currency, asset.unit, asset.name.casefold())
        if key not in seen:
            seen.add(key)
            unique.append(asset)
    return unique


def account_page(request: Request, account_id: int):
    c = container(request)
    account = c.accounts.get(account_id)
    if account.account_type != AccountType.PHYSICAL_ASSET:
        return redirect(f"/accounts/{account_id}")
    day = fmt_date(today())
    portfolio = c.investments.portfolio(day, account_id)
    by_asset = {position.asset_id: position for position in portfolio.open}
    items = []
    for item in c.physical_items.for_account(account_id):
        position = by_asset.get(item["asset_id"])
        item.update(position=position, held=position.quantity if position else ZERO,
                    gold_weight=Decimal(item["net_gold_grams_e6"]) / Decimal(1_000_000),
                    value=position.value if position else ZERO,
                    fine_gold=(Decimal(item["net_gold_grams_e6"]) / Decimal(1_000_000)
                               * Decimal(item["karat"]) / Decimal(24)
                               * (position.quantity if position else ZERO)),
                    history=c.physical_items.valuations(item["asset_id"]))
        items.append(item)
    item_ids = {item["asset_id"] for item in items}
    other_holdings = [position for position in portfolio.open if position.asset_id not in item_ids]
    total = c.reporting.account_value(account_id, today())
    owned = c.reporting.owned_account_value(account_id, today())
    rows = c.reporting.register(account_id, "1900-01-01", "9999-12-31")
    trade_details = {row["transaction_id"]: row | {
        "workmanship_cost": from_e6(row["workmanship_cost_e6"])}
        for row in c.physical_items.trade_details_for_account(account_id)}
    return render(request, "physical_account.html", account=account, items=items,
                  other_holdings=other_holdings, total=total, owned=owned, held=total-owned,
                  account_asset_breakdown=c.reporting.account_asset_class_breakdown(account_id, today()),
                  rows=rows, trade_details=trade_details, counterparties=c.counterparties.list_active(),
                  references=_references(c, account), cash_accounts=c.accounts.list(active_only=True))


@router.get("/accounts/{account_id:int}/items/new")
async def new_item(request: Request, account_id: int):
    c = container(request)
    account = c.accounts.get(account_id)
    return render(request, "physical_item_form.html", account=account, item=None,
                  references=_references(c, account), values={"name": "", "kind": "Jewelry", "weight": "",
                                                              "karat": "18", "reference_asset_id": "",
                                                              "details": "", "worn": ""})


@router.post("/accounts/{account_id:int}/items/new")
async def create_item(request: Request, account_id: int):
    c = container(request)
    account = c.accounts.get(account_id)
    form = await request.form()
    values = {key: str(form.get(key, "")) for key in ("name", "kind", "weight", "karat", "reference_asset_id", "details")}
    values["worn"] = "1" if form.get("worn") == "1" else ""
    try:
        c.physical_items.create(account_id, values["name"], values["kind"], values["weight"],
                                           int(values["karat"]), int(values["reference_asset_id"]), values["details"],
                                           worn=values["worn"] == "1")
    except (ValueError, LightningError) as exc:
        error = exc if isinstance(exc, LightningError) else LightningError("Choose a matching gold price reference.")
        return render(request, "physical_item_form.html", status_code=400, account=account, item=None,
                      references=_references(c, account), values=values,
                      error=error.message, error_field=error.field or "")
    return redirect(f"/accounts/{account_id}", "Item created. Record a purchase or add what you already own.")


@router.get("/accounts/{account_id:int}/items/{asset_id:int}/edit")
async def edit_item(request: Request, account_id: int, asset_id: int):
    c = container(request)
    account, item = c.accounts.get(account_id), c.physical_items.get(asset_id)
    if item["account_id"] != account_id:
        return redirect(f"/accounts/{account_id}", "That item belongs to another account.")
    asset = c.assets.get_asset(asset_id)
    values = {"name": asset.name, "kind": item["item_kind"],
              "weight": str(Decimal(item["net_gold_grams_e6"]) / Decimal(1_000_000)),
              "karat": str(item["karat"]), "reference_asset_id": str(item["reference_asset_id"]),
              "details": item["details"], "worn": "1" if item["worn"] else ""}
    return render(request, "physical_item_form.html", account=account, item=item,
                  references=_references(c, account), values=values)


@router.post("/accounts/{account_id:int}/items/{asset_id:int}/edit")
async def save_item(request: Request, account_id: int, asset_id: int):
    c = container(request)
    account, form = c.accounts.get(account_id), await request.form()
    if c.physical_items.get(asset_id)["account_id"] != account_id:
        return redirect(f"/accounts/{account_id}", "That item belongs to another account.")
    values = {key: str(form.get(key, "")) for key in ("name", "kind", "weight", "karat", "reference_asset_id", "details")}
    values["worn"] = "1" if form.get("worn") == "1" else ""
    try:
        c.physical_items.update(asset_id, values["name"], values["kind"], values["weight"],
                                int(values["karat"]), int(values["reference_asset_id"]), values["details"],
                                worn=values["worn"] == "1")
        c.reevaluations.process_due()
    except (ValueError, LightningError) as exc:
        error = exc if isinstance(exc, LightningError) else LightningError("Choose a matching gold price reference.")
        if request.headers.get("X-Requested-With") == "fetch":
            return Response(error.message, status_code=400, media_type="text/plain")
        return render(request, "physical_item_form.html", status_code=400, account=account,
                      item=c.physical_items.get(asset_id), references=_references(c, account),
                      values=values, error=error.message, error_field=error.field or "")
    if request.headers.get("X-Requested-With") == "fetch":
        return Response("Saved", status_code=204)
    return redirect(f"/accounts/{account_id}", "Item details saved; current reference-based value reflects the new weight or karat.")


@router.post("/accounts/{account_id:int}/items/{asset_id:int}/trade")
async def trade_item(request: Request, account_id: int, asset_id: int):
    c = container(request)
    item, form = c.physical_items.get(asset_id), await request.form()
    if item["account_id"] != account_id:
        return redirect(f"/accounts/{account_id}", "That item belongs to another account.")
    action = str(form.get("action", "buy"))
    date = str(form.get("date", fmt_date(today())))
    quantity = str(form.get("quantity", "1"))
    total = str(form.get("total", ""))
    fees = str(form.get("fees", "0"))
    cash_id, owner_text = _int(form.get("cash_account_id")), str(form.get("owner", "")).strip()
    notes = str(form.get("notes", ""))
    workmanship = str(form.get("workmanship", "0"))
    try:
        owner = None
        if owner_text:
            party = c.counterparties.resolve(owner_text)
            if not party or not party["active"]:
                raise LightningError("Choose an active saved Counterparty as the item owner.", "owner")
            owner = party["id"]
        if action not in ("buy", "sell", "holding"):
            raise LightningError("Choose Add holding, Purchase, or Sale.", "action")
        if action in ("buy", "sell") and not cash_id:
            raise LightningError("Choose the cash account that paid or received the money.", "cash_account_id")
        with c.db.transaction():
            if action == "buy":
                txn = c.investments.buy_total(date, account_id, asset_id, quantity, total, cash_id, notes,
                                              fees, True, owner)
                if to_decimal(workmanship or "0") > to_decimal(total or "0"):
                    raise LightningError("Workmanship cannot exceed the total purchase cost.", "workmanship")
                c.physical_items.record_trade_details(txn.id, asset_id, "BUY", workmanship, notes)
            elif action == "sell":
                txn = c.investments.sell_total(date, account_id, asset_id, quantity, total, cash_id, notes,
                                               fees, True, owner)
                c.physical_items.record_trade_details(txn.id, asset_id, "SEL", "0", notes)
            else:
                txn = c.investments.add_holding(account_id, asset_id, quantity, total, date, notes, owner)
                c.physical_items.record_trade_details(txn.id, asset_id, "OPN", "0", notes)
    except (ValueError, InvalidOperation, LightningError) as exc:
        msg = exc.message if isinstance(exc, LightningError) else "Check the quantity, amount, and date."
        return redirect(f"/accounts/{account_id}", msg)
    return redirect(f"/accounts/{account_id}", f"Saved {txn.ref}.")


@router.post("/accounts/{account_id:int}/items/{asset_id:int}/value")
async def value_item(request: Request, account_id: int, asset_id: int):
    c = container(request)
    form = await request.form()
    try:
        if c.physical_items.get(asset_id)["account_id"] != account_id:
            raise LightningError("That item belongs to another account.")
        c.physical_items.record_valuation(asset_id, str(form.get("date", fmt_date(today()))),
                                          str(form.get("value", "")), str(form.get("notes", "")))
        c.reevaluations.process_due()
    except (ValueError, InvalidOperation, LightningError) as exc:
        msg = exc.message if isinstance(exc, LightningError) else "Enter a valid value and date."
        return redirect(f"/accounts/{account_id}", msg)
    return redirect(f"/accounts/{account_id}", "Dated manual item valuation saved.")
