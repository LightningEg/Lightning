"""Recording a buy, sell, dividend, fee, interest or move typed into an investment account's register row.

The route parses the form; this records it, each entry in one database transaction, and raises
LightningError (with the field) when the entry cannot be recorded.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from lightning.accounts.domain import AccountType, INVESTMENT_ACCOUNT_TYPES
from lightning.assets.catalog import instruments as catalog_instruments
from lightning.core.codes import slug
from lightning.core.dates import fmt_date, parse_date, today
from lightning.core.errors import ValidationError
from lightning.core.money import ZERO, to_decimal

FIELDS = ("date", "instrument_key", "trade_action", "units", "total", "dividend_basis", "unit_price", "price_basis",
          "fees", "fees_included", "cash_account_id", "notes", "whom", "paid_from", "tax_withheld", "to_account_id")


def cash_account_id(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if not text.isdigit() or int(text) <= 0:
        raise ValidationError("Choose a valid cash account.", "cash_account_id")
    return int(text)


def catalog_asset(assets, item):
    """The held asset behind a catalogue row: same ticker on the same exchange (U9)."""
    prefix = "STK" if item["class_code"] == "STOCK" else "FND"
    symbol, mic = slug(item["ticker"], 20), (item.get("mic") or "").upper()
    for asset in assets:
        if asset.code in (f"{prefix}:{symbol}", f"{prefix}:{symbol}-{mic}" if mic else ""):
            if not mic or not asset.mic or asset.mic.upper() == mic:
                return asset
    return None


def record(c, account, values: dict):
    """Record the entry in `values` (FIELDS, plus is_others) on `account`; returns the posted transaction.
    `values` may be updated (price_basis) so a refused entry shows what was worked out."""
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
        return txn
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
    cash_id = cash_account_id(values["cash_account_id"])
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
            asset = catalog_asset(c.assets.investments(), ticker_row)
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
            return txn
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
                                        cash_account_id=cash_id,
                                        notes=values["notes"], owner_id=owner_id)
            else:
                if not total:
                    raise ValidationError("Enter the total paid or a price per unit.", "total")
                txn = c.investments.buy_total(values["date"], account.id, asset.id, units, total,
                                              fees=values["fees"], fees_included=values["fees_included"] != "0",
                                              cash_account_id=cash_id,
                                              notes=values["notes"], owner_id=owner_id)
        else:
            units = -units
            basis = values["price_basis"]
            if basis == "unit_price" or (unit_price and not total):
                if not unit_price:
                    raise ValidationError("Enter a price per unit or the total received.", "unit_price")
                txn = c.investments.sell(values["date"], account.id, asset.id, units, unit_price,
                                         fees=values["fees"],
                                         cash_account_id=cash_id,
                                         notes=values["notes"], owner_id=owner_id)
            else:
                if not total:
                    raise ValidationError("Enter the total received or a price per unit.", "total")
                txn = c.investments.sell_total(values["date"], account.id, asset.id, units, total,
                                               fees=values["fees"], fees_included=values["fees_included"] != "0",
                                               cash_account_id=cash_id,
                                               notes=values["notes"], owner_id=owner_id)
        held_in = next((line.account_id for line in txn.lines if line.asset_id == asset.id), account.id)  # a pocket
        c.money_from_others.sync_investment(txn.id, txn.date, owner, held_in, asset.id, signed_units)
        if owner:
            cash_line = next((line for line in txn.lines if c.assets.get_asset(line.asset_id).is_cash), None)
            if cash_line:
                cash_amount = cash_line.quantity
                c.money_from_others.sync_transaction(txn.id, txn.date, owner, cash_line.account_id,
                                                     cash_amount, values["notes"])
    return txn
