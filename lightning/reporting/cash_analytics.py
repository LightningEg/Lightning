"""Read-only FIFO cash age and the spending calendar (NF-7G).

Cash is pooled per currency across owned accounts. Transfers preserve age; a two-currency
conversion carries the consumed lots' dates into the received units. Opening balances have
unknown age. Investment purchases consume cash without becoming spending samples; proceeds
start a new cash lot. The last ten positive cash expenses determine the amount-weighted age.
"""
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import groupby

from lightning.core.money import ZERO, from_e6


@dataclass(frozen=True)
class CashAge:
    days: Decimal | None
    previous_days: Decimal | None
    payments: int
    unknown_payments: int
    first_date: str | None
    last_date: str | None


def cash_age(db, as_of, currency):
    pools = defaultdict(deque)
    debts = defaultdict(lambda: ZERO)
    samples = []

    def take(code, amount):
        taken = []
        while amount > 0 and pools[code]:
            quantity, earned = pools[code][0]
            used = min(quantity, amount)
            taken.append((used, earned))
            amount -= used
            if used == quantity:
                pools[code].popleft()
            else:
                pools[code][0] = (quantity - used, earned)
        if amount > 0:
            debts[code] += amount
            taken.append((amount, None))
        return taken

    def add(code, amount, earned):
        repaid = min(debts[code], amount)
        debts[code] -= repaid
        if amount > repaid:
            pools[code].append((amount - repaid, earned))

    def portion(lots, start, amount):
        output = []
        for quantity, earned in lots:
            skip = min(start, quantity)
            start -= skip
            used = min(quantity - skip, amount)
            if used > 0:
                output.append((used, earned))
                amount -= used
        return output

    rows = db.all(
        "SELECT t.id,t.date,t.type,f.currency,le.quantity_e6,le.effect,c.code category_code "
        "FROM transactions t JOIN ledger_entries le ON le.transaction_id=t.id "
        "JOIN financial_assets f ON f.id=le.asset_id LEFT JOIN categories c ON c.id=le.category_id "
        "WHERE t.status='POSTED' AND t.date<=? AND f.is_cash=1 AND le.owner_id IS NULL "
        "ORDER BY t.date,t.id,le.line_no", (str(as_of),))
    for _, lines in groupby(rows, key=lambda r: r['id']):
        lines = list(lines)
        day, kind = lines[0]['date'], lines[0]['type']
        totals = defaultdict(lambda: ZERO)
        expense = defaultdict(lambda: ZERO)
        for line in lines:
            code, amount = line['currency'], from_e6(line['quantity_e6'])
            totals[code] += amount
            if line['effect'] == 'OUTFLOW' and line['category_code'] != 'EXP.SYSTEM.CUSTODY':
                expense[code] += max(-amount, ZERO)
        outgoing = [(c, -q) for c, q in totals.items() if q < 0]
        incoming = [(c, q) for c, q in totals.items() if q > 0]
        consumed = {}
        for code, amount in outgoing:
            lots = take(code, amount)
            consumed[code] = lots
            if code == currency and expense[code] > 0:
                # One transaction is one sample, even when its categories are split.
                weight = min(amount, expense[code])
                spent_lots = portion(lots, amount - weight, weight)
                unknown = any(earned is None for _, earned in spent_lots)
                weighted = sum((q * Decimal((date.fromisoformat(day) - date.fromisoformat(earned)).days)
                                for q, earned in spent_lots if earned is not None), ZERO)
                samples.append((day, weight, None if unknown else weighted))
        for code, amount in incoming:
            if kind == 'CNV' and len(outgoing) == len(incoming) == 1:
                source, sent = outgoing[0]
                sent -= expense[source]
                for quantity, earned in portion(consumed[source], ZERO, sent):
                    add(code, amount * quantity / sent, earned)
            else:
                add(code, amount, None if kind == 'OPN' else day)

    def average(window):
        if not window or any(row[2] is None for row in window):
            return None
        return sum((row[2] for row in window), ZERO) / sum((row[1] for row in window), ZERO)
    window = samples[-10:]
    return CashAge(average(window), average(samples[-20:-10]), len(window),
                   sum(row[2] is None for row in window), window[0][0] if window else None,
                   window[-1][0] if window else None)
