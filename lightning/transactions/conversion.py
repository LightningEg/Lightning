"""Conversion (CNV): your own money changing currency, e.g. pounds into dollars at the bank.

One document, lines that net to zero in the profile currency:
- sending line   -sent, the money that left;
- receiving line +received at the EXECUTED rate, so the dollars carry what they really cost, spread included;
- fee            an OUTFLOW from the sending account in Fees & Charges (never part of the rate).

The executed rate is also saved as a dated rate (source TRADE) so the day has a rate even before any file arrives.
The line-level rule (amount_base == round2(amount x rate), a rate of at most 6 places) cannot always hit a
base amount exactly on a big amount; `exact_lines` then spreads it over two lines of the same account.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from lightning.core.errors import ValidationError
from lightning.core.ledger import Effect, PostingLine, _round2
from lightning.core.money import ONE, ZERO
from lightning.core.refs import DocType
from lightning import fx
from lightning.fx import rate_for, save_rate

SIX = Decimal("0.000001")
FEE_CATEGORY = "EXP.PERSONAL.FEES"
CONVERTIBLE = ("CASH", "BANK", "BROKERAGE")
_TAIL = Decimal(1000)   # units split off the end of a very large amount to absorb the cent rounding


def exact_lines(account_id: int, asset_id: int, units: Decimal, base: Decimal, memo: str) -> list[PostingLine]:
    """Cash lines in one account moving `units` (signed) that together carry exactly `base` (same sign) in the
    profile currency, each line obeying amount_base == round2(amount x rate) with a rate of at most 6 places."""
    sign = 1 if units > 0 else -1
    size, wanted = abs(units), abs(base)
    rate = (wanted / size).quantize(SIX)
    if rate <= 0:
        raise ValidationError("The amount received is too large for the amount sent.", "received")

    def line(part: Decimal, at: Decimal) -> PostingLine:
        return PostingLine.cash(account_id, asset_id, sign * part, Effect.INTERNAL, fx_rate=at, memo=memo)

    def fit(part: Decimal, target: Decimal, near: Decimal) -> Decimal | None:
        for step in (0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5):
            candidate = near + step * SIX
            if candidate > 0 and _round2(part * candidate) == target:
                return candidate
        return None

    single = fit(size, wanted, rate)
    if single is not None:
        return [line(size, single)]
    if size <= 2 * _TAIL:
        raise ValidationError("These amounts do not fit one exchange rate; check them.", "received")
    main = size - _TAIL
    main_rate = fit(main, _round2(main * rate), rate)  # a rate that carries the main part's own rounded base
    if main_rate is None:
        main_rate = rate
    main_base = _round2(main * main_rate)
    tail_base = wanted - main_base
    tail_rate = fit(_TAIL, tail_base, (tail_base / _TAIL).quantize(SIX)) if tail_base > 0 else None
    if tail_rate is None:
        raise ValidationError("These amounts do not fit one exchange rate; check them.", "received")
    return [line(main, main_rate), line(_TAIL, tail_rate)]


def build(svc, day: str, src, dst, sent, received, fee) -> list[PostingLine]:
    """The posting lines of a conversion from account `src` to `dst` on `day` (see the module docstring)."""
    if src.id == dst.id:
        raise ValidationError("Choose two different accounts.", "to_account")
    for account, field in ((src, "from_account"), (dst, "to_account")):
        if account.account_type.value not in CONVERTIBLE:
            raise ValidationError("Money can be converted between cash, bank and brokerage accounts.", field)
    if src.currency == dst.currency:
        raise ValidationError("Both accounts use the same currency; use a transfer.", "to_account")
    base = svc.base_currency
    src_asset, dst_asset = svc.assets.cash_asset(src.currency), svc.assets.cash_asset(dst.currency)
    sent = svc._positive_amount(sent, src_asset.quantity_decimals)
    received = svc._positive_amount(received, dst_asset.quantity_decimals)
    fee = ZERO if fee in (None, "") else svc._amount_or_zero(fee, src_asset.quantity_decimals)

    if src.currency == base:           # buying foreign money: the dollars carry what the pounds cost
        out_lines = [PostingLine.cash(src.id, src_asset.id, -sent, Effect.INTERNAL, memo="Conversion out")]
        in_lines = exact_lines(dst.id, dst_asset.id, received, sent, "Conversion in")
        send_rate = ONE
    elif dst.currency == base:         # selling foreign money: it leaves at the price it fetched
        out_lines = exact_lines(src.id, src_asset.id, -sent, -received, "Conversion out")
        in_lines = [PostingLine.cash(dst.id, dst_asset.id, received, Effect.INTERNAL, memo="Conversion in")]
        send_rate = (received / sent).quantize(SIX)
    else:                              # foreign into foreign: the sending side at the day's rate
        send_rate = svc._rate(src.currency, day)
        out_lines = [PostingLine.cash(src.id, src_asset.id, -sent, Effect.INTERNAL, fx_rate=send_rate,
                                      memo="Conversion out")]
        in_lines = exact_lines(dst.id, dst_asset.id, received, _round2(sent * send_rate), "Conversion in")
    lines = out_lines + in_lines
    if fee > 0:
        category = svc.categories.get_by_code(FEE_CATEGORY)
        lines.append(PostingLine.cash(src.id, src_asset.id, -fee, Effect.OUTFLOW, category.id,
                                      memo="Conversion fee", fx_rate=send_rate))
    return lines


@dataclass(frozen=True)
class Described:
    """A conversion read back from its lines."""
    src_account_id: int
    dst_account_id: int
    sent: Decimal
    sent_currency: str
    received: Decimal
    received_currency: str
    fee: Decimal
    base_value: Decimal          # what the money was worth in the profile currency when it changed hands
    quote_base: str              # the executed rate reads: 1 <quote_base> = rate <quote_quote>
    quote_quote: str
    rate: Decimal


def describe(svc, txn) -> Described | None:
    cash = [ln for ln in txn.lines if svc.assets.get_asset(ln.asset_id).is_cash]
    out = [ln for ln in cash if ln.effect == Effect.INTERNAL and ln.quantity < 0]
    inn = [ln for ln in cash if ln.effect == Effect.INTERNAL and ln.quantity > 0]
    if not out or not inn:
        return None
    sent, received = -sum((ln.quantity for ln in out), ZERO), sum((ln.quantity for ln in inn), ZERO)
    src_ccy = svc.assets.get_asset(out[0].asset_id).currency
    dst_ccy = svc.assets.get_asset(inn[0].asset_id).currency
    fee = -sum((ln.quantity for ln in cash if ln.effect == Effect.OUTFLOW), ZERO)
    value = sum((ln.amount_base for ln in inn), ZERO)
    pair, rate = executed(svc.base_currency, src_ccy, dst_ccy, sent, received)
    return Described(out[0].account_id, inn[0].account_id, sent, src_ccy, received, dst_ccy, fee, value,
                     pair[0], pair[1], rate)


def executed(base: str, sent_ccy: str, received_ccy: str, sent: Decimal, received: Decimal):
    """((a, b), rate): the rate reads 1 a = rate b. With the profile currency on one side it is the foreign
    currency's price in the profile currency; between two foreign currencies, what one sent unit became."""
    if sent_ccy == base:
        return (received_ccy, base), (sent / received).quantize(SIX)
    if received_ccy == base:
        return (sent_ccy, base), (received / sent).quantize(SIX)
    return (sent_ccy, received_ccy), (received / sent).quantize(SIX)


