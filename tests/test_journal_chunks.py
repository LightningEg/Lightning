"""A large action (an import) travels as hashed chunks beside its commit."""
import asyncio
import os

import pytest

from test_journal_finance import devices
from lightning.sync.journal.codec import unpack
from lightning.sync.journal.local import LocalChannel
from lightning.sync.journal.proxy import JournalServices


def many_payments(hd, count):
    """One home action posting many transactions at once: a bulk recategorize after many entries."""
    services = JournalServices(hd)
    bank = next(a.id for a in hd.c.accounts.list() if a.name == "Bank")
    food = hd.c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    health = hd.c.categories.get_by_code("EXP.PERSONAL.HEALTH").id
    ids = [services.transactions.record_in_account(bank, "2026-09-01", f"-{n % 9 + 1}", category_id=food).id for n in range(count)]
    services.transactions.set_category(ids, health)
    last = unpack(hd.store.db.scalar("SELECT wire FROM journal_commits ORDER BY revision DESC LIMIT 1"))["body"]
    return last["effects"][0]["domain"]


def test_a_large_effect_is_chunked_and_replays_in_process(devices):
    hd, pc = devices
    domain = many_payments(hd, 60)
    assert "chunks" in domain and len(domain["chunks"]) >= 2
    pc.sync_with(hd.home)
    assert hd.store.fingerprint() == pc.store.fingerprint() == pc.adapter.fingerprint(full=True)


def test_a_large_effect_crosses_the_local_link_in_bounded_rounds(devices):
    hd, pc = devices
    many_payments(hd, 60)
    secret = os.urandom(32)
    home_channel = LocalChannel(hd, transport_key=secret, peers={pc.identity.device_id: pc.identity.public_key})
    pc_channel = LocalChannel(pc, transport_key=secret, peers={hd.identity.device_id: hd.identity.public_key})
    sizes = []
    async def request(wire):
        sizes.append(len(wire))
        reply = home_channel.handle(wire)
        sizes.append(len(reply))
        return reply
    asyncio.run(pc_channel.synchronize(request, home_id=hd.identity.device_id))
    assert max(sizes) <= 64 * 1024
    assert hd.store.fingerprint() == pc.store.fingerprint()


def test_a_chunk_nobody_asked_for_or_a_damaged_one_is_refused(devices):
    hd, pc = devices
    from lightning.sync.journal.codec import JournalError
    with pytest.raises(JournalError):
        pc.store.put_chunk(b"[]", ["0" * 64])
