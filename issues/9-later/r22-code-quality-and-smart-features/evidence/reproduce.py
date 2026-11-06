"""Run from repo root: python issues/9-later/r22-code-quality-and-smart-features/evidence/reproduce.py
Standard-library-only probes; dummy data; no profile files opened.
The middleware probe executes the actual class with isolated collaborators.
"""
import ast
import asyncio
import importlib.util
import sys
import types
from contextlib import nullcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

def response_before_settlement():
    path = ROOT / 'lightning/ui/web.py'
    tree = ast.parse(path.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'RequestCache')
    events = []
    def match_payments(day):
        events.append('settlement attempted')
        raise OSError('simulated storage failure')
    current = types.SimpleNamespace(db=types.SimpleNamespace(closed=False, read_only=False),
                                    planning=types.SimpleNamespace(match_payments=match_payments))
    async def app(scope, receive, send):
        events.append('primary write committed (simulated)')
        await send({'type': 'http.response.start', 'status': 303})
        await send({'type': 'http.response.body', 'body': b'', 'more_body': False})
    async def send(message):
        events.append(message['type'] + (f" {message['status']}" if 'status' in message else ' complete'))
    module = types.ModuleType('lightning.undo')
    module.user_action = lambda label: nullcontext()
    prior = sys.modules.get('lightning.undo')
    sys.modules['lightning.undo'] = module
    namespace = {'request_cache': lambda db: nullcontext(), 'NOT_USER_ACTIONS': set(),
                 'ACTION_LABELS': {}, 'today': lambda: '2026-11-03'}
    try:
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
        middleware = namespace['RequestCache'](app, types.SimpleNamespace(container=current))
        try:
            asyncio.run(middleware({'type': 'http', 'method': 'POST', 'path': '/transactions'}, None, send))
        except OSError as error:
            events.append(str(error))
        assert events.index('http.response.body complete') < events.index('settlement attempted')
        print('F1:', ' -> '.join(events))
    finally:
        if prior is None:
            sys.modules.pop('lightning.undo', None)
        else:
            sys.modules['lightning.undo'] = prior

def xirr_limits():
    from decimal import Decimal
    path = ROOT / 'lightning/investments/xirr.py'
    spec = importlib.util.spec_from_file_location('audit_xirr', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    flows = [('2025-01-01', Decimal('-100')), ('2026-01-01', Decimal('230')),
             ('2027-01-01', Decimal('-132.16'))]
    result = module.xirr(flows)
    residuals = [sum(amount / (1 + rate) ** i for i, (_, amount) in enumerate(flows))
                 for rate in (Decimal('.12'), Decimal('.18'))]
    assert result is None and all(abs(r) < Decimal('1e-20') for r in residuals)
    print('F3: XIRR returned None for flows -100, +230, -132.16; independently verified roots 12% and 18%.')
    # Execute the existing dependency-free XIRR tests without claiming pytest ran.
    namespace = {}
    exec(compile((ROOT / 'tests/test_xirr.py').read_text(), 'tests/test_xirr.py', 'exec'), namespace)
    tests = [v for k, v in namespace.items() if k.startswith('test_')]
    for test in tests:
        test()
    print(f'Existing XIRR assertions: {len(tests)} test functions passed (direct execution, not pytest).')

if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    response_before_settlement()
    xirr_limits()
