from fastapi import APIRouter, Request

from lightning.core.errors import LightningError
from ..web import container, redirect

router = APIRouter(prefix="/history")


@router.post("/{operation}")
async def replay(request: Request, operation: str):
    c = container(request)
    form = await request.form()
    back = str(form.get("back", "/"))
    if not back.startswith("/") or back.startswith("//") or "\\" in back or any(ord(char) < 32 for char in back):
        back = "/"
    if operation not in {"undo", "redo"} or c.undo is None:
        return redirect(back, "History is unavailable in this session.")
    try:
        group_id = int(str(form.get("group_id", "0")))
        if c.db.has_table("journal_meta"):
            import json
            config = json.loads(c.db.scalar("SELECT config FROM journal_meta WHERE id=1"))
            if config.get("role") != "home":
                return redirect(back, "Undo and redo are available on the journal home.")
            fingerprint = c.undo.current_fingerprint()
            c.undo.replay(redo=operation == "redo", expected_id=group_id,
                          expected_fingerprint=fingerprint)
        else:
            c.undo.replay(redo=operation == "redo", expected_id=group_id)
    except (LightningError, ValueError, c.db.IntegrityError) as exc:
        return redirect(back, getattr(exc, "message", "Choose an action from the current history."))
    return redirect("/", "Action redone." if operation == "redo" else "Action undone.")
