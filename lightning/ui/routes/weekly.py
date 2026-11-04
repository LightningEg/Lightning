from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from lightning.core.errors import LightningError
from lightning.workflows.weekly import WeeklyReview
from lightning.workflows.reminders import ReminderService
from ..i18n import translate
from ..web import container, redirect, render, settled_save

router = APIRouter()


@router.get("/review")
async def review(request: Request):
    c = container(request)
    return render(request, "review.html", review=WeeklyReview(c).snapshot(), reminders=ReminderService(c).enabled)


@router.post("/review/complete")
async def complete(request: Request):
    form = await request.form()
    try:
        if form.get("acknowledged") != "1":
            return redirect("/review", "Read the remaining decisions before recording this review.")
        WeeklyReview(container(request)).complete(str(form.get("fingerprint", "")))
    except LightningError as exc:
        return redirect("/review", exc.message)
    return redirect("/review", "Review recorded. Unresolved decisions remain in Needs you.")


@router.post("/review/rules/{identity}/dismiss")
async def dismiss(request: Request, identity: str):
    try:
        WeeklyReview(container(request)).dismiss(identity)
    except LightningError as exc:
        return redirect("/review", exc.message)
    return redirect("/review", "Rule suggestion dismissed.")


@router.post("/reminders/settings")
async def reminders_settings(request: Request):
    c = container(request)
    form = await request.form()
    with settled_save(request, c, undo_label='Reminder preference'):
        c.settings.set("reminders_enabled", "1" if form.get("enabled") == "1" else "0")
    return redirect("/review", "Reminder preference saved.")


@router.get("/reminders/due.json")
async def due_reminders(request: Request):
    c = getattr(request.app.state, "container", None)
    if c is None or c.db.closed or c.db.read_only:
        return JSONResponse({"enabled": False, "items": []}, headers={"Cache-Control": "no-store"})
    service = ReminderService(c)
    locale = c.settings.get("locale") or "en"
    items = [{**item, "label": translate(item["label"], locale), "detail": translate(item["detail"], locale)} for item in service.due()]
    return JSONResponse({"enabled": service.enabled, "items": items}, headers={"Cache-Control": "no-store"})
