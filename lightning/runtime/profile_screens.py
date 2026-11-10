"""The profile lifecycle screens: the list, new profile, unlock (password and fingerprint), recovery and the
security settings of an open profile (IT-9K). Moved out of `profile_app` unchanged; the routes of restore, devices
and Lock stay beside the session code they call. A route here sees the session, the devices and the gate only
through `ProfileScreens`."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from starlette.requests import Request
from starlette.responses import RedirectResponse

from lightning.database.backup import list_backups
from lightning.database.seed import CASH_ASSETS
from lightning.security.keys import SUGGESTED_QUESTIONS, suggest_password
from lightning.ui.entitlements import use_folder as use_licence_folder
from lightning.ui.i18n import BROWSER_UI, localize_html
from lightning.ui.web import templates

from .paths import choose_data_root, discover_profiles, resolve_profile
from .roles import SessionRole
from .session import ProfileError


@dataclass
class ProfileScreens:
    """What the screens need from `profile_app`, and what they hand back for the routes that stay there."""
    session: Any
    devices: Any
    gate: Any
    fingerprint: Any                       # the phone's fingerprint unlock, or None
    kept: Any                              # staying signed in on the phone, or None
    open_kept: Callable[..., Any]
    keep_signed_in: Callable[[Any], None]
    page: Callable[..., Any] = None        # set by register(): render a profile screen
    action: Callable[..., Any] = None      # set by register(): run an operation, then show its result
    fingerprint_possible: Callable[[], bool] = None
    fingerprint_page: Callable[..., Any] = None


def register(app, screens: ProfileScreens) -> ProfileScreens:
    session, devices, fingerprint, kept = screens.session, screens.devices, screens.fingerprint, screens.kept
    open_kept, keep_signed_in = screens.open_kept, screens.keep_signed_in
    def page(request: Request, mode: str, *, error="", status=200, **context):
        locale = request.cookies.get("lightning_ui_locale", "en")
        locale = locale if locale in ("en", "ar") else "en"
        values = dict(mode=mode, csrf=session.csrf, error=error, root=str(session.root), borrowed=[],
                      journal_enabled=session.journal is not None,
                      is_borrowed=session.borrowed is not None, writable=session.role.writable,
                      profiles=[], backups=[], selected="", backup="", name="", recovery="",
                      active_name=session.name, notice="", suggestion="", chosen_password="",
                      questions=SUGGESTED_QUESTIONS, question="", new_recovery="", locale=locale,
                      profile_currencies=CASH_ASSETS, currency="EGP",
                      arabic_translations=BROWSER_UI if locale == "ar" else {})
        if mode == "setup" and not context.get("suggestion"):
            values["suggestion"] = suggest_password()
        if mode == "manage":
            values["question"] = session.current_question()
        if mode == "unlock":
            values["fingerprint"] = fingerprint_offered(str(context.get("selected", "")))
            values["stay_offered"] = kept is not None and kept.available()
        values.update(context)
        values["journal_restore"] = (mode == "restore" and bool(values["backup"])
            and Path(values["backup"]).with_suffix(".journal-manifest.json").is_file())
        response = templates.TemplateResponse(request, "profiles.html", values, status_code=status)
        if locale == "ar":
            response.body = localize_html(response.body.decode("utf-8")).encode("utf-8")
            response.headers["content-length"] = str(len(response.body))
        return response

    async def action(request, mode, operation, **context):
        try:
            result = operation()
            app.state.container = session.container
            return result or RedirectResponse("/" if session.container else "/profiles", 303)
        except ProfileError as exc:
            return page(request, mode, error=str(exc), status=400, **context)
        except Exception as exc:
            # Never render native exception strings (paths, SQL, secrets); the error's kind alone helps a report.
            return page(request, mode, error="The operation could not finish. Your existing database was not "
                        f"replaced. Check the folder permissions, available space and app version ({type(exc).__name__}).",
                        status=400, **context)

    @app.get("/profiles")
    async def profiles(request: Request):
        if session.container:
            return page(request, "manage")
        if session.paths is not None:
            return RedirectResponse("/profiles/checking", 303)
        try:
            root_value = request.query_params.get("root")
            if root_value:
                session.root = choose_data_root(root_value)
                use_licence_folder(session.root / "cosmetics")
            found = discover_profiles(session.root)
            if not root_value and await open_kept(found):
                return RedirectResponse("/", 303)
            backups = []
            for info in found:
                paths = resolve_profile(info.path)
                backups.extend({"path": str(item.path), "label": item.path.name,
                                "db": str(paths.db_path)}
                               for item in list_backups(paths.backups_dir, paths.db_path))
            return page(request, "choose", profiles=found, backups=backups, borrowed=devices.borrowed())
        except (OSError, ValueError):
            return page(request, "choose", error="That folder could not be read. Choose another location.", status=400)

    @app.post("/profiles/locale")
    async def save_gate_locale(request: Request):
        """Remember the locked-screen language separately from encrypted profile settings."""
        form = await request.form()
        locale = str(form.get("locale", "en"))
        locale = locale if locale in ("en", "ar") else "en"
        return_to = str(form.get("return_to", "/profiles"))
        if not return_to.startswith("/profiles") or return_to.startswith("//") or "\\" in return_to:
            return_to = "/profiles"
        response = RedirectResponse(return_to, 303)
        response.set_cookie("lightning_ui_locale", locale, max_age=60 * 60 * 24 * 365,
                            httponly=False, secure=request.url.scheme == "https", samesite="lax", path="/")
        return response

    @app.get("/profiles/new")
    async def new(request: Request):
        if session.container:
            return RedirectResponse("/profiles", 303)
        return page(request, "setup")

    @app.post("/profiles/new")
    async def prepare(request: Request):
        form = await request.form()
        suggestion = str(form.get("suggestion", ""))
        # "Use this password" takes the suggested words as the password, typed by nobody.
        chosen = suggestion if form.get("use_suggestion") == "yes" else ""
        password = chosen or str(form.get("password", ""))
        confirm = chosen or str(form.get("confirm", ""))
        currency = str(form.get("currency", "EGP"))
        def operation():
            pending = session.prepare(str(form.get("name", "")), password, confirm,
                                      str(form.get("question", "")), str(form.get("answer", "")), currency)
            return page(request, "recovery-key", recovery=pending.recovery, name=pending.paths.profile.name,
                        chosen_password=chosen, notice="Will create: " + str(pending.paths.db_path))
        return await action(request, "setup", operation, name=str(form.get("name", "")), suggestion=suggestion,
                            question=str(form.get("question", "")), currency=currency)

    @app.post("/profiles/confirm")
    async def confirm(request: Request):
        if session.pending is None:
            return page(request, "setup", error="Setup expired. Create the profile again.", status=400)
        pending = session.pending
        # Owner, 2026-10-06: the key is shown once and confirmed with a press, not typed back.
        return await action(request, "recovery-key", lambda: session.confirm(pending.recovery),
                            recovery=pending.recovery, name=pending.paths.profile.name if pending.paths.profile else "")

    @app.get("/profiles/open-file")
    async def open_file_page(request: Request):
        if session.container:
            return RedirectResponse("/profiles", 303)
        return page(request, "open-file")

    @app.post("/profiles/open-file")
    async def open_file(request: Request):
        """Bring a profile file in (BT-2AI2): it becomes a new profile here and opens. The upload is written to a
        private temporary file in the profiles folder, checked there, and deleted whatever happens."""
        import os
        import secrets
        from .http import PROFILE_FILE_PATH
        from .profile_file import MAX_BYTES, TOO_LARGE, read_profile_file
        if session.container:
            return RedirectResponse("/profiles", 303)
        assert request.url.path == PROFILE_FILE_PATH
        form = await request.form(max_files=1, max_fields=10)
        upload, password = form.get("profile"), str(form.get("password", ""))

        def operation():
            if not hasattr(upload, "file") or not getattr(upload, "filename", ""):
                raise ProfileError("Choose a profile file to open.")
            session.root.mkdir(parents=True, exist_ok=True)
            incoming = session.root / f".incoming-{secrets.token_hex(12)}.partial"
            try:
                descriptor = os.open(incoming, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                size = 0
                with os.fdopen(descriptor, "wb") as target:
                    for block in iter(lambda: upload.file.read(1024 * 1024), b""):
                        size += len(block)
                        if size > MAX_BYTES:
                            raise ProfileError(TOO_LARGE)
                        target.write(block)
                opened = read_profile_file(incoming, password, session.root)
            finally:
                incoming.unlink(missing_ok=True)
            selected = str(opened.paths.db_path)
            role = SessionRole.READER if opened.review_copy or devices.role_for(selected) == "reader" else SessionRole.HOME
            session.unlock(selected, password, role=role)
            if session.journal is None:
                devices.after_unlock(session.paths)
        return await action(request, "open-file", operation)

    @app.post("/profiles/cancel")
    async def cancel(request: Request):
        session.pending = None
        return RedirectResponse("/profiles", 303)

    @app.get("/profiles/unlock")
    async def unlock_page(request: Request):
        if session.container:
            return RedirectResponse("/profiles", 303)
        return page(request, "unlock", selected=request.query_params.get("db", ""))

    @app.post("/profiles/unlock")
    async def unlock(request: Request):
        form = await request.form()
        selected = str(form.get("db", ""))
        role = SessionRole.READER if devices.role_for(selected) == "reader" else SessionRole.HOME

        def operation():
            session.unlock(selected, str(form.get("password", "")), role=role)
            if session.journal is None:
                devices.after_unlock(session.paths)
            keep_signed_in(form)
        return await action(request, "unlock", operation, selected=selected)

    def fingerprint_offered(selected: str) -> bool:
        """The unlock screen's "Use fingerprint": only on the phone, with a slot for this profile and a phone
        that can ask for the fingerprint now."""
        if fingerprint is None or not selected or session.container is not None:
            return False
        try:
            profile_id, _ = session.fingerprint_target(selected)
        except (ProfileError, OSError, ValueError):
            return False
        return bool(profile_id) and fingerprint.offered(profile_id)

    @app.post("/profiles/unlock/fingerprint")
    async def unlock_fingerprint(request: Request):
        """The password screen's other way in. The prompt waits for the person on a worker thread; cancelling
        leaves the password screen as it was, and no attempt is counted."""
        from lightning.security.biometric import Outcome
        form = await request.form()
        selected = str(form.get("db", ""))
        role = SessionRole.READER if devices.role_for(selected) == "reader" else SessionRole.HOME
        try:
            profile_id, ident = session.fingerprint_target(selected) if fingerprint is not None else ("", "")
        except (ProfileError, OSError, ValueError) as exc:
            return page(request, "unlock", error=str(exc), status=400, selected=selected)
        if not profile_id:
            return page(request, "unlock", selected=selected, status=400,
                        error="Fingerprint unlock is not available now. Unlock with your password.")
        result = await asyncio.to_thread(fingerprint.unlock, profile_id, ident)
        if result.outcome is Outcome.OK:
            def operation():
                session.unlock_with_key(selected, result.key, role=role)
                if session.journal is None:
                    devices.after_unlock(session.paths)
            return await action(request, "unlock", operation, selected=selected)
        if result.outcome is Outcome.CANCELLED:
            return page(request, "unlock", selected=selected)
        if result.outcome in (Outcome.INVALIDATED, Outcome.MISMATCH):
            return page(request, "unlock", selected=selected, notice=result.message)
        return page(request, "unlock", selected=selected, status=400, error=result.message)

    def fingerprint_page(request: Request, *, status=200, error="", notice=""):
        from lightning.ui import web
        profile_id = session.paths.profile.profile_id if session.paths is not None and session.paths.profile else ""
        return web.render(request, "phone/fingerprint.html", status, csrf=session.csrf, error=error, notice=notice,
                          fingerprint_on=bool(profile_id) and fingerprint.enabled(profile_id))

    def fingerprint_possible() -> bool:
        return (fingerprint is not None and session.container is not None and session.borrowed is None
                and session.paths is not None and session.paths.profile is not None and fingerprint.available())

    @app.get("/profiles/fingerprint")
    async def fingerprint_get(request: Request):
        if not fingerprint_possible():
            return RedirectResponse("/settings" if session.container else "/profiles", 303)
        return fingerprint_page(request)

    @app.post("/profiles/fingerprint")
    async def fingerprint_post(request: Request):
        """Settings › This phone › Unlock with fingerprint. On needs the profile open and its password typed
        again, then the fingerprint prompt; off deletes the slot and the Keystore key."""
        from lightning.security.biometric import ENROL_MESSAGES, Outcome
        if not fingerprint_possible():
            return RedirectResponse("/settings" if session.container else "/profiles", 303)
        form = await request.form()
        profile_id = session.paths.profile.profile_id
        if form.get("action") == "off":
            await asyncio.to_thread(fingerprint.disable, profile_id)
            return fingerprint_page(request, notice="Fingerprint unlock is off. Your password still unlocks this profile.")
        try:
            key = session.prove_password(str(form.get("password", "")))
        except ProfileError as exc:
            return fingerprint_page(request, status=400, error=str(exc))
        outcome = await asyncio.to_thread(fingerprint.enrol, profile_id, key)
        if outcome is Outcome.OK:
            return fingerprint_page(request, notice="Fingerprint unlock is on. Your password still works.")
        return fingerprint_page(request, status=400, error=ENROL_MESSAGES[outcome])

    def known_question(selected: str) -> str:
        try:
            return session.question(selected)
        except (ProfileError, OSError, ValueError):
            return ""

    @app.get("/profiles/recover")
    async def recover_page(request: Request):
        if session.container:
            return RedirectResponse("/profiles", 303)
        selected = request.query_params.get("db", "")
        question = known_question(selected)
        return page(request, "recover", selected=selected, question=question,
                    error="" if question else "This profile's key file is missing or damaged, so it cannot be recovered here.")

    @app.post("/profiles/recover")
    async def recover(request: Request):
        form = await request.form()
        selected = str(form.get("db", ""))
        def operation():
            session.recover(selected, str(form.get("recovery", "")), str(form.get("answer", "")),
                            str(form.get("password", "")), str(form.get("confirm", "")))
            return page(request, "unlock", selected=selected, notice="Password reset. Unlock with your new password.")
        return await action(request, "recover", operation, selected=selected, question=known_question(selected))

    @app.post("/profiles/password")
    async def password(request: Request):
        form = await request.form()
        def operation():
            session.change_password(str(form.get("proof", "")), str(form.get("password", "")), str(form.get("confirm", "")))
            return page(request, "manage", notice="Password changed. Your recovery key and security question are unchanged.")
        return await action(request, "manage", operation)

    @app.post("/profiles/question")
    async def question(request: Request):
        form = await request.form()
        def operation():
            session.change_question(str(form.get("recovery", "")), str(form.get("question", "")), str(form.get("answer", "")))
            return page(request, "manage", notice="Security question changed. Your password and recovery key are unchanged.")
        return await action(request, "manage", operation)

    @app.post("/profiles/recovery-key")
    async def recovery_key(request: Request):
        form = await request.form()
        def operation():
            pending = session.prepare_recovery_key(str(form.get("answer", "")))
            return page(request, "manage", new_recovery=pending.recovery)
        return await action(request, "manage", operation)

    @app.post("/profiles/recovery-key/confirm")
    async def confirm_recovery_key(request: Request):
        pending = session.pending_recovery
        def operation():
            session.confirm_recovery_key(pending.recovery if pending else "")
            return page(request, "manage", notice="New recovery key saved. The old one no longer works.")
        return await action(request, "manage", operation, new_recovery=pending.recovery if pending else "")

    screens.page, screens.action = page, action
    screens.fingerprint_possible, screens.fingerprint_page = fingerprint_possible, fingerprint_page
    return screens
