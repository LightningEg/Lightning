"""Explicit journal conversion from the normal locked/unlocked profile chooser."""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from lightning.runtime.session import ProfileError
from lightning.sync.journal.codec import JournalError

_views = Jinja2Templates(directory=str(Path(__file__).parents[1] / "ui" / "templates"))


def journal_setup_router(session, devices):
    router = APIRouter()

    def render(request, *, error="", selected=""):
        locale = request.cookies.get("lightning_ui_locale", "en")
        return _views.TemplateResponse(request=request, name="journal/journal_setup.html", context=dict(
            locale=locale if locale in ("en", "ar") else "en", csrf=session.csrf,
            selected=selected, error=error, name=session.name))

    @router.get("/profiles/journal/setup")
    async def setup(request: Request):
        if session.journal is not None:
            return RedirectResponse("/journal/devices", 303)
        return render(request, selected=request.query_params.get("db", ""))

    @router.post("/profiles/journal/setup")
    async def convert(request: Request):
        form = await request.form(max_files=0, max_fields=10)
        selected = str(form.get("db", ""))
        try:
            if form.get("confirmed") != "yes":
                raise ProfileError("Confirm that you saved your recovery key before enabling device editing.")
            paths = session.paths
            if paths is None:
                from .paths import resolve_profile
                paths = resolve_profile(db_path=selected)
            state = devices.lending_state(paths)
            if state in ("missing", "damaged"):
                raise ProfileError("Repair the lending record before changing synchronization.")
            node = devices.home_node(paths) if state == "ok" else None
            legacy_state = str(node.model.state) if node is not None else "AT_HOME"
            session.enable_journal(str(form.get("password", "")), str(form.get("recovery", "")),
                str(form.get("answer", "")), selected=selected, legacy_state=legacy_state,
                retain_stranded=form.get("retain_stranded") == "yes")
            request.app.state.container = session.container
            return RedirectResponse("/journal/devices", 303)
        except (ProfileError, JournalError, OSError, ValueError) as error:
            return render(request, error=str(error), selected=selected)

    return router
