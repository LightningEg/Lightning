"""Routes that expose the unlocked journal runtime inside the main app."""
from __future__ import annotations

import inspect
import secrets
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from lightning.sync.journal.codec import JournalError
from lightning.ui.journal_i18n import action_name, translate_journal

_views = Jinja2Templates(directory=str(Path(__file__).parents[1] / "ui" / "journal_views"))
_views.env.filters["tr"] = translate_journal


def journal_ui_router(session) -> APIRouter:
    """Build main-app journal routes for a ProfileSession-like lifecycle object.

    The host app supplies its already guarded session. The journal runtime is
    resolved per request so locking immediately removes access to its services.
    """
    router = APIRouter()

    def runtime():
        value = getattr(session, "journal", None)
        if value is None:
            raise JournalError("Unlock a journal profile first")
        return value

    async def read_form(request):
        data = await request.form(max_files=0, max_fields=40)
        expected = str(getattr(session, "token", ""))
        provided = str(data.get("__session", ""))
        if not expected or not secrets.compare_digest(expected, provided):
            raise JournalError("Open the form again before saving")
        return data

    def render(request, *, page="devices", message="", error=""):
        current = runtime()
        device = current.device
        pairing = current.pairing
        try:
            pairing_screen = pairing.screen() if pairing is not None else dict(enabled=False)
        except Exception:
            pairing_screen = dict(enabled=False)
        from lightning.ui.journal import command_status_rows, command_values
        phone = bool(getattr(request.state, "phone", False))
        trust = getattr(current, "trust", None)
        try:
            trust_state = trust.state() if trust is not None else dict(available=False)
        except Exception:
            trust_state = dict(available=False, phase="damaged")
        container = getattr(session, "container", None)
        locale = container.settings.get("locale") if container is not None else "en"
        locale = locale if locale in {"en", "ar"} else "en"
        reviews = []
        if device.home:
            for item in device.review_items():
                proposal = item["proposed"]
                is_command = proposal["kind"].startswith("command.")
                item["is_command"] = is_command
                item["command"] = str(uuid4())
                item["action_name"] = action_name(proposal["kind"][len("command."):]) if is_command else ""
                item["proposed_shown"] = (command_values(proposal["kind"], proposal["groups"].get("args", {}), device)
                                           if is_command else device.describe(proposal["groups"]))
                item["current_shown"] = (device.describe(item["current"]["groups"])
                                          if item["current"] and item["current"].get("groups") else [])
                reviews.append(item)
        context = dict(request=request, phone=phone, page=page, home=device.home is not None,
                       pairing=pairing_screen, command_rows=command_status_rows(device),
                       reviews=reviews,
                       csrf=getattr(request.state, "csrf", ""), session=getattr(session, "token", ""),
                       trust_state=trust_state,
                       base_path="/journal", message=message, error=error,
                       locale=locale)
        return _views.TemplateResponse(request=request, name="native.html", context=context)

    @router.get("/journal", response_class=HTMLResponse)
    async def journal_home(request: Request):
        try:
            return render(request, page="register")
        except JournalError:
            return RedirectResponse("/", status_code=303)

    @router.get("/journal/devices", response_class=HTMLResponse)
    async def journal_devices(request: Request):
        try:
            return render(request)
        except JournalError:
            return RedirectResponse("/", status_code=303)

    @router.post("/journal/sync")
    async def journal_sync(request: Request):
        try:
            await read_form(request)
            current = runtime()
            result = await current._synchronize()
            if result == "synced":
                return render(request, page="register", message="Sync completed")
            if result == "idle":
                return render(request, page="register", message="Everything is up to date")
            if result == "syncing":
                return render(request, page="register", message="Synchronization is already running")
            if result == "offline":
                return render(request, page="register", error="Home unavailable · Your pending edits are saved on this device")
            if result == "locked":
                return render(request, page="register", error="Unlock this profile before syncing")
            return render(request, page="register", error="Sync did not complete. Your pending edits remain saved on this device")
        except (JournalError, OSError, TimeoutError) as error:
            return render(request, page="register", error=str(error))

    @router.post("/journal/review")
    async def journal_review(request: Request):
        try:
            data = await read_form(request)
            device = runtime().device
            if device.home is None:
                raise JournalError("Review this action on the home")
            device.home.review(command_id=str(data.get("command", "")),
                               proposal_id=str(data.get("proposal", "")), token=str(data.get("token", "")),
                               choice=str(data.get("choice", "")), existing=str(data.get("existing", "")) or None)
            device.home.process()
            return RedirectResponse("/journal", status_code=303)
        except (JournalError, ValueError) as error:
            return render(request, page="register", error=str(error))

    @router.post("/journal/seen")
    async def journal_seen(request: Request):
        try:
            data = await read_form(request)
            runtime().device.displayed(data.getlist("proposal"))
            return RedirectResponse("/journal", status_code=303)
        except (JournalError, ValueError) as error:
            return render(request, page="register", error=str(error))

    @router.post("/journal/devices/{action}")
    async def journal_device_action(request: Request, action: str):
        try:
            data = await read_form(request)
            current = runtime()
            pairing = current.pairing
            if action == "revoke":
                pairing.revoke(str(data.get("device", "")))
                return RedirectResponse("/journal/devices", status_code=303)
            if action in {"open", "stop", "find", "join", "compare", "prove", "cancel", "confirm", "check"}:
                if pairing is None:
                    raise JournalError("Nearby pairing is unavailable")
                if action == "open":
                    pairing.begin(str(data.get("password", "")))
                elif action == "stop":
                    pairing.stop()
                elif action == "find":
                    await pairing.find()
                elif action == "join":
                    await pairing.join(str(data.get("candidate", "")), str(data.get("code", "")))
                elif action == "compare":
                    pairing.compare(str(data.get("digits", "")))
                elif action == "prove":
                    await pairing.prove(str(data.get("password", "")))
                elif action == "cancel":
                    pairing.cancel()
                elif action == "confirm":
                    pairing.confirm(str(data.get("digits", "")))
                elif action == "check":
                    await pairing.finish()
                return RedirectResponse("/journal/devices", status_code=303)
            trust = getattr(current, "trust", None)
            methods = {"owner-rotate": "rotate_owner", "move": "move_home", "recover-home": "recover_home"}
            method_name = methods.get(action)
            method = getattr(trust, method_name, None) if trust is not None and method_name else None
            if method is None:
                raise JournalError("This device action is unavailable for the current profile")
            values = {key: str(data.get(key, "")) for key in
                      ("password", "answer", "recovery", "new_password", "new_answer", "new_recovery", "target", "code")}
            parameters = inspect.signature(method).parameters
            extra_proofs = any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
            outcome = method(**{key: value for key, value in values.items()
                                if key in parameters or (extra_proofs and key in {"answer", "recovery"})})
            if inspect.isawaitable(outcome):
                outcome = await outcome
            return render(request, message=str(outcome or "The device action completed"))
        except (JournalError, OSError, TimeoutError, ValueError) as error:
            return render(request, error=str(error))

    return router