def quote(svc, day: str, src, dst, sent, received) -> dict | None:
    """What the form shows while you type: the executed rate and how far it is from the day's market rate."""
    try:
        sent = svc._positive_amount(sent, svc.assets.cash_asset(src.currency).quantity_decimals)
        received = svc._positive_amount(received, svc.assets.cash_asset(dst.currency).quantity_decimals)
    except (ValidationError, ArithmeticError):
        return None
    if sent <= 0 or received <= 0 or src.currency == dst.currency:
        return None
    pair, rate = executed(svc.base_currency, src.currency, dst.currency, sent, received)
    out = {"base": pair[0], "quote": pair[1], "rate": str(rate)}
    reference = reference_rate(svc, pair, day)
    if reference:
        change = ((rate / reference.rate - 1) * 100).quantize(Decimal("0.1"))
        out |= {"reference": str(reference.rate), "reference_date": reference.date,
                "direction": "above" if rate >= reference.rate else "below", "percent": str(abs(change))}
        cost = spread_cost(svc, Described(src.id, dst.id, sent, src.currency, received, dst.currency, ZERO, ZERO,
                                          pair[0], pair[1], rate), day)
        if cost is not None:
            out["cost"] = str(cost)
    return out


def reference_rate(svc, pair: tuple[str, str], day: str):
    """The day's market rate for the pair, never the conversion's own saved rate (source TRADE)."""
    return rate_for(svc.db, pair[0], pair[1], day, exclude=("TRADE",))


