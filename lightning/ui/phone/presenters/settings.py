"""The phone's Settings page (templates/phone/settings/index.html, IV-11M8): the profile card's name and the day of the
newest backup, which the shared page does not work out."""
from __future__ import annotations

from datetime import datetime


def present(request, c, context: dict) -> dict:
    session = getattr(request.app.state, "profile_session", None)
    name = (getattr(session, "name", "") or "").strip()
    try:
        newest = max(path.stat().st_mtime for path in c.backup_files())
        last = datetime.fromtimestamp(newest).date().isoformat()
    except (ValueError, OSError):
        last = ""
    return {"profile_name": name, "last_backup_day": last}
