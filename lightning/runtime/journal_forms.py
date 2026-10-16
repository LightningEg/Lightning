"""Buffered financial-form adapter for explicit experimental journal runtimes.

File operations, legacy undo and import staging require separate adapters and
fail before dispatch. Every enabled route still needs an exact replay match.
"""
from __future__ import annotations

import asyncio
from html import unescape
import re
import secrets
from urllib.parse import urljoin, urlsplit, urlencode

from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response

from lightning.core.errors import LightningError
from lightning.sync.journal.codec import JournalError, digest
from lightning.sync.journal.forms import FormCapture, issue_form, prior_submission, submission_basis
from .http import body_receiver


FINANCIAL_WRITES = re.compile(r'(?:'
    r'/transactions/(?:register(?:/\d+)?|\d+/(?:split|reserve|void|delete|restore|edit-popup|convert/edit|ownership/edit)|bulk-(?:delete|category|edit))'
    r'|/accounts/(?:new|\d+/(?:register(?:/\d+)?|edit|deactivate|spendable|reactivate|convert|transaction/new|ownership/new|reconcile(?:/close|/unlock)?|investment-entry))'
    r'|/accounts/\d+/items/(?:new|\d+/(?:edit|trade|value))'
    r'|/categories/(?:new|add-row|bulk-action|\d+/(?:row|edit|delete))'
    r'|/counterparties'
    r'|/investments/(?:planner|targets|asset-plan/\d+|new|\d+/edit|assets/(?:new|\d+/edit)|prices)'
    r'|/plan/(?:purchases/new|items(?:/\d+/(?:early-payment|edit|amount|delete|pay))?|from-transaction/\d+|suggestions/\d+/not-recurring)'
    r'|/reserves(?:/(?:emergency|\d+/(?:edit|allocate|complete|payments)))?'
    r'|/budget(?:/(?:tracking|suggestions|one-off|settings/full|carryover(?:/global|/reset/\d+)?|limit/\d+|rule/\d+|percentage/\d+|bulk|ceiling|fill|setup|raise|move))?'
    r'|/deposits/\d+/(?:purchase|certificates/\d+/(?:terms|redeem|interest/match-all|interest/[^/]{1,10}/(?:confirm|remove))|interest/match-all|legacy-cash|legacy)'
    r'|/gameya/\d+/(?:terms|instalment|past-instalments|payout)'
    r'|/reimbursements(?:/\d+/(?:receipts(?:/\d+/unlink)?|delete))?'
    r'|/zakat/(?:enabled|settings)'
    r'|/settings/(?:fx-rate|financial-health-limit|liquidation-factor/\d+)'
    r'|/setup/salary|/payday/(?:apply|enable)'
    r')\Z')
_FORM = re.compile(r'<form\b[^>]*>', re.IGNORECASE)
_METHOD = re.compile(r'\bmethod\s*=\s*["\']post["\']', re.IGNORECASE)
_ACTION = re.compile(r'\baction\s*=\s*(["\'])(.*?)\1', re.IGNORECASE)


