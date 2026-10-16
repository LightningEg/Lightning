"""Explicit home service commands; a message cannot name arbitrary Python code."""
from __future__ import annotations

import inspect
import hashlib
from datetime import date
from decimal import Decimal
from enum import Enum

from .codec import JournalError, canonical, digest, fields, uuid
from .operations import OPERATIONS, operation

# Reviewed service entry points only. Private methods, repositories, callbacks,
# legacy restores and undo row restoration are intentionally absent.
WRITES = {
    'currencies': 'register',
    'institutions': 'add',
    'account_flows': 'open_account update_account deactivate reactivate',
    'accounts': 'set_spendable',
    'assets': 'create_investment update_investment set_price set_prices remove_price set_investment_preferences link_fund link_market',
    'categories': 'create update set_direction delete_or_archive',
    'counterparties': 'create ensure_person rename set_active set_default_category set_kind add_alias remove_alias rename_alias delete_or_archive',
    'transactions': 'record_in_account update_in_account record_inflow record_outflow record_refund update_refund record_transfer update_transfer record_conversion update_conversion change_cash_ownership record_expense_paid_by_person set_transaction_owner set_opening_balance update_money update_metadata update_expense_split set_category bulk_update void restore delete_many merge',
    'investments': 'add_holding buy buy_total sell sell_total dividend update set_target_weight clear_target_weight set_liquidation_factor set_all_liquidation_factors',
    'deposits': 'save purchase update_certificate redeem move_legacy_cash delete',
    'gameya': 'save_terms record_instalment record_payout record_past_instalments',
    'planning': 'create update record_payment mark_paid reopen skip remove set_amount match_payments',
    'reserves': 'create update allocate complete delete set_emergency_fund set_expense_link unlink_expense auto_link_transaction',
    'physical_items': 'create update record_trade_details record_valuation',
    'budgets': 'set_budget set_income_percentage save_month set_carryover reset_carryover move_room apply_fill set_one_off set_recurring_income set_emergency_basis',
    'reconciliation': 'adjust close unlock',
    'money_from_others': 'record sync_transaction sync_transfer sync_investment',
    'reimbursements': 'create_claim delete_claim link_receipt unlink_receipt',
    'deposit_receipts': 'confirm confirm_suggested remove',
    'reevaluations': 'process_due record_manual_price process_sale',
    'zakat': 'save_settings set_enabled',
    'fx': 'save',
    'rules': 'save delete apply_past',
    'health': 'set_limit restore_limit take_raise',
    'funding': 'apply',
}
COMMANDS = frozenset(f'{service}.{method}' for service, methods in WRITES.items() for method in methods.split()) | OPERATIONS.keys()
PREVIEW_COMMANDS = frozenset(('transactions.merge', 'rules.apply_past', 'funding.apply'))
REFS = dict.fromkeys(('account_id', 'from_account_id', 'to_account_id', 'cash_account_id', 'other_account_id',
                      'funding_account_id', 'payout_account_id', 'destination_account_id', 'source_id', 'target_id'), 'accounts')
REFS.update(dict.fromkeys(('category_id', 'default_category_id', 'parent_id', 'from_id', 'to_id'), 'categories'))
REFS.update(dict.fromkeys(('asset_id', 'reference_asset_id'), 'financial_assets'))
REFS.update(dict.fromkeys(('txn_id', 'transaction_id', 'keep_id', 'drop_id'), 'transactions'))
REFS.update(dict.fromkeys(('owner_id', 'from_owner_id', 'to_owner_id', 'counterparty_id', 'payer_id'), 'counterparties'))
REFS.update(dict.fromkeys(('class_id', 'asset_class_id'), 'asset_classes'))
REFS.update(reserve_id='cash_reserves', item_id='planned_items', rule_id='rules', claim_id='reimbursement_claims',
            link_id='reimbursement_receipts', alias_id='counterparty_aliases', certificate_id='cd_certificates')
