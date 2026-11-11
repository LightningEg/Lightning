"""Profile screens and serialized access to the existing finance application."""
from __future__ import annotations

import asyncio
import re
import time
from contextlib import suppress
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response

from lightning.core.limits import MAX_WORKSHEET_REQUEST_BYTES, MAX_STATEMENT_UPLOAD_FILES
from lightning.sync.state import ProtocolError
from lightning.ui.web import create_app

from .http import (MARKET_IMPORT_PATH, PRICE_CSV_PATH, MAX_IMPORT_CONFIRM_BODY, MAX_IMPORT_CONFIRM_FIELDS, MAX_MARKET_IMPORT_BODY,
                   MAX_IMPORT_MAP_BODY, PROFILE_FILE_PATH, Credentials, Guard,
                   body_receiver, configure_memory_only_import_uploads, equal)
from .devices import Devices, home_state_line, home_state_message, move_to_phone, open_move
from .paths import discover_profiles
from .restore import NOT_THIS_PROFILES_BACKUP
from .profile_screens import ProfileScreens, register as register_profile_screens
from .roles import READ_ONLY_REFUSAL

READ_ONLY_PATH = "/__read-only"
from .session import AttemptGuard, ProfileError, ProfileSession

_DEFAULT_FORM_FIELDS = 2_000
_IMPORT_CONFIRM_FORM_FIELDS = MAX_IMPORT_CONFIRM_FIELDS


def _form_field_limit(path: str) -> int:
    if re.fullmatch(r"/accounts/\d+/import/sheets", path):
        return 100
    if re.fullmatch(r"/accounts/\d+/import/\d+/confirm", path):
        return _IMPORT_CONFIRM_FORM_FIELDS
    return _DEFAULT_FORM_FIELDS


def _form_part_limit(path: str) -> int:
    if re.fullmatch(r"/accounts/\d+/import/sheets", path):
        return MAX_WORKSHEET_REQUEST_BYTES
    # The mapping page carries the CSV as base64 in one multipart text field.
    if re.fullmatch(r"/accounts/\d+/import/map", path):
        return MAX_IMPORT_MAP_BODY
    # A large CSV can include a correspondingly long notes cell in one review row.
    if re.fullmatch(r"/accounts/\d+/import/\d+/confirm", path):
        return MAX_IMPORT_CONFIRM_BODY
    if path == MARKET_IMPORT_PATH:
        return MAX_MARKET_IMPORT_BODY
    if path == PRICE_CSV_PATH:
        return MAX_IMPORT_MAP_BODY
    return 512 * 1024


