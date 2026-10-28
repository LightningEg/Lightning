"""Authenticated, bounded loopback transport shared by browser and window shells."""
from __future__ import annotations

import asyncio
import hmac
import secrets
import socket
import threading
import time
from dataclasses import dataclass, field
import re

import uvicorn
from starlette.formparsers import MultiPartParser
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse
from lightning.core.limits import (
    MAX_CSV_IMPORT_BYTES,
    MAX_CSV_MAPPING_REQUEST_BYTES,
    MAX_CSV_UPLOAD_REQUEST_BYTES,
    MAX_IMPORT_REVIEW_FIELDS,
    MAX_IMPORT_REVIEW_REQUEST_BYTES,
)

# Ordinary profile requests remain small. Bank-import routes get separate, still
# bounded allowances so an accepted CSV can reach review without being written
# to a plaintext temporary file.
MAX_BODY = 512 * 1024
MAX_IMPORT_FILE_BYTES = MAX_CSV_IMPORT_BYTES
MAX_IMPORT_UPLOAD_BODY = MAX_CSV_UPLOAD_REQUEST_BYTES
MAX_IMPORT_MAP_BODY = MAX_CSV_MAPPING_REQUEST_BYTES
MAX_IMPORT_CONFIRM_BODY = MAX_IMPORT_REVIEW_REQUEST_BYTES
MAX_IMPORT_CONFIRM_FIELDS = MAX_IMPORT_REVIEW_FIELDS
# A market price file (prices only, nothing personal) imported by hand: one zip, bounded.
MARKET_IMPORT_PATH = "/investments/prices/market/import"
MAX_MARKET_IMPORT_BODY = 40 * 1024 * 1024
# Many investment prices from one CSV (PC roadmap P6): one file, bounded like a statement upload.
PRICE_CSV_PATH = "/investments/prices/csv"


def request_body_limit(path: str, method: str = "POST") -> int:
    """Return the bounded request-body allowance for protected-profile routes."""
    if method != "POST":
        return MAX_BODY
    if re.fullmatch(r"/accounts/\d+/import", path):
        return MAX_IMPORT_UPLOAD_BODY
    if re.fullmatch(r"/accounts/\d+/import/map", path):
        return MAX_IMPORT_MAP_BODY
    if re.fullmatch(r"/accounts/\d+/import/\d+/confirm", path):
        return MAX_IMPORT_CONFIRM_BODY
    if path == MARKET_IMPORT_PATH:
        return MAX_MARKET_IMPORT_BODY
    if path == PRICE_CSV_PATH:
        return MAX_IMPORT_UPLOAD_BODY
    return MAX_BODY


def request_too_large_message(path: str) -> str:
    if re.fullmatch(r"/accounts/\d+/import(?:/map)?", path) or path == PRICE_CSV_PATH:
        return "CSV files must be 5 MB or smaller. Choose a smaller CSV and try again."
    if re.fullmatch(r"/accounts/\d+/import/\d+/confirm", path):
        return "This import review is too large to submit at once. Split the CSV into smaller files."
    return "This request is too large."


def configure_memory_only_import_uploads() -> None:
    """Keep Starlette's spooled upload below disk-rollover size for guarded CSVs.

    The profile Guard bounds the statement upload route to 5 MB plus a small
    multipart envelope, and rejects files on all other routes but the market
    price file's. Raising this threshold above the statement route's complete
    body size keeps statement bytes in memory instead of allowing
    SpooledTemporaryFile to roll them to disk. A market file larger than that
    may roll to disk: it holds public prices, nothing personal.
    """
    MultiPartParser.spool_max_size = MAX_IMPORT_UPLOAD_BODY + 1


@dataclass
class Credentials:
    origin: str
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    launch_code: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    cookie_name: str = field(default_factory=lambda: "lightning_" + secrets.token_hex(12))
    nonce: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    expires: float = field(default_factory=lambda: time.monotonic() + 120)
    used: bool = False


def equal(value: str, expected: str) -> bool:
    return hmac.compare_digest(value.encode("utf-8"), expected.encode("utf-8"))


def body_receiver(body: bytes):
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        # The inner response owns cancellation of any disconnect listener.
        await asyncio.Event().wait()

    return receive


def _append_bounded_chunk(chunks: bytearray, incoming: bytes, limit: int) -> bool:
    """Append only when the combined request body remains within its cap."""
    if len(chunks) + len(incoming) > limit:
        return False
    chunks.extend(incoming)
    return True


