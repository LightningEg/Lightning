"""Locked profile-picker routes for bringing an existing journal ledger to this device."""
from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from lightning.runtime.journal_enrollment import NewJournalReplica
from lightning.runtime.paths import create_profile
from lightning.sync.journal.codec import JournalError, digest, unpack
from lightning.ui.journal_enrollment_i18n import error_text, strings

_BASE = "/profiles/journal/join"
_views = Jinja2Templates(directory=str(Path(__file__).parents[1] / "ui" / "templates"))


def journal_enrollment_router(session) -> APIRouter:
    """Routes for first-replica enrollment, separated from profile unlock and ordinary device pairing."""
    router = APIRouter()

    def require_locked():
        if session.container is not None or session.paths is not None:
            raise JournalError("Lock the open profile before joining another device.")

    def active(*, restore=True):
        value = getattr(session, "enrollment", None)
        if value is not None:
            try:
                if not (value.root / "complete.json").exists():
                    return value
            except OSError:
                return value
            session.enrollment = None
        if not restore:
            return None
        root = Path(session.root)
        if root.is_symlink() or not root.is_dir():
            return None
        candidates = []
        try:
            children = tuple(root.iterdir())
        except OSError:
            return None
        for child in children:
            if child.is_symlink() or not child.is_dir():
                continue
            marker = child / "journal-enrollment-root.json"
            complete = child / "complete.json"
            if marker.is_symlink() or not marker.is_file() or complete.exists():
                continue
            state = child / "enrollment.json"
            try:
                modified = state.stat().st_mtime_ns if state.is_file() else marker.stat().st_mtime_ns
                candidates.append((modified, child))
            except OSError:
                continue
        for _modified, child in sorted(candidates, reverse=True):
            try:
                value = NewJournalReplica(child, child.name)
            except (JournalError, OSError, ValueError):
                continue
            session.enrollment = value
            return value
        return None

    async def form(request: Request):
        data = await request.form(max_files=0, max_fields=20)
        expected = str(getattr(session, "csrf", ""))
        provided = str(data.get("csrf", ""))
        if not expected or not secrets.compare_digest(expected, provided):
            raise JournalError("This form expired. Reload and try again.")
        require_locked()
        return data

    def render(request: Request, *, error="", notice="", notice_key="", status=200, name=""):
        locale = request.cookies.get("lightning_ui_locale", "en")
        locale = locale if locale in {"en", "ar"} else "en"
        enrollment = active()
        state = enrollment.state() if enrollment is not None else None
        stage = state.get("stage", "find") if state else ("find" if enrollment is not None else "name")
        if request.query_params.get("status") == "download":
            notice_key = "download_more"
        elif request.query_params.get("status") == "cancelled":
            notice_key = "cancelled"
        if notice_key:
            notice = strings(locale).get(notice_key, notice)
        found = []
        if enrollment is not None:
            found = [dict(id=identifier, name=candidate["name"], number_match=unpack(candidate["offer"].encode())["body"].get("method") == "number-match")
                     for identifier, candidate in enrollment.candidates.items()]
        context = dict(request=request, locale=locale, texts=strings(locale), csrf=session.csrf,
                       error=error_text(error, locale) if error else "", notice=notice,
                       stage=stage, state=state or {}, candidates=found, name=name, pairing_version=digest(found),
                       on_phone=bool(getattr(request.state, "phone", False)))
        response = _views.TemplateResponse(request=request, name="journal/journal_enrollment.html",
                                           context=context, status_code=status)
        return response

    def locked_redirect():
        return RedirectResponse("/profiles", status_code=303)

    @router.get(_BASE, response_class=HTMLResponse)
    async def page(request: Request):
        try:
            require_locked()
        except JournalError:
            return locked_redirect()
        return render(request)

    @router.post(_BASE, response_class=HTMLResponse)
    async def start(request: Request):
        name = ""
        try:
            data = await form(request)
            name = str(data.get("name", "")).strip()
            if not name or len(name) > 200:
                raise JournalError("Enter a profile name of 1–200 characters.")
            enrollment = active()
            if enrollment is None:
                root = Path(session.root)
                if root.is_symlink():
                    raise JournalError("Invalid profile folder.")
                root.mkdir(mode=0o700, parents=True, exist_ok=True)
                paths = create_profile(name, root=root)
                paths.data_dir.mkdir(mode=0o700, exist_ok=False)
                enrollment = NewJournalReplica(paths.data_dir, paths.profile.name)
                session.enrollment = enrollment
            return RedirectResponse(_BASE, status_code=303)
        except (JournalError, OSError, ValueError) as exc:
            if session.container is not None or session.paths is not None:
                return locked_redirect()
            return render(request, error=str(exc), status=400, name=name)

    async def post_action(request: Request, action):
        try:
            data = await form(request)
            enrollment = active()
            if enrollment is None:
                raise JournalError("Start an enrollment first.")
            result = await action(enrollment, data)
            if result == "complete":
                session.enrollment = None
                return RedirectResponse("/profiles", status_code=303)
            if result == "cancelled":
                return RedirectResponse(_BASE + "?status=cancelled", status_code=303)
            if result == "more":
                return RedirectResponse(_BASE + "?status=download", status_code=303)
            return RedirectResponse(_BASE, status_code=303)
        except (JournalError, OSError, ValueError, TimeoutError) as exc:
            if session.container is not None or session.paths is not None:
                return locked_redirect()
            message = str(exc)
            if "has not been approved" in message:
                return render(request, notice_key="home_approval")
            return render(request, error=message, status=400)

    @router.post(_BASE + "/poll")
    async def poll(request: Request):
        try:
            await form(request)
            enrollment = active()
            if enrollment is None or enrollment.state() is not None:
                return JSONResponse(dict(version=digest([])))
            found = await enrollment.find()
            return JSONResponse(dict(version=digest(found)))
        except (JournalError, OSError, ValueError, TimeoutError):
            return JSONResponse(dict(error=True), status_code=400)

    @router.post(_BASE + "/find", response_class=HTMLResponse)
    async def find(request: Request):
        async def operation(enrollment, _data):
            await enrollment.find()
        return await post_action(request, operation)

    @router.post(_BASE + "/join", response_class=HTMLResponse)
    async def join(request: Request):
        async def operation(enrollment, data):
            await enrollment.join(str(data.get("candidate", "")), str(data.get("code", "")))
        return await post_action(request, operation)

    @router.post(_BASE + "/compare", response_class=HTMLResponse)
    async def compare(request: Request):
        async def operation(enrollment, data):
            enrollment.compare(str(data.get("digits", "")))
        return await post_action(request, operation)

    @router.post(_BASE + "/prove", response_class=HTMLResponse)
    async def prove(request: Request):
        async def operation(enrollment, data):
            password = str(data.get("password", ""))
            if len(password.encode("utf-8")) > 4096:
                raise JournalError("Type the profile password.")
            await enrollment.prove(password)
        return await post_action(request, operation)

    @router.post(_BASE + "/finish", response_class=HTMLResponse)
    async def finish(request: Request):
        async def operation(enrollment, data):
            password = str(data.get("password", ""))
            if len(password.encode("utf-8")) > 4096:
                raise JournalError("Type the profile password.")
            if await enrollment.finish(password, budget=8):
                return "complete"
            return "more"
        return await post_action(request, operation)

    @router.post(_BASE + "/cancel", response_class=HTMLResponse)
    async def cancel(request: Request):
        async def operation(enrollment, _data):
            state = enrollment.state()
            if state is not None and state.get("stage") not in {"compare", "password"}:
                raise JournalError("The password proof has already been sent. Ask the home device to stop this pairing.")
            enrollment.cancel()
            return "cancelled"
        return await post_action(request, operation)

    return router
