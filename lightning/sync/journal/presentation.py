"""Readable descriptions of signed financial commands, without local IDs."""
import json
from .codec import JournalError, uuid
from .commands import LIST_REFS, MAP_REFS, REFS
from .domain import ID_SETTINGS, ID_TABLES, _reference


_TITLES = {
    'transactions.record_in_account': 'Record a payment',
    'transactions.record_outflow': 'Record money out',
    'transactions.record_inflow': 'Record money in',
    'transactions.void': 'Delete a transaction',
    'categories.create': 'Add a category',
    'account_flows.open_account': 'Open an account',
    'profile.set_financial_setting': 'Change a financial preference',
    'salary.setup': 'Set up salary',
    'loans.create_purchase': 'Add an instalment purchase',
    'loans.record_early_payment': 'Pay a loan early',
}
_LABELS = dict(account_id='Account', cash_account_id='Cash account', other_account_id='Other account',
               category_id='Category', asset_id='Investment', txn_id='Transaction', parent_id='Inside category',
               item_id='Planned payment', rule_id='Rule', owner_id='Owner', counterparty_id='Person',
               investment_monthly_goal='Monthly investment goal', budget_tracked_categories='Budget categories',
               amount='Amount', price='Price', fees='Fees', quantity='Quantity', date='Date', name='Name')
_HIDDEN = frozenset(('fingerprint', 'fetch_price', 'allow_legacy_deposit_cash'))


def _name(graph, value, entity=None, names=None):
    try:
        uuid(value)
    except (JournalError, TypeError):
        return None
    if names and value in names:
        return names[value]
    rows = graph.db.all('SELECT entity,local_id FROM journal_ids WHERE uuid=? ORDER BY entity', (value,))
    for row in rows:
        if entity and row['entity'] != entity:
            continue
        table = row['entity']
        if table not in ID_TABLES:
            continue
        found = graph.db.one(f'SELECT * FROM {table} WHERE id=?', (row['local_id'],))
        if found:
            for column in ('name', 'ref', 'code', 'title'):
                if column in found.keys() and found[column]:
                    return str(found[column])
    return 'Removed record'


def _value(graph, value, *, entity=None, names=None):
    if value is None or value == '':
        return 'None'
    if type(value) is bool:
        return 'Yes' if value else 'No'
    if type(value) is str:
        return (_name(graph, value, entity, names) or value) if entity else value
    if type(value) is list:
        return ', '.join(_value(graph, child, entity=entity, names=names) for child in value) or 'None'
    if type(value) is dict:
        result = []
        for key, child in value.items():
            label = (_name(graph, key, entity, names) if entity else None) or _LABELS.get(key, key.replace('_', ' ').capitalize())
            child_entity = 'accounts' if key == 'value' and value.get('field') == 'account' else REFS.get(key) or LIST_REFS.get(key)
            result.append(f'{label}: {_value(graph, child, entity=child_entity, names=names)}')
        return '; '.join(result) or 'None'
    return str(value)


def describe(graph, action):
    if action is None:
        return [('History', 'Detailed changes have expired')]
    result = []
    calls = []
    for call in action['calls']:
        if call['command'] == 'workflow.compose':
            arguments = call['arguments']
            names = {}
            for handle, binding in arguments['bindings'].items():
                producer = arguments['steps'][binding['step']]
                names[handle] = producer['arguments'].get('name') or 'Created in this change'
            calls.extend((step, names) for step in arguments['steps'])
        else:
            calls.append((call, {}))
    for call, names in calls:
        name, arguments = call['command'], call['arguments']
        title = _TITLES.get(name, name.split('.', 1)[1].replace('_', ' ').capitalize())
        result.append(('Change', title))
        for key, value in arguments.items():
            if key in _HIDDEN:
                continue
            label = _LABELS.get(key, key.removesuffix('_id').replace('_', ' ').capitalize())
            if name == 'profile.set_financial_setting' and key == 'key':
                result.append(('Preference', _LABELS.get(value, value.replace('_', ' ').capitalize())))
            elif name == 'profile.set_financial_setting' and key == 'value' and arguments['key'] in ID_SETTINGS | {'budget_suppressed_categories'}:
                result.append((label, _value(graph, json.loads(value), entity='categories', names=names)))
            else:
                result.append((label, _value(graph, value, entity=REFS.get(key) or LIST_REFS.get(key) or MAP_REFS.get(name, {}).get(key), names=names)))
    return result


def current(graph, action):
    """Current affected rows for a home review, with typed money and names."""
    return _rows(graph, action, graph.snapshot())


def before(graph, action):
    if 'baseline' not in action:
        return [('History', 'This older edit did not retain its original values')]
    from .codec import canonical
    from .domain import _key
    snapshot = {(entry['table'], canonical(_key(entry['table'], entry['values']))): entry['values']
                for entry in action['baseline']}
    return _rows(graph, action, snapshot)


def _rows(graph, action, snapshot):
    from lightning.core.money import from_e6
    result, seen = [], set()
    for condition in action['preconditions']:
        table, key = condition['table'], condition['key']
        matches = [(identity, row) for (entity, identity), row in snapshot.items() if entity == table
                   and all(row[column] == value for column, value in key.items())]
        if not matches:
            result.append((table.replace('_', ' ').capitalize(), 'Not present'))
        for identity, row in matches:
            if (table, identity) in seen:
                continue
            seen.add((table, identity))
            result.append(('Record', table.replace('_', ' ').capitalize()))
            for column, value in row.items():
                if column in ('id', 'created_at', 'updated_at') or value is None:
                    continue
                label = _LABELS.get(column, column.removesuffix('_id').removesuffix('_e6').replace('_', ' ').capitalize())
                if column.endswith('_e6'):
                    shown = format(from_e6(int(value)), 'f')
                elif column == 'key' and table == 'settings':
                    shown = _LABELS.get(value, value.replace('_', ' ').capitalize())
                elif column == 'value' and table == 'settings' and row['key'] in ID_SETTINGS | {'budget_suppressed_categories'}:
                    shown = _value(graph, json.loads(value), entity='categories')
                else:
                    entity = 'accounts' if table == 'rule_conditions' and column == 'value' and row['field'] == 'account' else _reference(table, column)
                    shown = _value(graph, value, entity=entity)
                result.append((label, shown))
    return result
