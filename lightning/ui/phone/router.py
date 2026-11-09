"""The phone router: owns every URL a migrated slot serves, and answers before the old shared routes do."""
from __future__ import annotations

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.routing import APIRoute
from starlette.routing import Match

from lightning.ui.web import container, render

PHONE_TEMPLATES = "phone/"

# Pages that are only practical on a PC (3AY4 d): on the phone they open "This is on your PC" instead of PC markup
# squeezed into one column. Empty on purpose (owner, 2026-11-08): Data checks and price files still work on the phone
# today, so a path joins this list only when its phone version exists or the owner decides it is PC-only.
BEST_ON_PC: tuple[str, ...] = ()


def _plain(*allowed: str, when=None) -> type[APIRoute]:
    """A route class that matches a URL only when its query holds nothing but ``allowed`` keys. A slot's bare URL is
    the new screen; the same path with a filter or another page's parameters still reaches the older shared route,
    so no link breaks while the old screens are removed (3AY11). ``when`` (a request test) also lets the older route
    answer: the empty profile's welcome page, where currencies, the first account and the samples are set up."""
    class PlainRoute(APIRoute):
        def matches(self, scope):
            match, child = super().matches(scope)
            if match == Match.FULL:
                keys = {part.split("=", 1)[0] for part in scope.get("query_string", b"").decode().split("&") if part}
                if keys - set(allowed):
                    return Match.NONE, {}
                if when is not None:
                    try:
                        if not when(Request(scope)):
                            return Match.NONE, {}
                    except Exception:  # no profile open yet: the older route answers (and says so)
                        return Match.NONE, {}
            return match, child
    return PlainRoute


def _read_new_sms(request: Request, c) -> None:
    """New bank messages join the review before To do is counted, as the old Overview did on every visit. Never breaks
    the page that asked; a read-only session reads nothing."""
    source = getattr(request.app.state, "sms_source", None)
    if source is None or getattr(request.state, "read_only", False):
        return
    try:
        c.sms_imports.read_source(source)
    except Exception:  # noqa: BLE001 - the phone's inbox is a convenience: the page still opens
        pass


def phone_router() -> APIRouter:
    """Every phone-owned URL. Home is served at /home while the old Overview keeps /; the slot URLs switch over
    together with the tab bar (3AY10)."""
    router = APIRouter()
    started = APIRouter(route_class=_plain(when=lambda request: bool(container(request).accounts.list())))
    slots = APIRouter(route_class=_plain())              # a bare slot URL: no query at all
    months = APIRouter(route_class=_plain("month"))      # Budget keeps its month stepper

    @router.get("/home")
    @started.get("/")
    async def home(request: Request):
        from lightning.core.dates import today
        from lightning.ui.phone.screens import home as screen
        c = container(request)
        _read_new_sms(request, c)
        return render_phone(request, "phone/home.html", screen=screen.build(c, today()))

    @router.get("/budget/flexible")
    @months.get("/budget")
    async def budget_flexible(request: Request):
        """Budget, flexible first (3AY9). Served beside the old Budget until the tab bar switches (3AY10)."""
        from lightning.core.dates import today
        from lightning.ui.phone.screens import budget as screen
        return render_phone(request, "phone/budget_flexible.html",
                            screen=screen.build(container(request), today(), request.query_params.get("month", "")))

    @router.get("/more")
    @slots.get("/accounts")
    async def to_money():
        """More is gone (3AY11): Money holds what it held. The account list is Money's Accounts page too (3AY10)."""
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

    @router.get("/pc")
    async def on_your_pc(request: Request):
        """This is on your PC: what a PC-only page is for, and the way back. ``?for=`` names the page asked for."""
        return render_phone(request, "phone/on_pc.html", asked=_on_pc_label(request.query_params.get("for") or request.url.path),
                            leave=_safe_back(request.query_params.get("return_to", "")))

    for path in BEST_ON_PC:  # a PC-only page answers its own address with the same page
        router.add_api_route(path, on_your_pc, methods=["GET"], include_in_schema=False)

    @router.get("/money/report")
    async def money_report(request: Request):
        """How did a period go? (the Overview's report, which Home no longer carries)"""
        from lightning.core.dates import today
        from lightning.ui.phone.screens import report as screen
        return render_phone(request, "phone/money_report.html",
                            screen=screen.build(container(request), today(), request.query_params.get("period", "month")))

    @router.get("/money/reviews")
    async def money_reviews(request: Request):
        """Reports and reviews (IV-11H): Report, Cash planning, Spending and the Weekly review behind Money's one row."""
        return render_phone(request, "phone/money_reviews.html")

    @router.get("/money/accounts")
    async def money_accounts(request: Request):
        from lightning.core.dates import today
        from lightning.ui.phone.screens import money as screen
        return render_phone(request, "phone/money_accounts.html", page=screen.accounts_page(container(request), today()))

    @router.get("/money/bills")
    async def money_bills(request: Request):
        from lightning.core.dates import today
        from lightning.ui.phone.screens import money as screen
        return render_phone(request, "phone/money_bills.html", page=screen.bills_page(container(request), today()))

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

    router.include_router(started)
    router.include_router(slots)
    router.include_router(months)
    return router


def _safe_back(value: str) -> str:
    return value if value.startswith("/") and not value.startswith("//") else "/money"


def _on_pc_label(path: str) -> str:
    """The plain name of a PC-only page for its message; unknown addresses say nothing specific."""
    names = {"/checks": "Data checks", "/investments/prices": "Price files"}
    return names.get(path.split("?")[0], "")


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
    app.state.phone_screens = True   # web.py's remembered period must not redirect Home or Budget away from them
    existing = list(app.router.routes)
    app.include_router(router if router is not None else phone_router())
    added = [route for route in app.router.routes if route not in existing]
    app.router.routes[:] = added + existing
