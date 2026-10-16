"""Named financial workflows whose existing API is a module-level function."""
from functools import partial

from .codec import JournalError
from .domain import financial_setting


def create_purchase(container, *, name, price, fee, months, first_date, account_id=None, counterparty_id=None):
    from lightning.planning.loan_actions import create_purchase
    return create_purchase(container.planning, name=name, price=price, fee=fee, months=months, first_date=first_date,
                           account_id=account_id, counterparty_id=counterparty_id)


def early_payment(container, item_id, principal, fee, date_paid, account_id, expected_remaining, due_date=None):
    from lightning.planning.loan_actions import record_early_payment
    return record_early_payment(container.planning, item_id, principal, fee, date_paid, account_id, expected_remaining, due_date)


def salary(container, account_id, amount, payday):
    from lightning.workflows.salary_setup import set_up_salary
    return set_up_salary(container, account_id, amount, payday)


def setting(container, key, value):
    if not financial_setting(key) or key == 'base_currency':
        raise JournalError('This setting is local or requires first-run setup')
    from .settings import validate
    validate(key, value)
    container.settings.set(key, value)


OPERATIONS = {
    'loans.create_purchase': create_purchase,
    'loans.record_early_payment': early_payment,
    'salary.setup': salary,
    'profile.set_financial_setting': setting,
}


def operation(container, name):
    if name not in OPERATIONS:
        raise JournalError('Unsupported financial workflow')
    return partial(OPERATIONS[name], container)