def _form_file_limit(path: str) -> int:
    # Only the initial CSV upload, the market price file, the price CSV and "Open a profile file" accept a file
    # part. Rejecting files on every other form avoids creating spooled temporary files on those routes.
    if re.fullmatch(r"/accounts/\d+/import", path):
        return MAX_STATEMENT_UPLOAD_FILES
    return 1 if path in (MARKET_IMPORT_PATH, PRICE_CSV_PATH, PROFILE_FILE_PATH) else 0


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

    def device_line(self) -> tuple[str, str, dict]:
        """The status line under the header while a ledger is borrowed or lent, and its action.

        The line is an i18n template; ``values`` holds the placeholders (for example ``name``).
        """
        devices, session = getattr(self, "devices", None), self.session
        if session.journal is not None:
            runtime = session.journal
            pending = len(runtime.store.pending())
            return (f"{pending} edits waiting for the home" if pending else "Synchronized profile", "", {})
        if devices is None or session.paths is None:
            return "", "", {}
        if session.borrowed is not None:
            if session.role.writable:
                if session.borrowed_home:
                    return "Borrowed from {name}", "hand-back", {"name": session.borrowed_home}
                return "Borrowed from your phone", "hand-back", {}
            return "Read only on this PC: the ledger is going home or needs repair.", "", {}
        try:
            lending = devices.lending_state(session.paths)
            line, values = home_state_message(devices.home_node(session.paths) if lending == "ok" else None, lending)
        except Exception:  # noqa: BLE001 - an unreadable record shows as needing the Devices page
            line, values = "The ledger's lending record needs checking.", {}
        return line, ("take-back" if line else ""), values

    def outside_row(self, path: str):
        """For the phone's Settings › Backup: None when the phone cannot keep a copy outside the app, else its
        status (BT-2AI3). Loading Settings or Home is also when a due copy is written, at most once a day."""
        outside = getattr(self, "outside", None)
        if outside is None or path not in ("/", "/settings") or self.session.container is None:
            return None
        try:
            outside.keep(self.session)
            profile = self.session.paths.profile if self.session.paths is not None else None
            return outside.status(profile.profile_id if profile is not None else "") if path == "/settings" else None
        except Exception:  # noqa: BLE001 - a bridge that cannot answer offers no row
            return None

    async def change_role(self, role) -> None:
        """Change the open profile's role between requests, never during one (multi-device task 06)."""
        async with self.mutex:
            try:
                self.session.change_role(role)
            finally:
                self.app.state.container = self.session.container

    def recents_row(self, path: str) -> str:
        """For Settings › This phone: "" when the phone has no Recents switch, else "on" (hidden) or "off"."""
        recents = getattr(self, "recents", None)
        if path != "/settings" or recents is None:
            return ""
        try:
            return "on" if recents.hidden() else "off"
        except Exception:  # noqa: BLE001 - a bridge that cannot answer offers no row
            return ""

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
        path = scope.get("path", "")
        if path.startswith("/static/") and scope["method"] in ("GET", "HEAD"):
            # Stylesheets, scripts and fonts never touch the ledger (backend roadmap B3): they no longer wait
            # behind a slow page, so a phone's page paints while its numbers are still being worked out.
            scope.setdefault("state", {}).update(phone=getattr(self, "phone", False))
            return await self.app(scope, receive, send)
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
                line, _, values = self.device_line()
                line = line.format(**values) if values else line
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
                selected = ""
                try:
                    async with parsed.form(max_files=_form_file_limit(request.url.path),
                                           max_fields=_form_field_limit(request.url.path),
                                           max_part_size=_form_part_limit(request.url.path)) as form:
                        token = form.get("csrf" if profile_route else "__session", "")
                        expected = self.session.csrf if profile_route else self.session.token
                        valid = isinstance(token, str) and equal(token, expected)
                        selected = str(form.get("db", ""))
                except Exception:
                    valid = False
                if not valid and request.url.path == "/profiles/unlock":
                    # The unlock form sent twice (Enter and a click): the first opened the profile and renewed the
                    # token. Open the app, or show the form again with the password empty, never an error (2AC).
                    if self.session.container is not None:
                        return await RedirectResponse("/", 303)(scope, receive, send)
                    again = "/profiles/unlock" + (f"?{urlencode({'db': selected})}" if selected else "")
                    return await RedirectResponse(again, 303)(scope, receive, send)
                if not valid:
                    return await PlainTextResponse("This form expired. Reload the page and try again.", 403)(scope, receive, send)
            line, device_action, device_values = self.device_line()
            scope.setdefault("state", {}).update(fingerprint_row=self.fingerprint_row(request.url.path),
                                                  recents_row=self.recents_row(request.url.path),
                                                  outside_row=self.outside_row(request.url.path) if scope["method"] == "GET" else None,
                                                  secure_profiles=True, csrf=self.session.csrf,
                                                  phone=getattr(self, "phone", False),
                                                  session_token=self.session.token,
                                                  read_only=not self.session.role.writable,
                                                  device_line=line, device_action=device_action,
                                                  device_line_values=device_values)
            self.app.state.container = self.session.container
            updates = getattr(self, "updates", None)
            if updates is not None and scope["method"] == "GET" and request.url.path in ("/", "/profiles"):
                updates.chooser_loaded()  # the new version reached its chooser: the helper may stop waiting
            if self.session.journal is not None and self.session.journal.task is None:
                self.session.journal.start(self, files_dir=self.session.root.parent if getattr(self, "phone", False) else None)
            if self.session.container is not None and request.url.path != "/profiles/health" and not request.url.path.startswith("/static/"):
                self.session.last_activity = time.monotonic()
            await self.app(scope, receive, send)