LIST_REFS = {'txn_ids': 'transactions', 'transaction_ids': 'transactions', 'selected_ids': 'transactions', 'category_ids': 'categories'}
MAP_REFS = {
    'assets.set_prices': {'prices': 'financial_assets'},
    'budgets.save_month': {'amounts': 'categories', 'average_months': 'categories'},
    'budgets.apply_fill': {'amounts': 'categories'},
    'budgets.set_carryover': {'settings': 'categories'},
    'funding.apply': {'amounts': 'categories', 'reserve_additions': 'cash_reserves'},
}
EXTRA_FIELDS = {
    'planning.create': frozenset('kind name amount frequency interval_count start_date end_date payment_count account_id category_id counterparty_id principal notes weekend_move month_day match_window_days match_tolerance_pct'.split()),
    'investments.update': frozenset('date notes owner_id account_id asset_id quantity price fees cash_account_id total total_fees fees_included amount'.split()),
}
EXTRA_FIELDS['planning.update'] = EXTRA_FIELDS['planning.create'] | {'item_id'}
EXTRA_FIELDS['loans.create_purchase'] = frozenset('name price fee months first_date account_id counterparty_id'.split())
EXTRA_FIELDS['loans.record_early_payment'] = frozenset('item_id principal fee date_paid account_id expected_remaining due_date'.split())


def method(container, name):
    if type(name) is not str or name not in COMMANDS:
        raise JournalError('Unsupported financial command; update the home')
    if name in OPERATIONS:
        return operation(container, name)
    service, entry = name.split('.')
    return getattr(getattr(container, service), entry)


def _reference(graph, entity, value, encode):
    if value is None or value == '':
        return None
    if encode:
        if type(value) is str and value.isdecimal():
            value = int(value)
        if type(value) is not int:
            raise JournalError('A financial reference needs a local record')
        return graph.uid(entity, value)
    uuid(value)
    return graph.local(entity, value)


def _convert(graph, name, key, value, encode):
    maps = MAP_REFS.get(name, {})
    if key in maps:
        if value is None:
            return None
        if type(value) is not dict or len(value) > 256:
            raise JournalError('Invalid financial allocation map')
        if encode:
            return {str(_reference(graph, maps[key], k, True)): _plain(v, True) for k, v in value.items()}
        return {(str(_reference(graph, maps[key], k, False)) if name == 'funding.apply' else
                 _reference(graph, maps[key], k, False)): _plain(v, False) for k, v in value.items()}
    if key == 'allocations' and name == 'transactions.update_expense_split':
        if type(value) not in (list, tuple) or len(value) > 256:
            raise JournalError('Invalid expense allocations')
        result = []
        for part in value:
            if type(part) not in (list, tuple) or len(part) != 2:
                raise JournalError('Invalid expense allocation')
            result.append([_reference(graph, 'categories', part[0], encode), _plain(part[1], encode)])
        return result
    if key in LIST_REFS:
        if value is None:
            return None
        if type(value) not in (list, tuple) or len(value) > 256:
            raise JournalError('Invalid financial reference list')
        return [_reference(graph, LIST_REFS[key], item, encode) for item in value]
    if key in REFS:
        return _reference(graph, REFS[key], value, encode)
    if key.startswith('part_category_') and name == 'rules.save':
        return _reference(graph, 'categories', value, encode)
    if key.endswith(('_id', '_ids')):
        raise JournalError('An unsupported reference needs an explicit command contract')
    if type(value) is dict:
        # Rule forms and bulk register changes have nested, named references.
        return {k: _convert(graph, name, k, v, encode) for k, v in value.items()}
    return _plain(value, encode)


def _plain(value, encode):
    if encode and isinstance(value, Enum):
        return value.value
    if encode and isinstance(value, Decimal):
        from lightning.core.money import to_decimal
        value = to_decimal(value)
        return format(value, 'f')
    if encode and isinstance(value, date):
        return value.isoformat()
    canonical(value)
    return value


def translate(container, graph, name, arguments, *, encode):
    target = method(container, name)
    if type(arguments) is not dict:
        raise JournalError('Invalid financial command arguments')
    signature = inspect.signature(target)
    if name in EXTRA_FIELDS and set(arguments) - (set(signature.parameters) | EXTRA_FIELDS[name]):
        raise JournalError('Unknown financial command arguments')
    try:
        signature.bind(**arguments)
    except TypeError as error:
        raise JournalError('Missing or unknown financial command arguments') from error
    if any(key in arguments for key in ('fetch_price', 'allow_legacy_deposit_cash')):
        raise JournalError('Unsupported financial command option')
    result = {key: _convert(graph, name, key, value, encode) for key, value in arguments.items()}
    if name == 'profile.set_financial_setting':
        from .domain import financial_setting, _embedded
        if type(arguments['key']) is not str or type(arguments['value']) is not str:
            raise JournalError('Invalid financial setting')
        if not financial_setting(arguments['key']) or arguments['key'] == 'base_currency':
            raise JournalError('Unsupported financial setting')
        values = dict(key=arguments['key'], value=arguments['value'], updated_at='')
        if encode:
            result['value'] = graph._encode('settings', values)['value']
        elif hasattr(graph, '_decode'):
            _embedded('settings', values)
            result['value'] = graph._decode('settings', values)['value']
        else:
            _embedded('settings', values)
    if not encode:
        for key, parameter in signature.parameters.items():
            annotation = str(parameter.annotation)
            if key in result and result[key] is not None:
                if annotation in ('Decimal', "'Decimal'"):
                    from lightning.core.money import to_decimal
                    result[key] = to_decimal(result[key], key)
                if annotation in ('date | None', "'date | None'"):
                    result[key] = date.fromisoformat(result[key])
                if annotation in ('TxnSource', "'TxnSource'"):
                    from lightning.transactions.domain import TxnSource
                    result[key] = TxnSource(result[key])
    else:
        canonical(result)
    return result


