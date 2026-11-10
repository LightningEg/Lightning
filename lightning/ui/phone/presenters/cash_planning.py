"""The phone's Cash planning (templates/phone/planning/plan.html): "What leaves before payday, and am I covered?",
shaped from the page's own forecast and payments (3AY11)."""
from __future__ import annotations

from decimal import Decimal

from lightning.core.dates import month_of, parse_date, today
from lightning.core.errors import ValidationError
from lightning.core.figures import label
from lightning.core.money import ZERO, fmt
from lightning.planning.domain import KIND_LABELS, PaymentStatus
from lightning.planning.forecast import emergency_fund
from lightning.ui import status as page_status


PHONE_ROWS_SHOWN = 8


def _phone_cash(c, f, next_payments, late, position, day) -> dict:
    """What the phone's Cash planning adds to the PC's figures (phone overhaul 2026-10-22, "What leaves before payday,
    and am I covered?"): the Due before payday hero with its coverage sentences, the dated list that ends with payday,
    and the Free cash and Reserves tiles. Figures are the ones Safe to spend already uses, so the hero is the working's
    Due before payday row; sentences go to the template as pattern and values (status.sentence)."""
    sentence = page_status.sentence
    until = f.next_income_date
    due = -dict(f.safe_to_spend_parts).get(label("payments_before_next_income"), ZERO)

    def base(p) -> Decimal:
        try:
            return c.planning.amount_in_base(p, p.still_owed, day)
        except ValidationError:  # no rate yet: show the amount as scheduled rather than hide the row
            return p.still_owed

    def when(date_text: str) -> dict:
        days = (parse_date(date_text) - day).days
        return sentence("today") if days <= 0 else sentence("tomorrow") if days == 1 else sentence("in {n} days", n=days)

    def row(p) -> dict:
        late_days = p.days_late(day)
        return {"name": p.item.name, "kind": KIND_LABELS[p.item.kind] if not p.item.is_income else "Payday",
                "income": p.item.is_income, "date": p.due_date, "when": when(p.due_date), "late": late_days,
                "late_text": sentence("Late · 1 day" if late_days == 1 else "Late · {n} days", n=late_days) if late_days else None,
                "amount": base(p), "estimated": False, "popup": True,
                "href": f"/plan/items/{p.item.id}/pay?due={p.due_date}&back=%2Fplan"}

    # Late and due-today payments first (their money is already out of Free cash), then what is not due yet before
    # payday, then payday itself, so the gap between them is plain.
    now = [row(p) for p in next_payments if p.status == PaymentStatus.DUE]
    ahead_payments = sorted(f.payments_before_income, key=lambda p: (p.due_date, p.item.name.casefold()))
    ahead = [row(p) for p in ahead_payments]
    payday_payment = next((p for p in f.upcoming if p.item.is_income), None) if until else None
    payday = None
    if payday_payment:
        payday = row(payday_payment)
    elif until and f.average_income:
        payday = {"name": "Payday", "kind": "Payday", "income": True, "date": until, "when": when(until), "late": 0,
                  "late_text": None, "amount": f.average_income, "estimated": True, "popup": False, "href": "/plan/recurring"}
    shown = {(p.item.id, p.due_date) for p in ahead_payments} | (
        {(payday_payment.item.id, payday_payment.due_date)} if payday_payment else set())
    rest = [row(p) for p in next_payments if p.status == PaymentStatus.UPCOMING and (p.item.id, p.due_date) not in shown]

    # The hero's sentences: how many, whether free cash covers them, whether any are late.
    count = len(ahead)
    if until:
        lines = [sentence("Nothing is due before {date}.", date=until) if not count else
                 sentence("1 payment until {date}." if count == 1 else "{n} payments until {date}.", n=count, date=until)]
    else:
        lines = [sentence("Nothing is due in the next 3 months.") if not count else
                 sentence("1 payment in the next 3 months." if count == 1 else "{n} payments in the next 3 months.", n=count)]
    # Nothing before payday but bills just after it (Audit 10, F15): name the next one, so "0" does not read as
    # nothing to pay.
    following = min((p for p in next_payments if p.status == PaymentStatus.UPCOMING and not p.item.is_income
                     and (p.item.id, p.due_date) not in shown), key=lambda p: p.due_date, default=None)
    if not count and following is not None:
        lines.append(sentence("Next: {name}, {amt} on {date}.", name=following.item.name,
                              amt=fmt(base(following), 0), date=following.due_date))
    if due > ZERO:
        lines.append(sentence("All covered by free cash.") if f.free_cash >= due else
                     sentence("Free cash is {amt} short of what is due.", amt=fmt(due - f.free_cash, 0)))
    if late:
        lines.append(sentence("1 payment is already late." if len(late) == 1 else "{n} payments are already late.", n=len(late)))

    # Two tiles after the list: Free cash against what is left of it after the bills, and Reserves with the
    # emergency fund in months (the figure Reserves already shows).
    fund = emergency_fund(c.reserves, c.budgets, month_of(day), c.schedules.view())
    reserves = position.reserves
    after = fmt(f.free_cash - due, 0).replace("-", "−")
    free_sub = f"After bills: {after}" if due > ZERO else ""
    reserve_sub = (f"Emergency fund {fund.months:.1f} months" if fund.months is not None
                   else "Set aside, not spendable" if reserves else "Nothing set aside yet")
    tiles = [{"key": "free", "surface": "hold", "label": label("free_cash"), "value": f.free_cash, "kind": "money",
              "sub": free_sub, "href": "/"},
             {"key": "reserves", "surface": "hold", "label": label("reserves"), "value": reserves, "kind": "money",
              "empty": "—", "sub": reserve_sub, "href": "/plan/reserves"}]
    return {"due": due, "lines": lines, "now": now, "ahead": ahead, "payday": payday, "rest": rest[:PHONE_ROWS_SHOWN],
            "rest_more": max(len(rest) - PHONE_ROWS_SHOWN, 0), "tiles": tiles}


def present(request, c, context: dict) -> dict:
    day = today()
    payments = context["next_payments"]
    late = [p for p in payments if p.days_late(day) and not p.item.is_income]
    return {"cash": _phone_cash(c, context["forecast"], payments, late, c.position.at(day), day)}