def spread_cost(svc, d: Described, day: str) -> Decimal | None:
    """What the bank kept beyond the market rate, in the profile currency: the reference value of what you sent
    minus the reference value of what you received. None when no reference rate exists for the day."""
    return fx.spread_cost(svc.db, svc.base_currency, d.sent, d.sent_currency, d.received, d.received_currency, day)


def rebuild_trade_rates(svc) -> None:
    """The executed rates of posted conversions, one per day and currency (the latest wins): a conversion that
    is edited, deleted or restored changes them, and nothing else writes source TRADE."""
    with svc.db.transaction():
        svc.db.execute("DELETE FROM fx_rates WHERE source='TRADE'")
        rows = svc.db.all("SELECT id,date FROM transactions WHERE type=? AND status='POSTED' ORDER BY date,id",
                          (DocType.CNV.value,))
        for row in rows:
            d = describe(svc, svc.get(row["id"]))
            if d and svc.base_currency in (d.quote_base, d.quote_quote) and d.quote_base != d.quote_quote:
                save_rate(svc.db, row["date"], d.quote_base, d.quote_quote, d.rate, "TRADE")


def refresh_trade_rates(svc, transactions) -> None:
    """Refresh affected date/pair keys only, including the old keys of edited conversions.

    The highest posted transaction id wins on each date, as in the full repair rebuild.
    Only that winner needs its posting lines loaded, even with many same-day conversions.
    """
    keys = set()
    for txn in transactions:
        if txn.type != DocType.CNV:
            continue
        d = describe(svc, txn)
        if d and svc.base_currency in (d.quote_base, d.quote_quote) and d.quote_base != d.quote_quote:
            keys.add((txn.date, d.quote_base, d.quote_quote))
    with svc.db.transaction():
        for day, base, quote_ccy in sorted(keys):
            winner = svc.db.one(
                "SELECT t.id FROM transactions t WHERE t.type='CNV' AND t.status='POSTED' AND t.date=? "
                "AND EXISTS (SELECT 1 FROM ledger_entries le JOIN financial_assets a ON a.id=le.asset_id "
                "WHERE le.transaction_id=t.id AND le.effect='INTERNAL' AND a.currency=?) "
                "AND EXISTS (SELECT 1 FROM ledger_entries le JOIN financial_assets a ON a.id=le.asset_id "
                "WHERE le.transaction_id=t.id AND le.effect='INTERNAL' AND a.currency=?) "
                "ORDER BY t.id DESC LIMIT 1", (day, base, quote_ccy))
            svc.db.execute("DELETE FROM fx_rates WHERE date=? AND base=? AND quote=? AND source='TRADE'",
                           (day, base, quote_ccy))
            if winner:
                d = describe(svc, svc.get(winner["id"]))
                save_rate(svc.db, day, base, quote_ccy, d.rate, "TRADE")
