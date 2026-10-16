"""Bounded normal-service workflows with references to earlier return values.

Bindings are message-local handles, not replica IDs or SQL patches. Return
accessors are defined in code for reviewed methods; the wire cannot select a
Python attribute, callback, table, or an arbitrary expression.
"""
from .codec import JournalError, fields, number, uuid
from .domain import DomainGraph


RESULTS = {
    'categories.create': {'record': ('categories', 'object')},
    'counterparties.create': {'record': ('counterparties', 'integer')},
    'counterparties.ensure_person': {'record': ('counterparties', 'integer')},
    'planning.create': {'record': ('planned_items', 'integer')},
    'reserves.create': {'record': ('cash_reserves', 'mapping')},
    'assets.create_investment': {'record': ('financial_assets', 'object')},
    'account_flows.open_account': {'record': ('accounts', 'object')},
    'physical_items.create': {'record': ('financial_assets', 'integer')},
    'rules.save': {'record': ('rules', 'integer')},
    'loans.create_purchase': {'record': ('planned_items', 'integer')},
    'salary.setup': {'record': ('planned_items', 'integer')},
    'deposits.purchase': {'certificate': ('cd_certificates', 'first_object'),
                          'transaction': ('transactions', 'second_object')},
}
for _name in ('record_in_account', 'update_in_account', 'record_inflow', 'record_outflow', 'record_refund',
              'record_transfer', 'record_conversion', 'change_cash_ownership', 'record_expense_paid_by_person',
              'set_opening_balance'):
    RESULTS['transactions.'+_name] = {'record': ('transactions', 'object')}
for _name in ('add_holding', 'buy', 'buy_total', 'sell', 'sell_total', 'dividend'):
    RESULTS['investments.'+_name] = {'record': ('transactions', 'object')}


def result_id(command, slot, result):
    try:
        entity, kind = RESULTS[command][slot]
        if kind == 'integer':
            value = result
        elif kind == 'mapping':
            value = result['id']
        elif kind == 'first_object':
            value = result[0].id
        elif kind == 'second_object':
            value = result[1].id
        else:
            value = result.id
        if type(value) is not int or value <= 0:
            raise ValueError
        return entity, value
    except (KeyError, TypeError, AttributeError, IndexError, ValueError) as error:
        raise JournalError('This financial workflow returned an unsupported record') from error


class _References:
    def __init__(self, bindings, index, resolved=None, graph=None):
        self.bindings, self.index, self.resolved, self.graph = bindings, index, resolved, graph

    def local(self, entity, value):
        uuid(value)
        binding = self.bindings.get(value)
        if binding:
            if binding['step'] >= self.index or binding['entity'] != entity:
                raise JournalError('A workflow reference must name an earlier compatible result')
            if self.resolved is None:
                return 1  # Syntax validation never invents a live local record.
            if value not in self.resolved:
                raise JournalError('An earlier workflow result is missing')
            return self.resolved[value]
        return self.graph.local(entity, value) if self.graph is not None else 1

    def _decode(self, table, values):
        # Only the preference translator uses this hook. The fixed decoder
        # resolves embedded category UUIDs through local(), including handles.
        if table != 'settings':
            raise JournalError('Unsupported embedded workflow reference')
        return DomainGraph._decode(self, table, values)


def validate(container, arguments):
    from . import commands
    fields(arguments, ('steps', 'bindings'))
    steps, bindings = arguments['steps'], arguments['bindings']
    if type(steps) is not list or not 1 <= len(steps) <= 32 or type(bindings) is not dict or len(bindings) > 64:
        raise JournalError('This workflow needs a smaller selection')
    for handle, binding in bindings.items():
        uuid(handle)
        fields(binding, ('step', 'entity', 'slot'))
        number(binding['step'])
        if binding['step'] >= len(steps) or type(binding['slot']) is not str:
            raise JournalError('Unknown workflow return value')
        step = steps[binding['step']]
        if type(step) is not dict or type(step.get('command')) is not str:
            raise JournalError('Unknown workflow step')
        contract = RESULTS.get(step['command'], {}).get(binding['slot'])
        if contract is None or binding['entity'] != contract[0]:
            raise JournalError('Unknown workflow result contract')
    for index, step in enumerate(steps):
        fields(step, ('command', 'arguments'))
        name = step['command']
        if type(name) is not str or name == 'workflow.compose' or name in commands.PREVIEW_COMMANDS:
            raise JournalError('This operation needs its own reviewed financial workflow')
        commands.translate(container, _References(bindings, index), name, step['arguments'], encode=False)


def execute(container, graph, arguments):
    from . import commands
    validate(container, arguments)
    steps, bindings = arguments['steps'], arguments['bindings']
    for handle in bindings:
        if graph.db.scalar('SELECT 1 FROM journal_ids WHERE uuid=?', (handle,)):
            raise JournalError('A workflow handle cannot replace a confirmed identity')
    resolved = {}
    for index, step in enumerate(steps):
        arguments = commands.translate(container, _References(bindings, index, resolved, graph),
                                       step['command'], step['arguments'], encode=False)
        result = commands.method(container, step['command'])(**arguments)
        for handle, binding in bindings.items():
            if binding['step'] == index:
                entity, local_id = result_id(step['command'], binding['slot'], result)
                if not graph.db.scalar(f'SELECT 1 FROM {entity} WHERE id=?', (local_id,)):
                    raise JournalError('The workflow result has no financial record')
                resolved[handle] = local_id