class JournalFormGate:
    def __init__(self, app, device, *, session_token=None, synchronize=None, channel=None, pairing=None, sms_source=None):
        self.app, self.device = app, device
        self.mutex = asyncio.Lock()
        self.prefix = '/edit-journal'
        self.token = session_token or secrets.token_urlsafe(32)
        from lightning.sync.journal.read_views import install
        install(device.c)
        from lightning.ui.journal import create_journal_app
        self.journal = create_journal_app(device, session_token=self.token, synchronize=synchronize,
            channel=channel, pairing=pairing, sms_source=sms_source, prefix=self.prefix, finance_url='/')

    async def _buffer(self, scope, receive):
        messages, size = [], 0
        async def collect(message):
            nonlocal size
            size += len(message.get('body', b''))
            if size > 8 * 1024 * 1024:
                raise JournalError('This journal page is too large')
            messages.append(message)
        # Buffer plain HTML; a compressed response cannot safely receive the
        # per-form token. Other app middleware still supplies security headers.
        scope = dict(scope, headers=[(key, value) for key, value in scope['headers'] if key.lower() != b'accept-encoding'])
        await self.app(scope, receive, collect)
        return messages

    @staticmethod
    def _response(messages):
        start = next(message for message in messages if message['type'] == 'http.response.start')
        body = b''.join(message.get('body', b'') for message in messages if message['type'] == 'http.response.body')
        return start, body

    def _with_tokens(self, scope, start, body, *, basis_key=None):
        if not any(key.lower() == b'content-type' and b'text/html' in value for key, value in start.get('headers', [])):
            return start, body
        text = body.decode('utf-8')
        if '<head>' in text:
            text = text.replace('<head>', '<head><meta name="journal-root" content="'+self.prefix+'">'
                                '<script src="/static/journal.js" defer></script>', 1)
        eligible = []
        for match in _FORM.finditer(text):
            opening = match.group()
            action = _ACTION.search(opening)
            path = urlsplit(urljoin('http://localhost'+scope['path'], unescape(action[2]) if action else scope['path'])).path
            if _METHOD.search(opening) and FINANCIAL_WRITES.fullmatch(path):
                eligible.append(path)
        if eligible and basis_key is None:
            from lightning.sync.journal.form_basis import capture
            basis_key = capture(self.device.store)
        if eligible:
            with self.device.store.db.transaction():
                def insert(match):
                    opening = match.group()
                    action = _ACTION.search(opening)
                    path = urlsplit(urljoin('http://localhost'+scope['path'], unescape(action[2]) if action else scope['path'])).path
                    if not _METHOD.search(opening) or not FINANCIAL_WRITES.fullmatch(path):
                        return opening
                    token = issue_form(self.device.store, path, basis_key=basis_key)
                    return opening + f'<input type="hidden" name="__journal_form" value="{token}">'
                text = _FORM.sub(insert, text)
        body = text.encode('utf-8')
        start = dict(start, headers=[(key, value) for key, value in start.get('headers', []) if key.lower() != b'content-length']
                     + [(b'content-length', str(len(body)).encode())])
        cookie = Response()
        cookie.set_cookie('journal_session', self.token, path=self.prefix, httponly=True, samesite='strict')
        start['headers'].extend((key, value) for key, value in cookie.raw_headers if key == b'set-cookie')
        return start, body

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path', '').startswith('/static/'):
            return await self.app(scope, receive, send)
        async with self.mutex:
            if self.app.state.container is not self.device.c or self.device.c.db.closed:
                return await PlainTextResponse('The profile changed. Unlock it again before continuing.', 409)(scope, receive, send)
            if scope['path'] == self.prefix or scope['path'].startswith(self.prefix+'/'):
                inner = dict(scope, path=scope['path'][len(self.prefix):] or '/',
                             raw_path=scope.get('raw_path', scope['path'].encode())[len(self.prefix):] or b'/')
                return await self.journal(inner, receive, send)
            if scope['method'] not in ('GET', 'HEAD'):
                if scope['method'] != 'POST' or not FINANCIAL_WRITES.fullmatch(scope['path']):
                    return await PlainTextResponse('This screen is not ready for journal profiles. Nothing was saved.', 409)(scope, receive, send)
                return await self._post(scope, receive, send)
            from lightning.sync.journal.read_views import confirmed_reads
            for attempt in range(2):
                before = dict(config=dict(self.device.store.config), cursor=self.device.store.cursor())
                with confirmed_reads(self.device.c.db):
                    messages = await self._buffer(scope, body_receiver(b''))
                after = dict(config=dict(self.device.store.config), cursor=self.device.store.cursor())
                if after == before:
                    break
            else:
                return await PlainTextResponse('The ledger is catching up. Open this screen again.', 409)(scope, receive, send)
            start, body = self._response(messages)
            if scope['method'] == 'GET' and start['status'] == 200:
                start, body = self._with_tokens(scope, start, body)
                await send(start)
                return await send(dict(type='http.response.body', body=body))
            for message in messages:
                await send(message)

    async def _post(self, scope, receive, send):
        request = Request(scope, receive)
        store = self.device.store
        original = self.app.state.container
        try:
            chunks = bytearray()
            async for chunk in request.stream():
                if len(chunks) + len(chunk) > 512 * 1024:
                    raise JournalError('This form is too large')
                chunks.extend(chunk)
            body = bytes(chunks)
            parsed = Request(scope, body_receiver(body))
            async with parsed.form(max_files=0, max_fields=2000) as form:
                tokens = form.getlist('__journal_form')
                if len(tokens) != 1 or not isinstance(tokens[0], str):
                    raise JournalError('This form expired; open it again')
                values = {}
                for key, value in form.multi_items():
                    if not isinstance(value, str):
                        raise JournalError('This form cannot contain files')
                    values.setdefault(key, []).append(value)
                request_hash = digest(dict(path=scope['path'], query=scope.get('query_string', b'').decode('ascii'), fields=values))
                submission = (tokens[0], scope['path'], request_hash)
            prior = prior_submission(store, *submission)
            if prior is None:
                basis_key = submission_basis(store, tokens[0], scope['path'])
                with FormCapture(store, basis_key=basis_key) as capture:
                    self.app.state.container = capture.container
                    messages = await self._buffer(scope, body_receiver(body))
                    if self.app.state.container is not capture.container:
                        raise JournalError('This form tried to replace the active profile')
                    start, rendered = self._response(messages)
                    if start['status'] >= 400:
                        start, rendered = self._with_tokens(scope, start, rendered, basis_key=basis_key)
                        await send(start)
                        await send(dict(type='http.response.body', body=rendered))
                        return
                    wire = capture.finish(self.device.identity.sign, submission=submission)
                    if wire is None:
                        for message in messages:
                            await send(message)
                        return
            # Do not return a shadow transaction's ID/ref or a message claiming
            # confirmation. The ordinary register continues reading confirmed
            # money until the home sends its durable decision.
            response = RedirectResponse(self.prefix+'/?' + urlencode(dict(msg='Saved on this device. Waiting for confirmation.')), 303)
            response.set_cookie('journal_session', self.token, path=self.prefix, httponly=True, samesite='strict')
            return await response(scope, receive, send)
        except (JournalError, LightningError, ValueError) as error:
            return await PlainTextResponse(str(error), 409)(scope, receive, send)
        finally:
            self.app.state.container = original
