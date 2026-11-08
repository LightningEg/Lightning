"""The phone router: owns every URL a migrated slot serves, and answers before the old shared routes do."""
from __future__ import annotations

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.routing import APIRoute
from starlette.routing import Match

from lightning.ui.web import container, render

PHONE_TEMPLATES = "phone/"


def _plain(*allowed: str) -> type[APIRoute]:
    """A route class that matches a URL only when its query holds nothing but ``allowed`` keys. A slot's bare URL is
    the new screen; the same path with a filter or another page's parameters still reaches the older shared route,
    so no link breaks while the old screens are removed (3AY11)."""
    class PlainRoute(APIRoute):
        def matches(self, scope):
            match, child = super().matches(scope)
            if match == Match.FULL:
                keys = {part.split("=", 1)[0] for part in scope.get("query_string", b"").decode().split("&") if part}
                if keys - set(allowed):
                    return Match.NONE, {}
            return match, child
    return PlainRoute


def phone_router() -> APIRouter:
    """Every phone-owned URL. Home is served at /home while the old Overview keeps /; the slot URLs switch over
    together with the tab bar (3AY10)."""
    router = APIRouter()
    slots = APIRouter(route_class=_plain())              # a bare slot URL: no query at all
    months = APIRouter(route_class=_plain("month"))      # Budget keeps its month stepper

    @router.get("/home")
    @slots.get("/")
    async def home(request: Request):
        from lightning.core.dates import today
        from lightning.ui.phone.screens import home as screen
        return render_phone(request, "phone/home.html", screen=screen.build(container(request), today()))

    @router.get("/budget/flexible")
    @months.get("/budget")
    async def budget_flexible(request: Request):
        """Budget, flexible first (3AY9). Served beside the old Budget until the tab bar switches (3AY10)."""
        from lightning.core.dates import today
        from lightning.ui.phone.screens import budget as screen
        return render_phone(request, "phone/budget_flexible.html",
                            screen=screen.build(container(request), today(), request.query_params.get("month", "")))

    @slots.get("/more")
    @slots.get("/accounts")
    async def to_money():
        """The old More and the account list are Money's job now (3AY10)."""
        return RedirectResponse("/money", status_code=307)

    @slots.get("/transactions")
    async def to_activity():
        return RedirectResponse("/activity", status_code=307)

    @router.get("/money")
    async def money(request: Request):
        """Money (3AY10): net worth, the balances, Coming up and one row for each of the rest. Served beside More until
        the tab bar switches."""
        from lightning.core.dates import today
        from lightning.ui.phone.screens import money as screen
        return render_phone(request, "phone/money.html", screen=screen.build(container(request), today()))

    @router.get("/activity")
    async def activity(request: Request):
        from lightning.core.dates import today
        from lightning.ui.phone.screens import activity as screen
        asked = request.query_params
        index = int(asked.get("i", "0")) if asked.get("i", "0").isdigit() else 0
        return render_phone(request, "phone/activity_home.html", screen=screen.build(
            container(request), today(), asked.get("tab", "all"), asked.get("month", ""), index))

    @router.post("/activity/not-now")
    async def activity_not_now(request: Request):
        """Not now on a review card: it leaves the queue until tomorrow and nothing is posted or changed (3AY8)."""
        from datetime import timedelta
        from lightning.core.dates import today
        from lightning.core.errors import LightningError
        from lightning.ui.web import redirect
        from lightning.workflows.review import ReviewInbox
        form = await request.form()
        day = today()
        try:
            ReviewInbox(container(request)).decide(str(form.get("identity", "")), "snoozed", day,
                                                   (day + timedelta(days=1)).isoformat())
        except LightningError as exc:
            return redirect("/activity?tab=review", exc.message)
        return redirect("/activity?tab=review")

    @router.get("/add/bills")
    async def add_bills(request: Request):
        """Pay a bill, from the Add sheet (3AY7): what is due, earliest first; a row opens that bill's pay sheet."""
        from lightning.core.dates import today
        from lightning.planning import bill_state
        c = container(request)
        back = request.query_params.get("return_to", "")
        back = back if back.startswith("/") and not back.startswith("//") else "/home"
        rows = bill_state.open_bills(c.planning, today(), bill_state.SOON_DAYS)
        return render_phone(request, "phone/add_bills.html", rows=rows, back=back)

    router.include_router(slots)
    router.include_router(months)
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
