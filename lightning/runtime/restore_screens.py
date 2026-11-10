"""The restore screens: restoring a backup and resuming an interrupted restore (IT-9K). Moved out of `profile_app`
unchanged, so `runtime/app.py` only builds the app; a route here sees the session, `devices.blocks_restore` and the
profile screens' `page`, nothing else."""
from __future__ import annotations

from starlette.requests import Request
from starlette.responses import RedirectResponse

from .session import ProfileError


def register(app, session, devices, page) -> None:
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
