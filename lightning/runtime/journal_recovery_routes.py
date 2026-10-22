"""Explicit recovery of saved edits after pairing a fresh device incarnation."""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from lightning.sync.journal.codec import JournalError

_views = Jinja2Templates(directory=str(Path(__file__).parents[1] / "ui" / "templates"))


def journal_recovery_router(session):
    router = APIRouter()

    def choices():
        result = {}
        for profile in Path(session.root).iterdir():
            folder = profile / "backups"
            if profile.is_symlink() or folder.is_symlink() or not folder.is_dir():
                continue
            for manifest in folder.glob("*.journal-manifest.json"):
                source = manifest.with_name(manifest.name.removesuffix(".journal-manifest.json") + ".db")
                if source.is_file() and not source.is_symlink() and not manifest.is_symlink():
                    result[f"{profile.name} / {source.name}"] = (source, manifest)
        return result

    def render(request, message="", error=""):
        locale = request.cookies.get("lightning_ui_locale", "en")
        return _views.TemplateResponse(request=request, name="journal/journal_recovery.html", context=dict(
            locale=locale if locale in ("en", "ar") else "en", token=session.token,
            options=[dict(id=key, label=key) for key, value in choices().items()],
            available=session.journal is not None and session.journal.device.home is None,
            message=message, error=error))

    @router.get("/journal/recover")
    async def recover_page(request: Request):
        if session.journal is None:
            return RedirectResponse("/profiles/journal/join", 303)
        return render(request)

    @router.post("/journal/recover")
    async def recover(request: Request):
        from lightning.sync.journal.backups import repropose_copy
        if session.journal is None:
            return RedirectResponse("/profiles", 303)
        form = await request.form(max_files=0, max_fields=4)
        try:
            if form.get("confirmed") != "yes":
                raise JournalError("Confirm recovery of saved edits before continuing.")
            selected = choices().get(str(form.get("backup", "")))
            if selected is None:
                raise JournalError("Choose a signed backup from this app's profiles.")
            source, manifest = selected
            result = repropose_copy(session.journal.device, source, manifest.read_bytes(),
                                    backup_key=session.container.db.copy_key())
            return render(request, message=f"{result['reproposed']} edits queued; {result['already_decided']} already decided; {result['held']} need review.")
        except (JournalError, OSError, ValueError) as error:
            return render(request, error=str(error))

    return router
