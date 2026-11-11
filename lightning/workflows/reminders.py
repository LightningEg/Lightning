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
        for certificate in c.deposits.open_certificates():  # IV-12J4: maturity and the earliest withdrawal day
            terms = certificate.terms
            href = f"/deposits/{terms.account_id}?redeem={terms.id}#certificate-{terms.id}"
            if terms.maturity_date == tomorrow.isoformat():
                items.append({"label": "Certificate matures tomorrow", "detail": terms.name, "href": href, "priority": 1})
            elif terms.lockup_end_date == tomorrow.isoformat() and terms.lockup_end_date != terms.start_date:
                items.append({"label": "Certificate can be withdrawn from tomorrow", "detail": terms.name, "href": href,
                              "priority": 2})
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

    def upcoming(self, days: int = 14) -> list[dict]:
        """NF-3AU2: what to announce over the next ``days`` days with the app closed, each dated the day before it is
        due, as ``{"day", "kind", "id"}``. Only days and kinds leave the profile (owner, 2026-11-08): the id is the
        same hash ``due()`` gives that reminder on its day, so the closed-app notice and the open app's never repeat
        each other, and it carries no name or figure. Payments (not income), gam'eya instalments and zakat day."""
        if not self.enabled:
            return []
        c, day = self.c, today()
        last = day + timedelta(days=days)
        found = []  # (reminder day, kind, href, label, detail): label and detail feed the hash only
        for payment in c.planning.all_payments(last + timedelta(days=1), day):
            due = parse_date(payment.due_date)
            if payment.outstanding and not payment.item.is_income and day < due <= last + timedelta(days=1):
                found.append((due - timedelta(days=1), "payment", f"/plan/items/{payment.item.id}/pay?due={payment.due_date}",
                              "Payment due tomorrow", payment.item.name))
        for circle, _terms in c.gameya.circles():
            next_date = c.gameya.progress(circle.id, day).next_date
            if next_date and day < parse_date(next_date) <= last + timedelta(days=1):
                found.append((parse_date(next_date) - timedelta(days=1), "gameya", f"/gameya/{circle.id}",
                              "Gam'eya instalment due tomorrow", circle.name))
        if c.zakat.enabled():
            zakat = c.zakat.forecast(day)
            if zakat and day < parse_date(str(zakat.day)) <= last + timedelta(days=1):
                found.append((parse_date(str(zakat.day)) - timedelta(days=1), "zakat", "/zakat",
                              "Zakat day is approaching", str(zakat.day)))
        profile_key = self._profile_key()
        result, seen = [], set()
        for when, kind, href, label, detail in sorted(found, key=lambda f: (f[0], f[1])):
            identity = sha256((profile_key + "\0" + when.isoformat() + "\0" + href
                               + "\0" + label + "\0" + detail).encode()).hexdigest()[:32]
            if identity not in seen:
                seen.add(identity)
                result.append({"day": when.isoformat(), "kind": kind, "id": identity})
        return result

    def profile_hash(self) -> str:
        """Which profile a schedule belongs to, without its name or path: a hash of its identity."""
        return sha256(("lightning-reminders\0" + self._profile_key()).encode()).hexdigest()[:32]

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
