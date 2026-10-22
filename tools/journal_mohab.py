"""Gauge for J6: live Mohab's year on an encrypted journal home through `proxy.JournalServices`.

Run `python tools/journal_mohab.py`. Prints the first failing step and every write the journal guard
denied (table and Mohab step line). The consolidated suite covers the same journey; this is a diagnostic runner.
"""
import os, sys, tempfile, traceback
from datetime import datetime, time, timezone
from pathlib import Path
from uuid import uuid4
sys.path[:0] = [os.getcwd(), os.path.join(os.getcwd(), "tests")]
import pytest
from lightning.core import dates
from lightning.bootstrap import build
from lightning.sync.identity import load_or_create
from lightning.sync.journal.device import JournalDevice
from lightning.sync.journal.finance import initialize
from lightning.sync.journal.home import JournalHome
from lightning.sync.journal.proxy import JournalServices
import test_mohab_year as m

root = Path(tempfile.mkdtemp())
pinned = os.environ.get("LIGHTNING_TODAY")
with pytest.MonkeyPatch.context() as patch:
    patch.setattr(dates, "_local_now", lambda: datetime.combine(dates.today(), time(12), timezone.utc))
    c = build(root / "mohab.db", key=os.urandom(32))
    c.budgets.set_emergency_basis("income")
    identity = load_or_create(root / "id", "Home")
    store = initialize(c, profile=str(uuid4()), generation=str(uuid4()), device=identity.device_id, incarnation=str(uuid4()),
                       home_key=identity.public_key, origin_key=identity.public_key, role="home", dummy_profile=True)
    home = JournalHome(store, identity.sign)
    home.approve_origin(identity.device_id, store.config["incarnation"], identity.public_key)
    device = JournalDevice(store, identity, home)
    person = m.Mohab(JournalServices(device))
    import sqlite3, traceback as tbm
    denials = []
    real = device.adapter._authorize
    def watched(action, table, *rest):
        result = real(action, table, *rest)
        if result == sqlite3.SQLITE_DENY:
            frame = next((f for f in reversed(tbm.extract_stack()) if f.filename.endswith("test_mohab_year.py")), None)
            denials.append((table, frame.lineno if frame else "?", frame.line if frame else ""))
        return result
    device.adapter._authorize = watched
    store.db.conn.set_authorizer(watched)
    try:
        m._live_the_year(person)
        print("MOHAB YEAR COMPLETED ON A JOURNAL HOME; commits:", store.cursor()["revision"])
    except BaseException as error:
        tb = traceback.extract_tb(error.__traceback__)
        step = next((f for f in reversed(tb) if f.filename.endswith("test_mohab_year.py")), None)
        print("FAILED at", step.lineno if step else "?", step.line if step else "", "|", type(error).__name__, str(error)[:400])
        print("commits so far:", store.cursor()["revision"], "| last page:", person.b.page.path if person.b.page else None)
        raise
    finally:
        os.environ["LIGHTNING_TODAY"] = pinned or ""
        seen = {}
        for table, line, code in denials:
            seen.setdefault((table, line), code)
        print("DENIED writes (table, step line):", len(denials))
        for (table, line), code in list(seen.items())[:15]:
            print("  ", table, line, (code or "")[:90])