def prepare(container, graph, calls):
    if type(calls) is not list or not 1 <= len(calls) <= 32:
        raise JournalError('A financial action needs 1 to 32 commands')
    commands = []
    for call in calls:
        fields(call, ('command', 'arguments'))
        arguments = dict(call['arguments'])
        if call['command'] == 'profile.set_financial_setting':
            from .settings import validate as validate_setting
            validate_setting(arguments.get('key'), arguments.get('value'))
        if call['command'] in PREVIEW_COMMANDS:
            token = _preview(container, call['command'], arguments)
            if arguments.get('fingerprint') != token:
                raise JournalError('The financial preview changed; open it again')
            arguments['fingerprint'] = 'journal-preview'
        commands.append(dict(command=call['command'], arguments=translate(container, graph, call['command'], arguments, encode=True)))
    # Preserve direct references and the actual write set, rather than every
    # historic posting under a referenced account. A large register must not
    # prevent saving an otherwise small action.
    references = set()
    def collect(value):
        if type(value) is dict:
            for key, child in value.items():
                collect(key)
                collect(child)
        elif type(value) is list:
            for child in value:
                collect(child)
        elif type(value) is str:
            try:
                uuid(value)
                references.add(value)
            except JournalError:
                pass
    collect(commands)
    snapshot = graph.snapshot()
    selected = {}
    from .domain import ID_TABLES, _key
    from .domain_schema import UNIQUE_KEYS
    def remember(table, key):
        selected[(table, canonical(key))] = dict(table=table, key=key, hash=_condition_hash(snapshot, table, key))
    for (table, key), row in sorted(snapshot.items()):
        if table in ID_TABLES and row['id'] in references:
            remember(table, _key(table, row))
    action = dict(calls=commands, preconditions=[], checkpoint=graph.fingerprint()
                  if any(call['command'] in PREVIEW_COMMANDS for call in calls) else None)
    from .preview import changes
    from lightning.core.errors import LightningError
    try:
        written = changes(container, action)
    except (LightningError, JournalError):
        # The home revalidates and records a terminal refusal. A local preview
        # never consumes an origin identity or mutates confirmed money.
        written = []
    except ArithmeticError as error:
        raise JournalError('The financial action exceeds its numeric limits') from error
    for table, before, after in written:
        if before is not None or table not in ID_TABLES:
            remember(table, _key(table, before if before is not None else after))
        if before is None and after is not None:
            for columns in UNIQUE_KEYS.get(table, ()):
                if all(after[column] is not None for column in columns):
                    remember(table, {column: after[column] for column in columns})
    preconditions = list(selected.values())
    if len(preconditions) > 256:
        raise JournalError('This action needs a smaller selection')
    baseline = []
    for (table, _), row in sorted(snapshot.items()):
        if any(condition['table'] == table and all(row[key] == value for key, value in condition['key'].items())
               for condition in preconditions):
            baseline.append(dict(table=table, values=row))
    return action | dict(preconditions=preconditions, baseline=baseline)


