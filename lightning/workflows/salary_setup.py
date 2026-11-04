"""One setup answer becomes an ordinary recurring salary; it never records income."""
from datetime import date
import calendar

from lightning.core.dates import fmt_date, today
from lightning.core.errors import ValidationError
from lightning.planning.domain import PlanKind


def set_up_salary(c, account_id, amount, payday) -> int:
    try:
        selected_account = int(str(account_id))
    except ValueError:
        raise ValidationError("Choose the account your salary goes into.", "account_id") from None
    account = c.accounts.require_usable(selected_account)
    if account.account_type.value not in ("BANK", "CASH") or account.currency != c.base_currency:
        raise ValidationError("Choose a bank or cash account in your profile currency.", "account_id")
    if c.planning.items((PlanKind.INCOME,)):
        raise ValidationError("Your income is already set up. Edit it in Recurring.")
    try:
        day_number = int(str(payday))
    except ValueError:
        raise ValidationError("Choose a payday from 1 to 31.", "payday") from None
    if not 1 <= day_number <= 31:
        raise ValidationError("Choose a payday from 1 to 31.", "payday")
    on = today()
    start = date(on.year, on.month, min(day_number, calendar.monthrange(on.year, on.month)[1]))
    if start < on:
        year, month = (on.year + 1, 1) if on.month == 12 else (on.year, on.month + 1)
        start = date(year, month, min(day_number, calendar.monthrange(year, month)[1]))
    category = c.categories.get_by_code("EXP.WORK.SALARY")
    with c.db.transaction():
        item_id = c.planning.create(kind="INCOME", name="Salary", amount=amount, frequency="MONTHLY",
                                   start_date=fmt_date(start), month_day=day_number,
                                   account_id=account.id, category_id=category.id)
    return item_id
