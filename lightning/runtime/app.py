"""Profile screens and serialized access to the existing finance application."""
from __future__ import annotations

import asyncio
import re
import time
from contextlib import suppress
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response

from lightning.database.backup import list_backups
from lightning.database.seed import CASH_ASSETS
from lightning.sync.state import ProtocolError
from lightning.security.keys import SUGGESTED_QUESTIONS, suggest_password
from lightning.ui.i18n import BROWSER_UI, localize_html
from lightning.ui.web import create_app, templates

from .http import (MARKET_IMPORT_PATH, MAX_IMPORT_CONFIRM_BODY, MAX_IMPORT_CONFIRM_FIELDS, MAX_MARKET_IMPORT_BODY,
                   MAX_IMPORT_MAP_BODY, Credentials, Guard,
                   body_receiver, configure_memory_only_import_uploads, equal)
from .devices import Devices, home_state_line, move_to_phone, open_move
from .paths import choose_data_root, discover_profiles, resolve_profile
from .roles import READ_ONLY_REFUSAL, SessionRole

READ_ONLY_PATH = "/__read-only"
from .session import AttemptGuard, ProfileError, ProfileSession

_DEFAULT_FORM_FIELDS = 2_000
_IMPORT_CONFIRM_FORM_FIELDS = MAX_IMPORT_CONFIRM_FIELDS


def _form_field_limit(path: str) -> int:
    if re.fullmatch(r"/accounts/\d+/import/\d+/confirm", path):
        return _IMPORT_CONFIRM_FORM_FIELDS
    return _DEFAULT_FORM_FIELDS


def _form_part_limit(path: str) -> int:
    # The mapping page carries the CSV as base64 in one multipart text field.
    if re.fullmatch(r"/accounts/\d+/import/map", path):
        return MAX_IMPORT_MAP_BODY
    # A large CSV can include a correspondingly long notes cell in one review row.
    if re.fullmatch(r"/accounts/\d+/import/\d+/confirm", path):
        return MAX_IMPORT_CONFIRM_BODY
    if path == MARKET_IMPORT_PATH:
        return MAX_MARKET_IMPORT_BODY
    return 512 * 1024


def _form_file_limit(path: str) -> int:
    # Only the initial CSV upload and the market price file accept a file part. Rejecting
    # files on every other form avoids creating spooled temporary files on those routes.
    return 1 if re.fullmatch(r"/accounts/\d+/import", path) or path == MARKET_IMPORT_PATH else 0