def validate(container, graph, action):
    fields(action, ('calls', 'preconditions', 'checkpoint', *(['baseline'] if 'baseline' in action else [])))
    from .codec import hash_value
    if action['checkpoint'] is not None:
        hash_value(action['checkpoint'])
    if type(action['calls']) is not list or not 1 <= len(action['calls']) <= 32:
        raise JournalError('Invalid financial command count')
    for call in action['calls']:
        fields(call, ('command', 'arguments'))
        if call['command'] in PREVIEW_COMMANDS and (action['checkpoint'] is None or call['arguments'].get('fingerprint') != 'journal-preview'):
            raise JournalError('A financial preview needs its checkpoint')
        # Admission checks syntax independently of current ledger existence.
        # Missing/deleted references receive a durable decision during execution.
        class References:
            @staticmethod
            def local(entity, value):
                uuid(value)
                return 1
        try:
            translate(container, References(), call['command'], call['arguments'], encode=False)
        except (ValueError, TypeError, ArithmeticError) as error:
            raise JournalError('Invalid financial command arguments') from error
        if call['command'] == 'workflow.compose':
            from .composition import validate as validate_composition
            validate_composition(container, call['arguments'])
    if type(action['preconditions']) is not list or len(action['preconditions']) > 256:
        raise JournalError('Invalid financial preconditions')
    from .domain import TABLES, _value
    from .domain_schema import UNIQUE_KEYS
    from .codec import hash_value
    for condition in action['preconditions']:
        fields(condition, ('table', 'key', 'hash'))
        table = condition['table']
        if type(table) is not str or table not in TABLES:
            raise JournalError('Unknown financial precondition')
        keys = [tuple(key for key, spec in TABLES[table]['columns'].items() if spec['pk'])] + UNIQUE_KEYS.get(table, [])
        if type(condition['key']) is not dict or not any(set(condition['key']) == set(key) for key in keys):
            raise JournalError('Unknown financial lookup key')
        for key, value in condition['key'].items():
            _value(table, key, value)
        hash_value(condition['hash'])
    if 'baseline' in action:
        _validate_baseline(action)
    canonical(action)


def _validate_baseline(action):
    from .domain import TABLES, _embedded, _key, _value, financial_setting
    baseline = action['baseline']
    if type(baseline) is not list or len(baseline) > 256:
        raise JournalError('Invalid original financial values')
    snapshot = {}
    for entry in baseline:
        fields(entry, ('table', 'values'))
        table, row = entry['table'], entry['values']
        if type(table) is not str or table not in TABLES:
            raise JournalError('Unknown original financial table')
        fields(row, TABLES[table]['columns'])
        for column, value in row.items():
            _value(table, column, value)
        _embedded(table, row)
        if table == 'settings' and not financial_setting(row['key']):
            raise JournalError('Device-local values cannot enter a financial baseline')
        identity = (table, canonical(_key(table, row)))
        if identity in snapshot or not any(condition['table'] == table and all(row[key] == value for key, value in condition['key'].items())
                                           for condition in action['preconditions']):
            raise JournalError('Unexpected original financial row')
        snapshot[identity] = row
    for condition in action['preconditions']:
        if _condition_hash(snapshot, condition['table'], condition['key']) != condition['hash']:
            raise JournalError('Original values do not match their financial preconditions')


def conflicts(graph, action):
    if action['checkpoint'] is not None and action['checkpoint'] != graph.fingerprint():
        return True
    snapshot = graph.snapshot()
    return any(_condition_hash(snapshot, row['table'], row['key']) != row['hash'] for row in action['preconditions'])


def _condition_hash(snapshot, table, key):
    result = hashlib.sha256(b'lightning-command-read-v1\n')
    from .domain_schema import TABLES
    primary = {name for name, spec in TABLES[table]['columns'].items() if spec['pk']}
    if set(key) == primary:
        row = snapshot.get((table, canonical(key)))
        rows = [row] if row is not None else []
    else:
        rows = [row for identity, row in sorted((identity, row) for (entity, identity), row in snapshot.items()
                if entity == table and all(row[column] == value for column, value in key.items()))]
    for row in rows:
        result.update(canonical(row) + b'\n')
    return result.hexdigest()


def execute(container, graph, action):
    validate(container, graph, action)
    for call in action['calls']:
        if call['command'] == 'workflow.compose':
            from .composition import execute as execute_composition
            execute_composition(container, graph, call['arguments'])
            continue
        arguments = translate(container, graph, call['command'], call['arguments'], encode=False)
        if call['command'] == 'transactions.restore':
            record = graph.uid('transactions', arguments['txn_id'])
            if container.db.scalar('SELECT deleted FROM journal_records WHERE record_id=?', (record,)):
                raise JournalError('A deleted journal record needs a new addition')
        if call['command'] in PREVIEW_COMMANDS:
            arguments['fingerprint'] = _preview(container, call['command'], arguments)
        method(container, call['command'])(**arguments)


def _preview(container, name, arguments):
    if name == 'transactions.merge':
        return container.transactions.merge_preview(arguments['keep_id'], arguments['drop_id']).fingerprint
    if name == 'rules.apply_past':
        return container.rules.past_token(arguments['rule_id'])
    if name == 'funding.apply':
        return container.funding.preview()['token']
    raise JournalError('Unsupported financial preview')
