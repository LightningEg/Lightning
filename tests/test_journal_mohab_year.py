"""The existing year-long acceptance journey through journal-backed app services."""
import os
from datetime import datetime, time, timezone
from uuid import uuid4

from lightning.bootstrap import build
from lightning.core import dates
from lightning.sync.identity import load_or_create
from lightning.sync.journal.device import JournalDevice
from lightning.sync.journal.finance import initialize
from lightning.sync.journal.home import JournalHome
from lightning.sync.journal.proxy import JournalServices
from test_mohab_year import Mohab, _live_the_year


def test_mohabs_year_uses_journal_commands_and_preserves_exact_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", os.environ.get("LIGHTNING_TODAY", ""))
    monkeypatch.setattr(dates, "_local_now", lambda: datetime.combine(dates.today(), time(12), timezone.utc))
    c = build(tmp_path / "mohab.db", key=os.urandom(32))
    c.budgets.set_emergency_basis("income")
    identity = load_or_create(tmp_path / "identity", "Home")
    store = initialize(c, profile=str(uuid4()), generation=str(uuid4()), device=identity.device_id,
                       incarnation=str(uuid4()), home_key=identity.public_key, origin_key=identity.public_key,
                       role="home", dummy_profile=True)
    home = JournalHome(store, identity.sign)
    home.approve_origin(identity.device_id, store.config["incarnation"], identity.public_key)
    device = JournalDevice(store, identity, home)
    try:
        _live_the_year(Mohab(JournalServices(device)))
        assert store.cursor()["revision"] > 0
        assert not store.pending()
        assert store.fingerprint() == store.adapter.fingerprint(full=True)
    finally:
        store.close()
