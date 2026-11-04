"""One holding's history: month-end price, value and cost, and what they say about it (each month's
price change, Fall from its high, Typical move). `lightning.ui.visuals` only draws these figures."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from lightning.core.dates import fmt_date, months_back, parse_date, parse_month
from lightning.core.money import ZERO, from_e6

from .lots import LotLine, build_lots

KINDS = {"BUY": "Bought", "SEL": "Sold", "DIV": "Dividend", "OPN": "Starting holding", "ADJ": "Adjusted"}


def holding_history(reporting, investments, account_id: int, asset_id: int, end: date, months: int = 24) -> dict:
    """Up to ``months`` month ends, from the holding's first trade to ``end``."""
    lines = [l for l in reporting.investment_lines(fmt_date(end), account_id)
             if l.get("asset_id") == asset_id or l.get("dividend_asset_id") == asset_id]
    trades = [l for l in lines if l.get("asset_id") == asset_id and l["type"] != "DIV"]
    if not trades:
        return {"labels": []}
    first = parse_date(trades[0]["date"])
    keys = months_back(end, months, fmt_date(first))
    labels, price, value, cost = [], [], [], []
    for key in keys:
        _, last = parse_month(key)
        day = min(last, end)
        pos = next((x for x in investments.portfolio(fmt_date(day), account_id).positions if x.asset_id == asset_id), None)
        labels.append(key)
        price.append(pos.price if pos and pos.quantity else None)
        value.append(pos.value if pos and pos.quantity else None)
        cost.append(pos.cost_basis if pos and pos.quantity else None)
    # Each month's price change, in percent.
    returns = []
    for i in range(1, len(price)):
        if price[i] is not None and price[i - 1]:
            returns.append((labels[i], (price[i] / price[i - 1] - 1) * 100))
    # Fall from its high: how far each month-end price sat below the highest one before it.
    peak, drawdown = None, []
    for p in price:
        if p is None:
            drawdown.append(None)
            continue
        peak = p if peak is None or p > peak else peak
        drawdown.append((p / peak - 1) * 100 if peak else ZERO)
    # Typical move: the standard deviation of the monthly price changes, once there are three.
    moves = [r for _, r in returns]
    typical = None
    if len(moves) >= 3:
        mean = sum(moves, ZERO) / len(moves)
        typical = (sum(((m - mean) ** 2 for m in moves), ZERO) / len(moves)).sqrt()
    known_dd = [d for d in drawdown if d is not None]
    # The journey: every trade and payout, with units held after it.
    # Cost is also kept in the holding's own currency (the account's), average-cost method, so a dollar holding's
    # dashed line is the dollars paid, not today's pound cost turned back into dollars (audit 2026-10-15).
    held, trail, native_lines = ZERO, [], []
    for l in lines:
        reinvested = l["type"] == "DIV" and l.get("effect") == "INTERNAL"
        if reinvested and l.get("is_cash"):
            continue  # the spend of a reinvested dividend: the units line below is the row
        units = from_e6(l["quantity_e6"] or 0) if reinvested else ZERO if l["type"] == "DIV" else from_e6(l["quantity_e6"] or 0)
        if not units and l["type"] not in KINDS:
            continue  # a month-end revaluation checkpoint is not a trade or a payout (5K)
        amount = from_e6(l["amount_base_e6"] or 0)
        amount_native = from_e6(l.get("amount_e6") or 0)
        returned = not units and l["type"] == "SEL" and l.get("effect") == "INTERNAL" and amount < 0
        if returned:  # a return of capital: the cost falls (never below zero), the units stay
            native_lines.append(LotLine(l["date"], "SEL", "INTERNAL", ZERO, -abs(amount_native)))
        elif units > 0:
            native_lines.append(LotLine(l["date"], l["type"], "EXTERNAL", units, abs(amount_native)))
        elif units < 0 and held:
            native_lines.append(LotLine(l["date"], l["type"], "EXTERNAL", units, -abs(amount_native)))
        held += units
        trail.append({"date": l["date"], "kind": "Capital returned" if returned else "Dividend reinvested" if reinvested else KINDS.get(l["type"], "Holding added" if units > 0 else "Units out"),
                      "units": units, "amount": abs(amount), "price": abs(amount / units) if units else None,
                      "price_native": abs(amount_native / units) if units else None,
                      "held": held, "ref": l.get("ref")})
    # A certificate's interest lands on the bank, so no line of the holding carries it: list each payout (5K).
    for paid in reporting.certificate_interest(fmt_date(end)):
        if paid["account_id"] == account_id and paid["asset_id"] == asset_id:
            held_then = next((t["held"] for t in reversed(trail) if t["date"] <= paid["date"]), ZERO)
            trail.append({"date": paid["date"], "kind": "Interest paid", "units": ZERO, "amount": paid["amount"],
                          "price": None, "price_native": None, "held": held_then, "ref": None})
    trail.sort(key=lambda t: t["date"])   # stable: a payout follows a trade of the same day
    native = build_lots(native_lines, investments.accounts.get(account_id).cost_method).cost
    average = cost[-1] / (value[-1] / price[-1]) if cost[-1] and value[-1] and price[-1] else None
    average_native = native / held if held > 0 else None
    return {"labels": labels, "first": fmt_date(first), "months_held": len(keys), "price": price, "value": value,
            "cost": cost, "average": average, "average_native": average_native, "returns": returns, "drawdown": drawdown,
            "best": max(returns, key=lambda r: r[1]) if returns else None,
            "worst": min(returns, key=lambda r: r[1]) if returns else None,
            "flat": bool(returns) and not any(abs(r[1]) > Decimal("0.0001") for r in returns),  # a fixed price: nothing to show as bumpy
            "typical": typical, "max_drawdown": min(known_dd) if known_dd else None,
            "up": sum(1 for m in moves if m > 0), "down": sum(1 for m in moves if m < 0),
            "trades": list(reversed(trail))}
