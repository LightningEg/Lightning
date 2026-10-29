"""Downloads on the phone (2F): Android's WebView saves nothing a page sends as an attachment, and most of Lightning's
downloads answer a POST, which a download listener cannot repeat. So on the phone the server hands each finished
file to the app (`FileBridge` in the Android app), which asks where to save it with the system's own "Save to"
screen, and the page goes back to where it was, saying so. On a PC nothing here runs."""
from __future__ import annotations

import logging
import re
from typing import Protocol
from urllib.parse import quote, urlsplit

LOG = logging.getLogger("lightning")
MAX_FILE_BYTES = 64 * 1024 * 1024  # an export is far smaller; anything larger is left to the page as it was
_NAME = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', re.IGNORECASE)


class FileSaver(Protocol):
    def offer(self, name: str, media_type: str, data: bytes) -> bool: ...  # True: the "Save to" screen is shown


def attachment_name(disposition: str) -> str | None:
    """The file name of an attachment, made safe for a file system; None for anything shown in the page."""
    if not disposition.lower().startswith("attachment"):
        return None
    found = _NAME.search(disposition)
    name = (found.group(1) if found else "").strip().replace("/", "-").replace("\\", "-")
    return name[:120] or "lightning-file"


def _back(headers: dict[bytes, bytes]) -> str:
    """The page the person was on (a path of this app), else Overview."""
    referer = headers.get(b"referer", b"").decode("latin-1")
    parts = urlsplit(referer)
    path = parts.path or "/"
    if not path.startswith("/") or path.startswith("//"):
        path = "/"
    query = "&".join(item for item in parts.query.split("&") if item and not item.startswith("msg="))
    return path + (f"?{query}" if query else "")


class PhoneSaves:
    """ASGI: an attachment becomes an offer to save it, then a way back to the page (or, for a page's own fetch,
    an empty answer with `X-Lightning-Offered`). If the app cannot take the file, the response goes out unchanged."""

    def __init__(self, app, saver: FileSaver):
        self.app, self.saver = app, saver

    @property
    def state(self):
        return self.app.state

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_headers = dict(scope.get("headers") or [])
        held: dict = {}
        body = bytearray()

        async def capture(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers") or [])
                name = attachment_name(headers.get(b"content-disposition", b"").decode("latin-1"))
                if name is None or message.get("status", 200) != 200:
                    return await send(message)
                held.update(start=message, name=name, media=headers.get(b"content-type", b"").decode("latin-1"))
                return None
            if "start" not in held:
                return await send(message)
            body.extend(message.get("body", b""))
            if len(body) > MAX_FILE_BYTES:
                await send(held.pop("start"))
                await send({"type": "http.response.body", "body": bytes(body), "more_body": message.get("more_body", False)})
                return None
            if not message.get("more_body", False):
                await self._deliver(held, bytes(body), request_headers, send)
            return None

        await self.app(scope, receive, capture)

    async def _deliver(self, held, data, request_headers, send):
        name = held["name"]
        try:
            offered = bool(self.saver.offer(name, held["media"].split(";")[0].strip() or "application/octet-stream", data))
        except Exception:  # the app could not take it: the page gets the file as before
            LOG.exception("The phone could not offer %s for saving", name)
            offered = False
        if not offered:
            await send(held["start"])
            await send({"type": "http.response.body", "body": data})
            return
        if request_headers.get(b"x-requested-with") == b"fetch":
            headers = [(b"x-lightning-offered", quote(name).encode()), (b"cache-control", b"no-store")]
            await send({"type": "http.response.start", "status": 204, "headers": headers})
        else:
            back = _back(request_headers)
            location = back + ("&" if "?" in back else "?") + "msg=" + quote(f"Choose where to save {name}.")
            await send({"type": "http.response.start", "status": 303,
                        "headers": [(b"location", location.encode()), (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": b""})