class SessionGate:
    """Serialize entire requests, including awaits, with lifecycle transitions.

    Every write also carries the token rendered with its profile. An old tab can
    never write into a new profile, even if it submits after that profile unlocks.
    """
    def __init__(self, app, session: ProfileSession):
        self.app, self.session = app, session
        self.mutex = asyncio.Lock()

    async def set_mode(self, mode: str) -> None:
        """Sync's mode change for the open profile (lightning.runtime.devices.AppBridge), between requests."""
        async with self.mutex:
            try:
                self.session.set_mode(mode)
            finally:
                self.app.state.container = self.session.container

    def device_line(self) -> tuple[str, str]:
        """The status line under the header while a ledger is borrowed or lent, and its action."""
        devices, session = getattr(self, "devices", None), self.session
        if session.journal is not None:
            runtime = session.journal
            pending = len(runtime.store.pending())
            return (f"{pending} edits waiting for the home" if pending else "Synchronized profile", "")
        if devices is None or session.paths is None:
            return "", ""
        if session.borrowed is not None:
            if session.role.writable:
                return f"Borrowed from {session.borrowed_home or 'your phone'}", "hand-back"
            return "Read only on this PC: the ledger is going home or needs repair.", ""
        try:
            lending = devices.lending_state(session.paths)
            line = home_state_line(devices.home_node(session.paths) if lending == "ok" else None, lending)
        except Exception:  # noqa: BLE001 - an unreadable record shows as needing the Devices page
            line = "The ledger's lending record needs checking."
        return line, ("take-back" if line else "")

    async def change_role(self, role) -> None:
        """Change the open profile's role between requests, never during one (multi-device task 06)."""
        async with self.mutex:
            try:
                self.session.change_role(role)
            finally:
                self.app.state.container = self.session.container

    def fingerprint_row(self, path: str) -> str:
        """For Settings › This phone: "" when fingerprint unlock is not offered here, else "on" or "off"."""
        fingerprint = getattr(self, "fingerprint", None)
        session = self.session
        if (path != "/settings" or fingerprint is None or session.container is None or session.borrowed is not None
                or session.paths is None or session.paths.profile is None or not fingerprint.available()):
            return ""
        return "on" if fingerprint.enabled(session.paths.profile.profile_id) else "off"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        generation = self.session.token
        async with self.mutex:
            request = Request(scope)
            profile_route = request.url.path == "/profiles" or request.url.path.startswith("/profiles/")
            public = profile_route or request.url.path.startswith("/static/")
            if not public and self.session.container is None and self.session.paths is None:
                return await RedirectResponse("/profiles", 303)(scope, receive, send)
            if not public and self.session.container is None:
                # Sync closed the ledger for a moment (a returned copy going in): wait, not the chooser.
                return await RedirectResponse("/profiles/checking", 303)(scope, receive, send)
            if scope["method"] not in ("GET", "HEAD") and not profile_route and not self.session.role.writable:
                line = self.device_line()[0]
                if request.headers.get("x-requested-with") == "fetch":  # an inline save shows this text as is
                    text = f"{line}. Nothing was saved." if line else READ_ONLY_REFUSAL
                    return await PlainTextResponse(text, 403)(scope, receive, send)
                # A form: say so in a page of the app, with who has the ledger and a way on (see read_only_page).
                scope = dict(scope, method="GET", path=READ_ONLY_PATH, raw_path=READ_ONLY_PATH.encode(),
                             query_string=b"")
            elif scope["method"] not in ("GET", "HEAD"):
                if generation != self.session.token:
                    return await PlainTextResponse("Profile changed. Reload before submitting.", 409)(scope, receive, send)
                body = scope["state"]["request_body"]
                parsed = Request(scope, body_receiver(body))
                try:
                    async with parsed.form(max_files=_form_file_limit(request.url.path),
                                           max_fields=_form_field_limit(request.url.path),
                                           max_part_size=_form_part_limit(request.url.path)) as form:
                        token = form.get("csrf" if profile_route else "__session", "")
                        expected = self.session.csrf if profile_route else self.session.token
                        valid = isinstance(token, str) and equal(token, expected)
                except Exception:
                    valid = False
                if not valid:
                    return await PlainTextResponse("This form expired. Reload the page and try again.", 403)(scope, receive, send)
            line, device_action = self.device_line()
            scope.setdefault("state", {}).update(fingerprint_row=self.fingerprint_row(request.url.path),
                                                  secure_profiles=True, csrf=self.session.csrf,
                                                  phone=getattr(self, "phone", False),
                                                  session_token=self.session.token,
                                                  read_only=not self.session.role.writable,
                                                  device_line=line, device_action=device_action)
            self.app.state.container = self.session.container
            if self.session.journal is not None and self.session.journal.task is None:
                self.session.journal.start(self, files_dir=self.session.root.parent if getattr(self, "phone", False) else None)
            if self.session.container is not None and request.url.path != "/profiles/health" and not request.url.path.startswith("/static/"):
                self.session.last_activity = time.monotonic()
            await self.app(scope, receive, send)