def profile_app(credentials: Credentials, root: Path | str | None = None, devices: Devices | None = None,
                *, phone: bool = False, sms=None, biometric=None, stay=None, files=None, updates=None, recents=None,
                billing=None, outside=None):
    """`phone`: the Android app, whose pages use the phone frame and screens (guideline Part C). `sms`: where
    bank messages come from on that phone (`lightning.sms_imports.SmsSource`), or None. `biometric`: the phone's
    optional fingerprint unlock (`lightning.security.biometric.FingerprintUnlock`), or None: never on a PC.
    `stay`: staying signed in on the phone (the same slots over `StayBridge`, no prompt), or None: never on a PC.
    `files`: where the phone saves downloads (`lightning.runtime.phone_files.FileSaver`), or None.
    `updates`: the Windows app's `UpdateController` (Settings › Lightning version), or None: never elsewhere.
    `recents`: the phone's "Hide in recent apps" switch (`hidden()`, `set_hidden(bool)`; NF-11B6), or None.
    `billing`: Google Play Billing in the Play build (`lightning.ui.play_store.PlayBilling`), or None: the GitHub APK and
    the PC sell themes on the website instead. `outside`: the phone's copy outside the app
    (`lightning.runtime.outside_copy.OutsideCopy`; BT-2AI3), or None."""
    configure_memory_only_import_uploads()
    session = ProfileSession(root)
    session.borrowed_home = ""
    app = create_app(None)
    if phone:
        from lightning.ui.phone.router import mount_phone
        mount_phone(app)  # the phone's own routes first (3AY4); the shared routes answer what it does not own
    app.state.profile_session = session
    from .journal_ui_routes import journal_ui_router
    from .journal_enrollment_routes import journal_enrollment_router
    from .journal_setup_routes import journal_setup_router
    from .journal_recovery_routes import journal_recovery_router
    app.include_router(journal_ui_router(session))
    app.include_router(journal_enrollment_router(session))
    app.include_router(journal_recovery_router(session))
    app.state.sms_source = sms
    app.state.play_billing = billing if phone else None
    if phone and files is not None:
        from .phone_files import PhoneSaves
        gate = SessionGate(PhoneSaves(app, files), session)  # inside the gate: only authorized files (2F)
    else:
        gate = SessionGate(app, session)
    devices = devices if devices is not None else Devices()
    app.include_router(journal_setup_router(session, devices))
    gate.devices = devices
    gate.phone = phone
    app.state.updates = updates
    gate.updates = updates
    if updates is not None:  # what only the profile app knows: how to lock, and what is borrowed
        updates.devices, updates.lock_profile = devices, session.close
        updates.profiles_root, updates.borrowed_root = session.root, devices.root / "borrowed"
    fingerprint = biometric if phone else None
    gate.fingerprint = fingerprint
    gate.recents = recents if phone else None
    gate.outside = outside if phone else None
    # Stay signed in (owner, 2026-11-01): the phone opens the profile by itself until Lock, and never locks for idling.
    kept = stay if phone else None

    def open_profile_id() -> str:
        if session.container is None or session.paths is None or session.paths.profile is None:
            return ""
        return session.paths.profile.profile_id

    def kept_on() -> bool:
        profile_id = open_profile_id()
        return kept is not None and bool(profile_id) and kept.enabled(profile_id)

    def keep_signed_in(form) -> None:
        """After an unlock on the phone: "Stay signed in" ticked wraps the data key in a Keystore key that needs no
        fingerprint (only an unlocked phone); unticked removes it. A read-only copy is never kept."""
        profile_id = open_profile_id()
        if kept is None or not profile_id or not session.role.writable or session.data_key is None:
            return
        if form.get("stay") == "yes":
            kept.enrol(profile_id, session.data_key)
        else:
            kept.disable(profile_id)

    async def open_kept(found) -> bool:
        """Opening the app on the phone: a profile kept signed in opens without its password. Anything that does
        not work (the phone is locked, the key changed) leaves the profile list, as before."""
        from lightning.security.biometric import Outcome
        if kept is None or session.container is not None:
            return False
        for info in found:
            selected = str(info.db_path)
            try:
                profile_id, ident = session.fingerprint_target(selected)
            except (ProfileError, OSError, ValueError):
                continue
            if not profile_id or not kept.enabled(profile_id) or devices.role_for(selected) == "reader":
                continue
            result = await asyncio.to_thread(kept.unlock, profile_id, ident)
            if result.outcome is not Outcome.OK:
                continue
            try:
                session.unlock_with_key(selected, result.key)
                if session.journal is None:
                    devices.after_unlock(session.paths)
            except ProfileError:
                continue
            app.state.container = session.container
            return True
        return False

    async def expire_sessions():
        while True:
            await asyncio.sleep(1)
            async with gate.mutex:
                if session.pending and time.monotonic() >= session.pending.expires:
                    session.pending = None
                if (session.container and time.monotonic() - session.last_activity >= session.idle_seconds
                        and not kept_on()):
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

    screens = register_profile_screens(app, ProfileScreens(session, devices, gate, fingerprint, kept, open_kept, keep_signed_in))
    page, action = screens.page, screens.action

    def known_profile(selected: str) -> str:
        """The database path of a profile Lightning itself found in the profiles folder that ``selected`` names.
        The new restore routes (IT-2C3, 2C4) pass on this enumerated path, never the text of the request."""
        try:
            found = discover_profiles(session.root) if selected and len(selected) <= 4096 else []
        except (OSError, ValueError):
            found = []
        for info in found:  # plain text compared with what was found; the request's text never touches the disk
            if selected in (str(info.db_path), str(info.db_path.resolve())):
                return str(info.db_path)
        raise ProfileError("Restore requires a named Lightning profile.")

    @app.get("/profiles/restore")
    async def restore_page(request: Request):
        if session.container:
            return RedirectResponse("/profiles", 303)
        return page(request, "restore", selected=request.query_params.get("db", ""),
                    backup=request.query_params.get("backup", ""))

    @app.post("/profiles/restore/pick")
    async def restore_pick(request: Request):
        """Choose a backup file… (IT-2C3): the Windows Open dialog, opened by Python. The chosen file is copied into
        this profile's backups and goes through the ordinary restore, which checks it with the profile's key."""
        from lightning.runtime import file_picker
        picker = file_picker.current()
        if picker is None:
            return Response(status_code=404)
        if session.container:
            return RedirectResponse("/profiles", 303)
        form = await request.form()
        selected = str(form.get("db", ""))
        try:
            paths = session._select(known_profile(selected))
            if paths.profile is None:
                raise ProfileError("Restore requires a named Lightning profile.")
        except ProfileError as exc:
            return page(request, "restore", status=400, selected=selected, error=str(exc), can_pick=True)
        chosen = await asyncio.to_thread(picker)
        if not chosen:
            return RedirectResponse("/profiles/restore?" + urlencode({"db": selected}), 303)
        try:
            copied = file_picker.copy_into_backups(chosen, paths.backups_dir, paths.db_path)
        except (OSError, ValueError):
            return page(request, "restore", status=400, selected=selected, can_pick=True,
                        error="That file could not be read as a backup. Choose another file.")
        return RedirectResponse("/profiles/restore?" + urlencode({"db": selected, "backup": str(copied)}), 303)

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
            if str(exc) == NOT_THIS_PROFILES_BACKUP and backup_path.endswith("_picked.db"):
                backup_path = ""  # the restorer removed that copy
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

    @app.get("/profiles/restore/repair")
    async def repair_restore_page(request: Request):
        """Restore needs checking (IT-2C4): the kept files and their check, and the way back to the copy from before."""
        if session.container:
            return RedirectResponse("/profiles", 303)
        selected = request.query_params.get("db", "")
        try:
            evidence = session.restore_evidence(known_profile(selected))
        except ProfileError as exc:
            return page(request, "repair-restore", status=400, selected=selected, error=str(exc))
        return page(request, "repair-restore", selected=selected, evidence=evidence)

    @app.post("/profiles/restore/repair")
    async def repair_restore(request: Request):
        form = await request.form()
        selected = str(form.get("db", ""))
        try:
            known = known_profile(selected)
        except ProfileError as exc:
            return page(request, "repair-restore", status=400, selected=selected, error=str(exc))

        def again(error: str):
            try:
                evidence = session.restore_evidence(known)
            except ProfileError:
                evidence = []
            return page(request, "repair-restore", status=400, selected=selected, evidence=evidence, error=error)
        if devices.blocks_restore(known):
            return again("This profile is lent to a PC or has a hand-back to finish. Bring the ledger home first (Devices).")
        if form.get("confirm") != "yes":
            return again("Confirm that Lightning should go back to the copy from before the restore.")
        try:
            session.go_back_before_restore(known, str(form.get("password", "")))
        except ProfileError as exc:
            return again(str(exc))
        except Exception:
            return again("Going back could not finish. The profile remains locked and every file was kept.")
        return page(request, "unlock", selected=known,
                    notice="Back to the copy from before the restore. The other files were kept in a restore-evidence folder. Unlock this profile to check it.")

    @app.post("/profiles/recents")
    async def recents_switch(request: Request):
        """Settings › This phone › Hide in recent apps (NF-11B6): on by default; a phone setting, not the profile's,
        so it holds while the profile is locked too."""
        if gate.recents is not None:
            form = await request.form()
            gate.recents.set_hidden("1" in form.getlist("on"))
        return RedirectResponse("/settings" if session.container else "/profiles", 303)

    @app.post("/profiles/outside-copy")
    async def outside_copy(request: Request):
        """Settings › Backup › Keep a copy outside the app (BT-2AI3): choose the folder, or stop. A phone setting:
        the folder belongs to the phone, not to one profile."""
        if gate.outside is not None:
            form = await request.form()
            if form.get("action") == "stop":
                gate.outside.stop()
            else:
                gate.outside.choose()
        return RedirectResponse("/settings" if session.container else "/profiles", 303)

    @app.post("/profiles/lock")
    async def lock(request: Request):
        if session.borrowed is not None:
            return await hand_back(request)
        if kept is not None and open_profile_id():
            kept.disable(open_profile_id())  # Lock is signing out: the next open asks for the password
        if session.container is not None:  # NF-3AU2: what is due while locked is announced from the schedule
            from lightning.workflows import reminder_schedule
            reminder_schedule.refresh(session.container, force=True)
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
        from lightning.runtime.paths import borrowed_profile
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
            node = await asyncio.to_thread(join_home, paired, endpoint=address, identity=identity,
                                          borrowed_profile=borrowed_profile, root=devices.root)
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
