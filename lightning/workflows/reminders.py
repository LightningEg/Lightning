"""Opt-in reminders over existing plans and the review inbox; nothing is posted."""
from datetime import timedelta
from hashlib import sha256
from pathlib import Path

from lightning.core.dates import parse_date, today
from lightning.workflows.review import ReviewInbox


class ReminderService:
    def __init__(self, c):
        self.c = c

    @property
    def enabled(self):
        return self.c.settings.get("reminders_enabled") == "1" and not self.c.db.read_only and not self.c.db.closed

    def due(self):
        if not self.enabled:
            return []
        c, day = self.c, today()
        tomorrow = day + timedelta(days=1)
        # Home's glance holds Decimals and is the phone's; a reminder is its label and detail (due.json).
        items = [{k: v for k, v in item.items() if k != "glance"} for item in ReviewInbox(c).items(day) if item["priority"] <= 1]
        for payment in c.planning.all_payments(tomorrow, day):
            if payment.outstanding and not payment.item.is_income and payment.due_date == tomorrow.isoformat():
                items.append({"label": "Payment due tomorrow", "detail": payment.item.name,
                              "href": f"/plan/items/{payment.item.id}/pay?due={payment.due_date}", "priority": 1})
        for circle, terms in c.gameya.circles():
            progress = c.gameya.progress(circle.id, day)
            if progress.next_date == tomorrow.isoformat():
                items.append({"label": "Gam'eya instalment due tomorrow", "detail": circle.name,
                              "href": f"/gameya/{circle.id}", "priority": 1})
        for event in c.deposits.future_events(day, tomorrow):
            if getattr(event, "source", "CD") == "CD" and event.kind == "INTEREST":
                items.append({"label": "Certificate interest expected tomorrow", "detail": event.date,
                              "href": f"/deposits/{event.deposit_account_id}", "priority": 2})
        if c.zakat.enabled():
            zakat = c.zakat.forecast(day)
            if zakat and day.isoformat() <= str(zakat.day) <= tomorrow.isoformat():
                items.append({"label": "Zakat day is approaching", "detail": str(zakat.day), "href": "/zakat", "priority": 1})
        last = c.settings.get("weekly_review_at")
        if not last or (day - parse_date(last[:10])).days >= 7:
            items.append({"label": "Weekly review is ready", "detail": "Review pending decisions and record your progress.",
                          "href": "/review", "priority": 2})
        backups = c.backup_files()
        if backups:
            from datetime import datetime
            latest = max(datetime.fromtimestamp(path.stat().st_mtime).date() for path in backups)
            old_backup = (day - latest).days >= 14
        else:
            old_backup = True
        if old_backup:
            items.append({"label": "A fresh backup is due", "detail": "Keep a recent copy of your records.",
                          "href": "/settings?section=data", "priority": 1})
        profile_key = self._profile_key()
        seen, result = set(), []
        for item in items:
            identity = sha256((profile_key + "\0" + day.isoformat() + "\0" + item["href"]
                               + "\0" + item["label"] + "\0" + item["detail"]).encode()).hexdigest()[:32]
            if identity not in seen:
                seen.add(identity)
                result.append({"id": identity, "label": item["label"], "detail": item["detail"], "href": item["href"]})
        return result

    def _profile_key(self):
        """Give native per-day dedupe a stable profile scope, with a path fallback for legacy databases."""
        db = self.c.db
        try:
            if db.has_table("profile_identity"):
                row = db.one("SELECT profile_id FROM profile_identity WHERE singleton=1")
                if row and row["profile_id"]:
                    return str(row["profile_id"])
        except Exception:
            # A profile may predate persistent identity, or be closing while the UI stays fail-closed.
            pass
        return str(Path(db.path).expanduser().resolve())