def profile_app(credentials: Credentials, root: Path | str | None = None, devices: Devices | None = None,
                *, phone: bool = False, sms=None, biometric=None):
    """`phone`: the Android app, whose pages use the phone frame and screens (guideline Part C). `sms`: where
    bank messages come from on that phone (`lightning.sms_imports.SmsSource`), or None. `biometric`: the phone's
    optional fingerprint unlock (`lightning.security.biometric.FingerprintUnlock`), or None: never on a PC."""
    configure_memory_only_import_uploads()
    session = ProfileSession(root)
    session.borrowed_home = ""
    app = create_app(None)
    app.state.profile_session = session
    from .journal_ui_routes import journal_ui_router
    from .journal_enrollment_routes import journal_enrollment_router
    from .journal_setup_routes import journal_setup_router
    from .journal_recovery_routes import journal_recovery_router
    app.include_router(journal_ui_router(session))
    app.include_router(journal_enrollment_router(session))
    app.include_router(journal_recovery_router(session))
    app.state.sms_source = sms
    gate = SessionGate(app, session)
    devices = devices if devices is not None else Devices()
    app.include_router(journal_setup_router(session, devices))
    gate.devices = devices
    gate.phone = phone
    fingerprint = biometric if phone else None
    gate.fingerprint = fingerprint

    async def expire_sessions():
        while True:
            await asyncio.sleep(1)
            async with gate.mutex:
                if session.pending and time.monotonic() >= session.pending.expires:
                    session.pending = None
                if session.container and time.monotonic() - session.last_activity >= session.idle_seconds:
                    borrowed = session.borrowed
                    session.close()
                    app.state.container = None
                    if borrowed is not None:  # idle lock: hand back if the phone answers, else seal (review L13)
                        asyncio.get_running_loop().run_in_executor(None, devices.hand_back_or_seal, borrowed)

    @asynccontextmanager
    async def lifespan(_app):
        devices.start(asyncio.get_running_loop(), session, gate)
        expiry = asyncio.create_task(expire_sessions())
        try:
            yield
        finally:
            expiry.cancel()
            with suppress(asyncio.CancelledError):
                await expiry
            borrowed = session.borrowed
            session.close()
            app.state.container = None
            if borrowed is not None:
                # Closing Lightning on the PC: hand back if the phone answers, else keep the lend sealed here.
                with suppress(Exception):
                    await asyncio.to_thread(devices.hand_back_or_seal, borrowed)
            devices.stop()

    app.router.lifespan_context = lifespan

    @app.get("/profiles/health")
    async def health():
        # Locked means closed. While sync briefly closes an open ledger (a returned copy going in) it is not.
        return JSONResponse({"ok": True, "locked": session.paths is None, "session": session.token})

    @app.get("/profiles/checking")
    async def checking(request: Request):
        """While a copy a PC handed back goes in, the phone's ledger is closed for a moment: wait here."""
        if session.container is not None:
            return RedirectResponse("/", 303)
        if session.paths is None:
            return RedirectResponse("/profiles", 303)
        return page(request, "checking")

    @app.get(READ_ONLY_PATH)
    async def read_only_page(request: Request):
        """A form saved while this device only reads the ledger: the gate turns that POST into this page."""
        from lightning.ui import web
        if session.container is None or session.role.writable:
            return RedirectResponse("/", 303)
        action = gate.device_line()[1]
        came_from = urlsplit(request.headers.get("referer", ""))
        back = came_from.path + (f"?{came_from.query}" if came_from.query else "")
        if not back.startswith("/") or back.startswith("//") or came_from.path == READ_ONLY_PATH:
            back = "/"
        return web.render(request, "read_only.html", 403, holder=lent_to(), action=action, back=back,
                          refusal=READ_ONLY_REFUSAL)

    def lent_to() -> str:
        """The PC this phone's ledger is lent to, or "" when it reads only for another reason."""
        from lightning.sync.state import HomeState
        if session.borrowed is not None or session.paths is None or devices.lending_state(session.paths) != "ok":
            return ""
        node = devices.home_node(session.paths)
        home = node.model if node is not None else None
        if home is None or home.state is not HomeState.LENT or home.active is None:
            return ""
        peer = node.store.peer(home.active.grant.borrower_id)
        return peer.name if peer else "A PC"

    @app.post("/__activity")
    async def activity():
        # Admitted under the current profile token; JS sends only in response to
        # trusted keyboard/pointer input, never from the background health poll.
        return Response(status_code=204)

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
            found = discover_profiles(session.root)
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
        form = await request.form()
        if session.pending is None:
            return page(request, "setup", error="Setup expired. Create the profile again.", status=400)
        pending = session.pending
        # Owner, 2026-10-06: the key is shown once and confirmed with a press, not typed back.
        return await action(request, "recovery-key", lambda: session.confirm(pending.recovery),
                            recovery=pending.recovery, name=pending.paths.profile.name if pending.paths.profile else "")

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

    @app.get("/profiles/restore")
    async def restore_page(request: Request):
        if session.container:
            return RedirectResponse("/profiles", 303)
        return page(request, "restore", selected=request.query_params.get("db", ""),
                    backup=request.query_params.get("backup", ""))

    @app.post("/profiles/restore")
    async def restore(request: Request):
        form = await request.form()
        selected = str(form.get("db", ""))
        backup_path = str(form.get("backup", ""))
        if devices.blocks_restore(selected):  # review H2: an old backup would fork a lent ledger
            return page(request, "restore", status=400, selected=selected, backup=backup_path,
                        error="This profile is lent to a PC or has a hand-back to finish. Bring the ledger home "
                              "first (Devices), then restore.")
        if form.get("confirm") != "yes":
            return page(request, "restore", status=400, selected=selected, backup=backup_path,
                        error="Confirm that this backup restore should proceed.")
        try:
            restored_copy = session.restore_backup(selected, backup_path, str(form.get("password", "")))
        except ProfileError as exc:
            return page(request, "restore", status=400, selected=selected,
                        backup=backup_path, error=str(exc))
        except Exception:
            # Replacement may already have happened before a disk or process
            # error. Never promise the old live path is still unchanged.
            return page(request, "restore", status=400, selected=selected,
                        backup=backup_path, error="Restore needs checking. Keep this profile locked and inspect the selected backup and retained copies before trying again.")
        if restored_copy:
            return page(request, "unlock", selected=restored_copy,
                        notice="Backup restored as a separate review copy. Pair a fresh device to recover saved edits.")
        return page(request, "unlock", selected=selected,
                    notice="Backup restored. The previous database was kept for recovery. Unlock this profile to review it.")

    @app.get("/profiles/restore/resume")
    async def resume_restore_page(request: Request):
        if session.container:
            return RedirectResponse("/profiles", 303)
        return page(request, "resume-restore", selected=request.query_params.get("db", ""))

    @app.post("/profiles/restore/resume")
    async def resume_restore(request: Request):
        form = await request.form()
        selected = str(form.get("db", ""))
        if devices.blocks_restore(selected):
            return page(request, "resume-restore", status=400, selected=selected,
                        error="This profile is lent to a PC or has a hand-back to finish. Bring the ledger home "
                              "first (Devices).")
        if form.get("confirm") != "yes":
            return page(request, "resume-restore", status=400, selected=selected,
                        error="Confirm that Lightning should check and resume this restore.")
        try:
            session.resume_interrupted_restore(selected, str(form.get("password", "")))
        except ProfileError as exc:
            return page(request, "resume-restore", status=400, selected=selected, error=str(exc))
        except Exception:
            return page(request, "resume-restore", status=400, selected=selected,
                        error="Restore recovery needs inspection. The profile remains locked and its copies were kept.")
        return page(request, "unlock", selected=selected,
                    notice="Restore checks finished. Unlock this profile to review the recovered database.")

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
        form = await request.form()
        pending = session.pending_recovery
        def operation():
            session.confirm_recovery_key(pending.recovery if pending else "")
            return page(request, "manage", notice="New recovery key saved. The old one no longer works.")
        return await action(request, "manage", operation, new_recovery=pending.recovery if pending else "")

    @app.post("/profiles/lock")
    async def lock(request: Request):
        if session.borrowed is not None:
            return await hand_back(request)
        return await action(request, "manage", session.close)

    # ------------------------------------------------------------ multiple devices: the phone's side
    def device_page(request, **context):
        if session.journal is not None:
            return RedirectResponse("/journal/devices", 303)
        if gate.phone and session.container is not None and session.borrowed is None:
            return phone_device_page(request, **context)
        return pc_device_page(request, **context)

    def phone_device_page(request, *, status=200, error="", notice="", **context):
        """Inside the phone frame (review, 2026-10-06): the same figures as below, the phone's own layout."""
        from lightning.ui import web
        response = pc_device_page(request, status=status, error=error, notice=notice, **context)
        keys = ("csrf", "error", "notice", "state_line", "lending", "pending", "peers", "lent_to", "address",
                "phone_name")
        return web.render(request, "phone/devices.html", status,
                          **{key: response.context.get(key) for key in keys})

    def pc_device_page(request, **context):
        lending = devices.lending_state(session.paths) if session.paths is not None else "none"
        if lending in ("missing", "damaged"):
            return page(request, "devices", node=None, peers=[], lent_to="", pending=None, address="",
                        state_line=home_state_line(None, lending), lending=lending,
                        phone_name=devices.identity().name if devices.has_identity() else "", **context)
        node = devices.home_node(session.paths) if session.paths is not None else None
        pending = devices.desk.pending if devices.desk is not None else None
        if pending is not None and (node is None or pending.node is not node):
            pending = None
        peers = node.store.peers() if node is not None else []
        home = node.model if node is not None else None
        lent_to = home.active.grant.borrower_id if home is not None and home.active is not None else ""
        return page(request, "devices", node=node, peers=peers, lent_to=lent_to, pending=pending,
                    address=devices.address() if devices.server is not None else "",
                    state_line=home_state_line(node), lending=lending, phone_name=devices.identity().name
                    if devices.has_identity() else "", **context)

    def home_only():
        if session.journal is not None:
            return RedirectResponse("/journal/devices", 303)
        if session.container is None:
            return RedirectResponse("/profiles", 303)
        if devices.lending_state(session.paths) in ("missing", "damaged"):
            return RedirectResponse("/profiles/devices", 303)
        if session.borrowed is not None:
            return RedirectResponse("/profiles", 303)
        return None

    @app.get("/profiles/devices")
    async def devices_page(request: Request):
        if session.container is not None and session.borrowed is None:
            return device_page(request)  # also where a missing or damaged lending record is repaired
        return home_only() or device_page(request)

    @app.post("/profiles/devices/pair")
    async def open_pairing(request: Request):
        if (refused := home_only()) is not None:
            return refused
        form = await request.form()
        name = " ".join(str(form.get("phone_name", "")).split())[:60]
        if not name:
            return device_page(request, error="Name this phone, so the PC can show it.", status=400)
        try:
            node = devices.home_node(session.paths) or devices.enable_home(session, name)
            devices.identity(name)
            devices.ensure_listener()
        except OSError:
            return device_page(request, error="Another app is using the port Lightning listens on. Close it and "
                                              "try again.", status=400)
        except (ProtocolError, ValueError) as exc:
            return device_page(request, error=str(exc), status=400)
        devices.desk.open(node, home_name=name, profile_name=session.name)
        return RedirectResponse("/profiles/devices", 303)

    @app.post("/profiles/devices/keep-home")
    async def keep_home(request: Request):
        if session.container is None or session.borrowed is not None:
            return RedirectResponse("/profiles", 303)
        form = await request.form()
        if form.get("confirm") != "yes":
            return device_page(request, error="Tick the box to confirm that a PC's copy from before will not "
                                              "come back.", status=400)
        try:
            devices.keep_as_home(session, devices.identity().name if devices.has_identity() else "My phone")
            session.set_mode("home")
            app.state.container = session.container
        except (ProtocolError, OSError, ValueError) as exc:
            return device_page(request, error=str(exc), status=400)
        return device_page(request, notice="This copy is the ledger again and opens for editing. Pair your PC "
                                           "again; its copy from before stays on it, read only.")

    @app.post("/profiles/devices/stop-pairing")
    async def stop_pairing(request: Request):
        if devices.desk is not None:
            devices.desk.close()
        return RedirectResponse("/profiles/devices", 303)

    @app.post("/profiles/devices/revoke")
    async def revoke(request: Request):
        if (refused := home_only()) is not None:
            return refused
        form = await request.form()
        node = devices.home_node(session.paths)
        if node is not None:
            try:
                node.revoke(str(form.get("device", "")))
            except ProtocolError as exc:
                return device_page(request, error=str(exc), status=400)
        return RedirectResponse("/profiles/devices", 303)

    @app.post("/profiles/devices/take-back")
    async def take_back(request: Request):
        if (refused := home_only()) is not None:
            return refused
        form = await request.form()
        node = devices.home_node(session.paths)
        if node is None:
            return RedirectResponse("/profiles/devices", 303)
        if form.get("confirm") != "yes":
            return device_page(request, error="Tick the box to confirm that the PC's edits since it borrowed "
                                              "the ledger will not come back.", status=400)
        try:
            node.take_back(reopen=False)  # this request holds the gate: reopen here, not through it
            session.set_mode("home")
            app.state.container = session.container
        except ProtocolError as exc:
            return device_page(request, error=str(exc), status=400)
        return device_page(request, notice="The ledger is back on this phone. That PC's copy can no longer be "
                                           "handed back; it stays on the PC, read only.")

    # ------------------------------------------------------------ multiple devices: the PC's side
    @app.get("/profiles/connect")
    async def connect_page(request: Request):
        if session.container:
            return RedirectResponse("/profiles", 303)
        import socket as _socket
        return page(request, "connect", pc_name=_socket.gethostname()[:60] or "This PC")

    @app.post("/profiles/connect")
    async def connect(request: Request):
        from lightning.sync.identity import normalize_code
        from lightning.sync.service import LinkDown
        from lightning.sync.transport import join_home, pair
        if session.container:
            return RedirectResponse("/profiles", 303)
        form = await request.form()
        address, code = str(form.get("address", "")).strip(), str(form.get("code", ""))
        pc_name = " ".join(str(form.get("pc_name", "")).split())[:60]
        values = dict(address=address, pc_name=pc_name)
        try:
            normalize_code(code)
            if not pc_name:
                raise ValueError("Name this PC, so the phone can show it.")
            identity = devices.identity(pc_name)
            paired = await asyncio.to_thread(pair, address, code, identity)
            node = await asyncio.to_thread(join_home, paired, endpoint=address, identity=identity, root=devices.root)
        except (ProfileError, ValueError) as exc:
            return page(request, "connect", error=str(exc), status=400, **values)
        except (LinkDown, ProtocolError) as exc:
            return page(request, "connect", error=str(exc), status=400, **values)
        return page(request, "connected", digits=paired.digits, profile_name=paired.reply.profile_name,
                    home_name=paired.reply.home_name, profile_id=node.model.profile_id)

    @app.get("/profiles/borrowed")
    async def borrowed_page(request: Request):
        if session.container:
            return RedirectResponse("/profiles", 303)
        found = devices.find_borrowed(request.query_params.get("id", ""))
        if found is None:
            return RedirectResponse("/profiles", 303)
        return page(request, "borrowed", item=found)

    @app.post("/profiles/borrowed")
    async def open_borrowed(request: Request):
        import json as _json
        from lightning.security.keys import unwrap_key
        from lightning.sync.copies import CopyRejected
        from lightning.sync.service import LinkDown
        from lightning.sync.state import BorrowerState
        if session.container:
            return RedirectResponse("/profiles", 303)
        form = await request.form()
        found = devices.find_borrowed(str(form.get("id", "")))
        if found is None:
            return RedirectResponse("/profiles", 303)
        node = found.node
        attempts = AttemptGuard(node.paths.keys_path.with_name("attempts.json"))
        try:
            attempts.check()
            try:
                key = unwrap_key(_json.loads(node.paths.keys_path.read_text(encoding="utf-8")),
                                 str(form.get("password", "")))
            except ValueError as exc:
                attempts.failed()
                raise ProfileError("The password is incorrect. It is the profile's password, the same as on "
                                   "the phone.") from exc
            attempts.succeeded()
            state = node.model.state
            notice = ""
            if state is BorrowerState.SEALED:
                if await asyncio.to_thread(devices.taken_back, node):
                    notice = "The phone took the ledger back. This copy is kept here, read only."
                else:
                    node.reopen()
            elif state is BorrowerState.RETURNING:
                result = await asyncio.to_thread(devices.hand_back_or_seal, node)
                if result in ("accepted", "handed_back"):
                    return page(request, "choose", notice=f"{found.name} is home on {found.home_name}. Open it "
                                                          "again to borrow it.", profiles=discover_profiles(session.root),
                                borrowed=devices.borrowed())
                notice = "The phone has not taken the ledger back yet. This copy is read only until it does."
            elif state is BorrowerState.NEEDS_REPAIR and form.get("start_over") == "yes":
                kept = await asyncio.to_thread(node.start_over)
                link = devices.link(node)
                await asyncio.to_thread(node.fetch, link, key)
                await asyncio.to_thread(node.borrow, link, key)
                notice = (f"You now edit the phone's ledger. This PC's earlier copy is kept as {kept.name}."
                          if kept is not None else "")
            elif state is BorrowerState.NEEDS_REPAIR:
                notice = "The phone took the ledger back. This copy is kept here, read only."
            elif state is not BorrowerState.BORROWING:
                link = devices.link(node)
                if state is not BorrowerState.BORROW_PREPARED:
                    await asyncio.to_thread(node.fetch, link, key)
                await asyncio.to_thread(node.borrow, link, key)
            session.open_borrowed(node, key, name=found.name, writable=node.writable)
            session.borrowed_home = found.home_name
            app.state.container = session.container
            if notice:
                return page(request, "manage", notice=notice)
            return RedirectResponse("/", 303)
        except ProfileError as exc:
            return page(request, "borrowed", item=found, error=str(exc), status=400)
        except LinkDown:
            return page(request, "borrowed", item=found, status=400,
                        error=f"{found.home_name} did not answer. Open Lightning on it, on the same Wi-Fi, and try "
                              "again.")
        except ProtocolError as exc:
            return page(request, "borrowed", item=found, error=str(exc), status=400)
        except CopyRejected as exc:
            return page(request, "borrowed", item=found, error=str(exc), status=400)

    # ------------------------------------------------------------ moving a profile's home to the phone
    @app.get("/profiles/receive")
    async def receive_page(request: Request):
        pending = devices.desk.pending if devices.desk is not None else None
        if pending is not None and pending.receive is None:
            pending = None
        return page(request, "receive", pending=pending, arrived=devices.arrived(),
                    address=devices.address() if devices.server is not None else "",
                    phone_name=devices.identity().name if devices.has_identity() else "My phone")

    @app.post("/profiles/receive")
    async def open_receive(request: Request):
        if session.container:
            return RedirectResponse("/profiles", 303)
        form = await request.form()
        name = " ".join(str(form.get("phone_name", "")).split())[:60]
        if not name:
            return page(request, "receive", error="Name this phone, so the PC can show it.", status=400,
                        phone_name="", pending=None, address="")
        try:
            open_move(devices, session.root, name)
        except OSError:
            return page(request, "receive", error="Another app is using the port Lightning listens on. Close it "
                                                  "and try again.", status=400, phone_name=name, pending=None,
                        address="")
        return RedirectResponse("/profiles/receive", 303)

    @app.post("/profiles/move")
    async def move(request: Request):
        from lightning.security.keys import key_id
        from lightning.sync.copies import ensure_profile_id, schema_version
        from lightning.sync.identity import normalize_code
        from lightning.sync.service import LinkDown
        if session.container is None or session.borrowed is not None or not session.role.writable:
            return RedirectResponse("/profiles", 303)
        form = await request.form()
        address, code = str(form.get("address", "")).strip(), str(form.get("code", ""))
        pc_name = " ".join(str(form.get("pc_name", "")).split())[:60] or "This PC"
        try:
            normalize_code(code)
        except ValueError as exc:
            return page(request, "manage", error=str(exc), status=400)
        db = session.container.db
        profile_id = ensure_profile_id(db)
        schema, kid, name, paths = schema_version(db), key_id(session.sync_key), session.name, session.paths
        session.close()  # the file is closed before it moves; this request holds the gate, so nothing reopens it
        app.state.container = None
        try:
            moved = await asyncio.to_thread(move_to_phone, devices, paths=paths, profile_id=profile_id, name=name,
                                            key_id=kid, schema=schema, address=address, code=code, pc_name=pc_name)
        except (LinkDown, ProtocolError, ValueError) as exc:
            return page(request, "unlock", selected=str(paths.db_path), status=400,
                        error=f"{exc} {name} stays on this PC; unlock it to try again.")
        return page(request, "choose", profiles=discover_profiles(session.root), borrowed=devices.borrowed(),
                    notice=f"{name} now lives on {moved.done.home_name}. Check that it shows {moved.digits[:3]} "
                           f"{moved.digits[3:]}. Borrow it here under From your phone; the PC's old copy is kept "
                           "as a backup.")

    @app.post("/profiles/hand-back")
    @app.post("/sync/hand-back")  # the finance pages' banner, which carries the session token
    async def hand_back(request: Request):
        node = session.borrowed
        if node is None:
            return RedirectResponse("/profiles", 303)
        name, home_name = session.name, session.borrowed_home or "your phone"
        session.close()  # the working copy closes before it is frozen and sent
        session.borrowed_home = ""
        app.state.container = None
        result = await asyncio.to_thread(devices.hand_back_or_seal, node)
        notices = {
            "accepted": f"{name} is back on {home_name}, with your changes.",
            "received": f"{home_name} has your changes and takes them in when it is unlocked. Until then this PC "
                        "keeps a read-only copy.",
            "sealed": f"{home_name} did not answer. Your changes are saved on this PC; open {name} here to keep "
                      "working, or hand it back when the phone is near.",
            "returning": f"Sending to {home_name} stopped halfway. Open {name} here near the phone to finish.",
            "unpaired": f"{home_name} no longer knows this PC. Your changes are saved here; pair this PC again on "
                        f"the phone (Devices), then open {name} here.",
            "refused": f"{home_name} took the ledger back, so this copy stays on this PC, read only. Open {name} "
                       "here to borrow again; the copy is kept as a backup.",
        }
        return page(request, "choose", notice=notices.get(result, ""), profiles=discover_profiles(session.root),
                    borrowed=devices.borrowed())

    secured = Guard(gate, credentials)
    secured.session = session  # Lifecycle tests inspect synthetic state only.
    secured.gate = gate  # The sync service (task 07) changes roles through gate.change_role.
    return secured
