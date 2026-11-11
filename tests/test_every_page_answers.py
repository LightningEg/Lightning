"""IT-1Y2: every GET page of Mohab's sample year answers on the PC and on the phone, none with a server error."""
import re

import pytest
from fastapi.testclient import TestClient

from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app


def _routes(app) -> list[str]:
    found: list[str] = []

    def walk(routes, prefix=""):
        for r in routes:
            if hasattr(r, "original_router"):
                o = r.original_router
                own = getattr(o, "prefix", "") or ""
                nested = any(getattr(x, "path", "").startswith(own or "~") for x in o.routes)
                walk(o.routes, prefix + ("" if nested else own))
            elif hasattr(r, "routes") and not hasattr(r, "methods"):
                walk(r.routes, prefix + getattr(r, "path", ""))
            elif hasattr(r, "methods") and "GET" in (r.methods or ()):
                found.append(prefix + r.path)

    walk(app.routes)
    return sorted(set(found))


def _address(path: str) -> str:
    path = re.sub(r"\{[^}:]+:int\}", "1", path)
    return re.sub(r"\{[^}]+\}", "x", path)


def _failures(app) -> list[str]:
    client = TestClient(app, base_url="http://127.0.0.1", follow_redirects=False, raise_server_exceptions=False)
    bad = []
    for path in _routes(app):
        if path.startswith(("/static", "/docs", "/openapi", "/redoc")):
            continue
        status = client.get(_address(path)).status_code
        if status >= 500:
            bad.append(f"{path} -> {status}")
    return bad


def test_every_pc_page_answers(c):
    load_mohab_2026(c)
    bad = _failures(create_app(c))
    assert not bad, "\n".join(bad)


def test_every_phone_page_answers(c):
    from lightning.ui.phone.router import mount_phone
    load_mohab_2026(c)
    app = create_app(c)
    mount_phone(app)
    inner = app

    async def phone_app(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        return await inner(scope, receive, send)

    phone_app.routes = app.routes
    bad = _failures(phone_app)
    assert not bad, "\n".join(bad)
