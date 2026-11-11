"""The restore screens: restoring a backup, choosing a backup file, resuming an interrupted restore and going back
after a restore that needs checking (IT-9K, IT-2C). Moved out of `profile_app` unchanged, so `runtime/app.py` only
builds the app; a route here sees the session, `devices.blocks_restore` and the profile screens' `page`, nothing else."""
from __future__ import annotations

import asyncio
from urllib.parse import urlencode

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from .paths import discover_profiles
from .restore import NOT_THIS_PROFILES_BACKUP
from .session import ProfileError


def register(app, session, devices, page) -> None:
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
