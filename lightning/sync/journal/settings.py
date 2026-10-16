"""Semantic validation for the explicit financial-preference command."""
import json

from lightning.core.dates import parse_month
from lightning.core.money import to_decimal
from .codec import JournalError, uuid
from .domain import ID_SETTINGS

_BOOLEAN = frozenset(('cash_funding_enabled', 'income_from_recurring', 'budget_carryover_global', 'zakat_enabled'))
_MONEY = frozenset(('investment_monthly_goal', 'budget_manual_monthly_income', 'budget_overall_ceiling', 'income_raise_declined'))


def validate(key, value):
    if type(key) is not str or type(value) is not str or len(value) > 16384:
        raise JournalError('Invalid financial preference')
    if key in _BOOLEAN:
        if value not in ('0', '1'):
            raise JournalError('Choose whether this preference is enabled')
    elif key in _MONEY:
        if value == '' and key != 'investment_monthly_goal':
            return
        if to_decimal(value, 'amount') < 0:
            raise JournalError('A financial preference amount cannot be negative')
    elif key == 'budget_income_months':
        if value not in ('3', '6'):
            raise JournalError('Use three or six completed months for income')
    elif key == 'investment_planner_mode':
        from lightning.investments.report import PLANNER_MODES
        if value not in PLANNER_MODES:
            raise JournalError('Choose a supported investment planning method')
    elif key == 'budget_carryover_month':
        parse_month(value)
    elif key in ID_SETTINGS or key == 'budget_suppressed_categories':
        try:
            selection = json.loads(value)
        except ValueError as error:
            raise JournalError('Invalid category selection') from error
        if key in ID_SETTINGS:
            if type(selection) is not list or len(selection) > 256:
                raise JournalError('Invalid category selection')
            values = selection
        else:
            if type(selection) is not dict or len(selection) > 256:
                raise JournalError('Invalid suppressed categories')
            values = selection.keys()
            for until in selection.values():
                if until != 'never':
                    if type(until) is not str:
                        raise JournalError('Choose a valid suppression month')
                    parse_month(until)
        for identifier in values:
            if type(identifier) is int and identifier > 0:
                continue
            if key == 'budget_suppressed_categories' and type(identifier) is str and identifier.isdecimal() and int(identifier) > 0:
                continue
            uuid(identifier)
    else:
        raise JournalError('Use the dedicated financial screen to change this preference')
