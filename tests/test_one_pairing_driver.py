"""IT-4K4: one joining-side pairing driver; the owner's three decisions (2026-11-02) are pinned for both clients."""
import asyncio

import pytest

from test_journal_finance import devices  # noqa: F401
from test_journal_pairing import nearby, started
from lightning.runtime.journal_enrollment import NewJournalReplica
from lightning.runtime.journal_pairing import NearbyPairing
from lightning.runtime.journal_pairing_driver import JoiningDriver
from lightning.sync.journal.codec import JournalError, unpack


def test_both_clients_share_the_one_driver_and_do_not_reimplement_it():
    for client in (NearbyPairing, NewJournalReplica):
        assert issubclass(client, JoiningDriver)
        for name in ("resume", "compare", "prove", "cancel"):
            assert name not in vars(client), f"{client.__name__}.{name} must come from the driver"


def test_resume_asks_the_home_for_status_while_waiting(devices):
    async def run():
        hs, make, pc = await started(devices)
        pc.compare(pc.screen()["pending"])
        state = pc._started()
        pc._save_join(dict(state, stage="waiting"))
        sent = []
        normal = pc.client_factory
        def spy(endpoint, certificate, timeout):
            request = normal(endpoint, certificate, timeout)
            async def exchange(wire):
                sent.append(unpack(wire)["body"]["type"])
                return await request(wire)
            return exchange
        pc.client_factory = spy
        await pc.resume()
        assert "journal-pairing-status" in sent
    asyncio.run(run())


def test_compare_checks_the_offer_before_the_failed_flag(devices, monkeypatch):
    async def run():
        hs, make, pc = await started(devices)
        pc._save_join(dict(pc._started(), failed=True))
        with pytest.raises(JournalError, match="Compare the numbers again"):
            pc.compare("000000")
        import lightning.sync.journal.pairing as module
        monkeypatch.setattr(module.time, "time", lambda: 4_000_000_000)
        with pytest.raises(JournalError) as error:
            pc.compare("000000")
        assert "Compare the numbers again" not in str(error.value)
    asyncio.run(run())


def test_cancel_and_finish_need_a_started_pairing(devices, tmp_path):
    async def run():
        hs, make = nearby(devices)
        pc = make()
        with pytest.raises(JournalError):
            await pc.cancel()
        with pytest.raises(JournalError):
            await pc.finish()
        fresh = NewJournalReplica(tmp_path / "fresh", "New laptop")
        with pytest.raises(JournalError):
            await fresh.cancel()
        with pytest.raises(JournalError):
            await fresh.finish("Pairing password")
    asyncio.run(run())