class Guard:
    def __init__(self, app, credentials: Credentials):
        self.app, self.credentials = app, credentials

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        cfg = self.credentials
        request = Request(scope)
        scope.setdefault("state", {})["csp_nonce"] = cfg.nonce

        async def secured_send(message):
            if message["type"] == "http.response.start":
                csp = ("default-src 'none'; script-src 'self' 'nonce-" + cfg.nonce + "'; "
                       "script-src-attr 'none'; style-src 'self' 'unsafe-inline'; "
                       "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
                       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() not in
                           (b"cache-control", b"content-security-policy", b"referrer-policy")]
                # no-referrer on ordinary HTML makes Chromium send Origin:null
                # for native form POSTs. Keep exact-origin checks and use
                # same-origin, which still suppresses all external referrers.
                referrer = b"no-referrer" if request.url.path == "/__launch" else b"same-origin"
                # Pages are never stored. The app's own CSS, JS, fonts and images hold no user data and
                # each launch gets a new random port (a new origin), so the window may keep them for the
                # session instead of fetching and parsing them again on every click.
                static = request.url.path.startswith("/static/") and message.get("status") == 200
                cache = b"private, max-age=86400" if static else b"no-store"
                headers.extend([(b"cache-control", cache), (b"referrer-policy", referrer),
                                (b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
                                (b"content-security-policy", csp.encode("ascii"))])
                message = {**message, "headers": headers}
            await send(message)

        response = None
        origin = request.headers.get("origin")
        site = request.headers.get("sec-fetch-site")
        if request.headers.get("host") != cfg.origin.removeprefix("http://"):
            response = PlainTextResponse("Bad host", 400)
        elif origin is not None and origin != cfg.origin:
            response = PlainTextResponse("Forbidden origin", 403)
        elif site not in (None, "none", "same-origin"):
            response = PlainTextResponse("Forbidden site", 403)
        elif request.url.path == "/__launch":
            if request.method != "GET" or cfg.used or time.monotonic() >= cfg.expires or not equal(
                    request.query_params.get("code", ""), cfg.launch_code):
                response = PlainTextResponse("Launch link expired. Restart Lightning.", 403)
            else:
                cfg.used = True
                response = RedirectResponse("/profiles", 303)
                response.set_cookie(cfg.cookie_name, cfg.token, httponly=True, samesite="strict")
        elif not equal(request.cookies.get(cfg.cookie_name, ""), cfg.token):
            response = PlainTextResponse("Forbidden", 403)
        elif request.method not in ("GET", "HEAD") and origin != cfg.origin:
            response = PlainTextResponse("A same-origin form submission is required.", 403)
        if response is not None:
            return await response(scope, receive, secured_send)
        limit = request_body_limit(request.url.path, request.method)
        too_large = request_too_large_message(request.url.path)
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdecimal() and int(content_length) > limit:
            return await PlainTextResponse(too_large, 413)(scope, receive, secured_send)
        try:
            chunks = bytearray()
            async with asyncio.timeout(15):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    if not _append_bounded_chunk(chunks, message.get("body", b""), limit):
                        response = PlainTextResponse(too_large, 413)
                        return await response(scope, receive, secured_send)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            return await PlainTextResponse("Request timed out", 408)(scope, receive, secured_send)
        body = bytes(chunks)
        del chunks
        scope["state"]["request_body"] = body
        await self.app(scope, body_receiver(body), secured_send)


class Host:
    """Pre-bind before choosing an origin; ASGI thread owns the complete session."""

    def __init__(self, factory):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            self.socket.bind(("127.0.0.1", 0))
            self.origin = f"http://127.0.0.1:{self.socket.getsockname()[1]}"
            self.credentials = Credentials(self.origin)
            self.app = factory(self.credentials)
            self.server = uvicorn.Server(uvicorn.Config(
                self.app, log_config=None, access_log=False, log_level="critical",
                http="h11", loop="asyncio", ws="none", lifespan="on",
                server_header=False, date_header=False, timeout_graceful_shutdown=5,
            ))
            self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [self.socket]},
                                           name="lightning-profile-owner", daemon=True)
        except BaseException:
            self.socket.close()
            raise

    @property
    def launch_url(self):
        return f"{self.origin}/__launch?code={self.credentials.launch_code}"

    def start(self):
        self.thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                self.stop()
                raise RuntimeError("The local server could not start")
            time.sleep(.02)
        return self

    def stop(self):
        self.server.should_exit = True
        if self.thread.ident is not None:
            self.thread.join(10)
        if self.thread.is_alive():
            raise RuntimeError("The profile server did not stop cleanly")
        self.socket.close()
