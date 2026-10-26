"""Purchase schedules and extra payments, derived without replacing past loan or cash records."""
from dataclasses import replace
from decimal import Decimal, ROUND_UP

from lightning.core.dates import fmt_date, parse_date, today
from lightning.core.errors import ValidationError
from lightning.core.money import ZERO, check_places, from_e6, to_decimal
from .domain import Frequency, PaymentStatus, PlanKind, PlannedItem
from .schedule import scheduled_dates


def adjusted_payments(payments, terms, extras):
    if terms and payments:
        total = from_e6(terms["price_e6"] + terms["fee_e6"])
        monthly = payments[0].item.amount
        original_last = total - monthly * (terms["payment_count"] - 1)
        payments = [replace(p, amount_override=original_last) if p.number == terms["payment_count"] else p
                    for p in payments]
        live = [i for i, p in enumerate(payments) if p.status != PaymentStatus.SKIPPED]
        if live:
            last = live[-1]
            last_amount = total - sum((payments[i].amount for i in live[:-1]), ZERO)
            payments[last] = replace(payments[last], amount_override=last_amount)
    for extra in extras:
        if extra["due_date"]:
            payments = [replace(p, status=PaymentStatus.PAID,
                                paid_amount=(p.paid_amount or ZERO) + from_e6(extra["principal_e6"]))
                        if p.due_date == extra["due_date"] else p for p in payments]
            continue
        left = from_e6(extra["principal_e6"])
        on = extra.get("date", "0001-01-01")
        order = [i for i, p in enumerate(payments) if p.due_date <= on]
        order += [i for i in range(len(payments) - 1, -1, -1) if payments[i].due_date > on]
        for i in order:
            p = payments[i]
            take = min(left, p.still_owed)
            if take:
                payments[i] = replace(p, amount_override=p.amount - take)
                left -= take
            if not left:
                break
    return [p for p in payments if p.amount > ZERO]


def purchase_quote(price, fee, months, first_date):
    # Instalments are paid in the profile currency: a sub-cent price would leave a final payment nobody can post (2L).
    value = check_places(to_decimal(price, "price"), 2, "price")
    charge = check_places(to_decimal(fee or "0", "fee"), 2, "fee")
    try:
        count = int(str(months))
    except ValueError:
        raise ValidationError("Enter 1 to 600 instalments.", "months") from None
    if value <= ZERO or charge < ZERO or not 1 <= count <= 600:
        raise ValidationError("Enter a positive price, a fee of zero or more, and 1 to 600 instalments.")
    total = value + charge
    monthly = (total / count).quantize(Decimal("0.01"), rounding=ROUND_UP)
    if total - monthly * (count - 1) <= ZERO:
        raise ValidationError("The price is too small for that many instalments.", "months")
    start = fmt_date(parse_date(first_date, "first_date"))
    item = PlannedItem(0, PlanKind.LOAN, "Purchase", monthly, Frequency.MONTHLY, 1, start, None,
                       count, None, None, None, value, True, "")
    return {"price": value, "fee": charge, "months": count, "total": total, "monthly": monthly,
            "final": total - monthly * (count - 1), "first_date": start,
            "last_date": scheduled_dates(item, "2999-12-31")[-1][2]}


def create_purchase(planning, *, name, price, fee, months, first_date, account_id=None, counterparty_id=None):
    quote = purchase_quote(price, fee, months, first_date)
    value, charge, count, monthly = (quote[key] for key in ("price", "fee", "months", "monthly"))
    if account_id:
        account = planning.accounts.require_usable(int(account_id))
        if account.currency != planning.transactions.base_currency or account.account_type.value not in ("BANK", "CASH", "BROKERAGE"):
            raise ValidationError("Choose a cash account in your profile currency.", "account_id")
    with planning.db.transaction():
        item_id = planning.create(kind="LOAN", name=name, amount=monthly, frequency="MONTHLY",
                                  payment_count=count, start_date=first_date, account_id=account_id,
                                  counterparty_id=counterparty_id, principal=value)
        planning.repo.add_installment_terms(item_id, value, charge, count)
    return item_id


def preview_early_payment(planning, item_id, principal, fee="0", on=None):
    item = planning.get(item_id)
    if item.kind != PlanKind.LOAN or not item.active:
        raise ValidationError("Choose an active loan.")
    day = parse_date(on or fmt_date(today()), "date_paid")
    if day > today():
        raise ValidationError("Record the payment on its actual date, not a future date.", "date_paid")
    value = check_places(to_decimal(principal, "principal"), 2, "principal")
    charge = check_places(to_decimal(fee or "0", "fee"), 2, "fee")
    payments = planning.payments(item, "2999-12-31", day)
    remaining = sum((p.still_owed for p in payments), ZERO)
    # A backdated payment is capped by what is owed after every repayment already recorded, including ones
    # dated after it (audit 2026-10-26: two payoffs of a 300 loan took 600).
    owed_now = sum((p.still_owed for p in planning.payments(item, "2999-12-31", max(day, today()))), ZERO)
    if value <= ZERO or value > min(remaining, owed_now) or charge < ZERO:
        raise ValidationError("Pay more than zero and no more than the remaining loan; a fee cannot be negative.")
    adjusted = adjusted_payments(payments, None, [{"due_date": None, "date": fmt_date(day), "principal_e6": int(value * 1_000_000)}])
    unpaid = [p for p in adjusted if p.still_owed > ZERO]
    return {"item": item, "principal": value, "fee": charge, "cash_payment": value + charge,
            "remaining_before": remaining, "remaining_after": remaining - value,
            "last_date": unpaid[-1].due_date if unpaid else None,
            "next_amount": unpaid[0].still_owed if unpaid else ZERO, "date_paid": fmt_date(day)}


def record_early_payment(planning, item_id, principal, fee, date_paid, account_id, expected_remaining, due_date=None):
    with planning.db.transaction():
        return _record_early_payment(planning, item_id, principal, fee, date_paid, account_id, expected_remaining, due_date)


def _record_early_payment(planning, item_id, principal, fee, date_paid, account_id, expected_remaining, due_date=None):
    preview = preview_early_payment(planning, item_id, principal, fee, date_paid)
    item = preview["item"]
    if to_decimal(expected_remaining) != preview["remaining_before"]:
        raise ValidationError("The loan changed. Preview it again before recording a payment.")
    account = planning.accounts.require_usable(int(account_id or item.account_id or 0))
    base = planning.transactions.base_currency
    if account.currency != base or account.account_type.value not in ("BANK", "CASH", "BROKERAGE"):
        raise ValidationError("Choose a cash account in your profile currency.", "account_id")
    if not item.category_id:
        raise ValidationError("Give the loan a payment category first.")
    party = planning.counterparties.get(item.counterparty_id)["name"] if item.counterparty_id else ""
    with planning.db.transaction():
        txn = planning.transactions.record_outflow(preview["date_paid"], account.id, preview["cash_payment"],
                                                   item.category_id, counterparty=party,
                                                   description=item.name,
                                                   notes=f"Loan payment · {item.name}")
        planning.repo.add_extra_payment(item.id, txn.id, preview["principal"], preview["fee"], due_date)
    return txn.id
