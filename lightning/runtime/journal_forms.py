"""Buffered native-register adapter for explicit experimental journal runtimes.

Only exercised register routes are enabled. Other writes fail before dispatch;
native cutover must wait for every remaining financial/capture route's adapter.
"""
from __future__ import annotations

import asyncio
from html import unescape
import re
from urllib.parse import urljoin, urlsplit, urlencode

from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse

from lightning.core.errors import LightningError
from lightning.sync.journal.codec import JournalError, digest
from lightning.sync.journal.forms import FormCapture, issue_form, prior_submission
from .http import body_receiver


REGISTER_WRITES = re.compile(r'/(?:transactions/register(?:/\d+)?|accounts/\d+/register(?:/\d+)?)\Z')
_FORM = re.compile(r'<form\b[^>]*>', re.IGNORECASE)
_METHOD = re.compile(r'\bmethod\s*=\s*["\']post["\']', re.IGNORECASE)
_ACTION = re.compile(r'\baction\s*=\s*(["\'])(.*?)\1', re.IGNORECASE)


class JournalFormGate:
    def __init__(self, app, device):
        self.app, self.device = app, device
        self.mutex = asyncio.Lock()

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

    def _with_tokens(self, scope, start, body):
        if not any(key.lower() == b'content-type' and b'text/html' in value for key, value in start.get('headers', [])):
            return start, body
        text = body.decode('utf-8')
        with self.device.store.db.transaction():
            def insert(match):
                opening = match.group()
                action = _ACTION.search(opening)
                path = urlsplit(urljoin('http://localhost'+scope['path'], unescape(action[2]) if action else scope['path'])).path
                if not _METHOD.search(opening) or not REGISTER_WRITES.fullmatch(path):
                    return opening
                token = issue_form(self.device.store, path)
                return opening + f'<input type="hidden" name="__journal_form" value="{token}">'
            text = _FORM.sub(insert, text)
        body = text.encode('utf-8')
        start = dict(start, headers=[(key, value) for key, value in start.get('headers', []) if key.lower() != b'content-length']
                     + [(b'content-length', str(len(body)).encode())])
        return start, body

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path', '').startswith('/static/'):
            return await self.app(scope, receive, send)
        async with self.mutex:
            if scope['method'] not in ('GET', 'HEAD'):
                if scope['method'] != 'POST' or not REGISTER_WRITES.fullmatch(scope['path']):
                    return await PlainTextResponse('This screen is not ready for journal profiles. Nothing was saved.', 409)(scope, receive, send)
                return await self._post(scope, receive, send)
            messages = await self._buffer(scope, receive)
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
                with FormCapture(store) as capture:
                    self.app.state.container = capture.container
                    messages = await self._buffer(scope, body_receiver(body))
                    if self.app.state.container is not capture.container:
                        raise JournalError('This form tried to replace the active profile')
                    start, rendered = self._response(messages)
                    if start['status'] >= 400:
                        start, rendered = self._with_tokens(scope, start, rendered)
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
            response = RedirectResponse('/transactions?' + urlencode(dict(msg='Saved on this device. Waiting for confirmation.')), 303)
            return await response(scope, receive, send)
        except (JournalError, LightningError, ValueError) as error:
            return await PlainTextResponse(str(error), 409)(scope, receive, send)
        finally:
            self.app.state.container = original
