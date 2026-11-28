import asyncio

from test_journal_area_plans import add_rent, plan, status
from test_journal_cloud import Carrier, peers
from test_journal_finance import devices  # noqa: F401
from lightning.sync.journal import legacy87
from lightning.sync.journal.codec import unpack


def test_schema_95_edit_waits_until_old_device_reconnects_after_updating(devices):
    home, replica = devices
    db = home.c.db
    db.conn.set_authorizer(None)
    db.execute("CREATE TABLE journal_wire_history(id INTEGER PRIMARY KEY, last_87 INTEGER NOT NULL)")
    db.execute("INSERT INTO journal_wire_history VALUES(1,-1)")
    db.conn.set_authorizer(home.adapter._authorize)
    loan = add_rent(home, kind="LOAN", name="Car loan", amount="3000.00", payment_count=24, principal="60000.00")
    record = unpack(loan)["body"]["record"]
    assert legacy87.fingerprint(home.adapter.rows) != home.store.fingerprint()
    rate = home.command("plans.set_loan_rate", item_id=record, interest_rate="10", rate_kind="FLAT")
    assert status(home, rate) == {"status": "staged", "reason": "peer-upgrade-needed"}
    assert plan(home, "Car loan").interest_rate is None
    hp, rp = peers(devices, Carrier())
    async def request(wire):
        return hp.channel.handle(wire)
    asyncio.run(rp.channel.synchronize(request, home_id=home.identity.device_id))
    assert status(home, rate)["status"] == "accepted"
    assert plan(replica, "Car loan").interest_rate == 10
    assert home.store.cursor() == replica.store.cursor()
    assert home.store.fingerprint() == replica.store.fingerprint()
