"""The phone router: owns every URL a migrated slot serves, and answers before the old shared routes do."""
from __future__ import annotations

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse

from lightning.ui.web import container, render

PHONE_TEMPLATES = "phone/"


def phone_router() -> APIRouter:
    """Every phone-owned URL. Home is served at /home while the old Overview keeps /; the slot URLs switch over
    together with the tab bar (3AY10)."""
    router = APIRouter()

    @router.get("/home")
    async def home(request: Request):
        from lightning.core.dates import today
        from lightning.ui.phone.screens import home as screen
        return render_phone(request, "phone/home.html", screen=screen.build(container(request), today()))

    return router


def render_phone(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
    """Render a phone screen. The template must live under ``templates/phone/``: a phone route never draws a PC
    template, however a PC page of the same name looks (the "no PC fallback" rule of 3AY4)."""
    if not name.startswith(PHONE_TEMPLATES) or ".." in name:
        raise ValueError(f"A phone screen renders only templates/phone/, not {name!r}")
    request.state.phone = True
    return render(request, name, status_code, **context)


def mount_phone(app: FastAPI, router: APIRouter | None = None) -> None:
    """Add the phone's routes at the front of the app's routing table, so a phone-owned URL wins over an older
    shared route of the same path. Called only by ``profile_app(..., phone=True)``."""
    existing = list(app.router.routes)
    app.include_router(router if router is not None else phone_router())
    added = [route for route in app.router.routes if route not in existing]
    app.router.routes[:] = added + existing
