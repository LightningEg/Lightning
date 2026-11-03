"""The response must not acknowledge a save before required settlement completes."""
import ast
import asyncio
from contextlib import nullcontext
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def exercise(fail=False, read_only=False, journal=False, status=303):
    events = []
    def settle(day):
        events.append('settle')
        if fail:
            raise OSError('storage failure')
    current = SimpleNamespace(db=SimpleNamespace(closed=False, read_only=read_only),
                              is_journal=journal, planning=SimpleNamespace(match_payments=settle))
    async def app(scope, receive, send):
        await send({'type': 'http.response.start', 'status': status})
        await send({'type': 'http.response.body', 'body': b'', 'more_body': False})
    async def send(message):
        events.append(message['type'])
    path = ROOT / 'lightning/ui/web.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'RequestCache')
    namespace = dict(request_cache=lambda db: nullcontext(), NOT_USER_ACTIONS=set(),
                     ACTION_LABELS={}, today=lambda: '2026-11-03')
    module = ModuleType('lightning.undo')
    module.user_action = lambda label: nullcontext()
    previous = sys.modules.get('lightning.undo')
    sys.modules['lightning.undo'] = module
    try:
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
        middleware = namespace['RequestCache'](app, SimpleNamespace(container=current))
        try:
            asyncio.run(middleware({'type': 'http', 'method': 'POST', 'path': '/transactions'}, None, send))
        except OSError:
            if not fail:
                raise
        return events
    finally:
        if previous is None:
            sys.modules.pop('lightning.undo', None)
        else:
            sys.modules['lightning.undo'] = previous


def test_settlement_precedes_success_headers():
    assert exercise() == ['settle', 'http.response.start', 'http.response.body']


def test_settlement_failure_cannot_send_success():
    assert exercise(fail=True) == ['settle']


def test_failed_read_only_and_journal_responses_do_not_settle():
    for options in ({'status': 422}, {'read_only': True}, {'journal': True}):
        assert exercise(**options) == ['http.response.start', 'http.response.body']


def test_phone_search_response_order():
    node = shutil.which('node')
    if node:
        subprocess.run([node, str(ROOT / 'tests/phone-search-race.test.cjs')], check=True)
