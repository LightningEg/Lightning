"""Security boundaries when removing the manually copied bootstrap code."""
import asyncio
import os
from uuid import uuid4

import pytest

from test_journal_finance import devices
from test_journal_pairing import PASSWORD, nearby, started
from lightning.sync.journal import pairing
from lightning.sync.journal.codec import JournalError, unpack


def test_password_proof_cannot_admit_before_secret_reveal(devices):
    home, pc = devices
    desk, _ = nearby(devices)
    offer = desk._value("pairing")["offer"].encode()
    request, _ = pairing.request_pairing(offer, "", pc.identity, str(uuid4()),
                                        home_key=home.identity.public_key, secret=os.urandom(32))
    desk.exchange(request)
    proof = pairing.prove_pairing(offer, request, PASSWORD, pc.identity, home_key=home.identity.public_key)
    with pytest.raises(JournalError, match="No verified"):
        desk.exchange(proof)
    assert desk.screen()["digits"] is None
    assert not desk.screen()["confirmed"]
    assert pc.identity.device_id not in desk.membership.state()["members"]


def test_expired_matching_offer_cannot_advance_to_password(devices, monkeypatch):
    async def run():
        home, _, joiner = await started(devices)
        expiration = unpack(home._value("pairing")["offer"].encode())["body"]["expires"]
        monkeypatch.setattr(pairing.time, "time", lambda: expiration + 1)
        home.desk.clock = lambda: expiration + 1
        with pytest.raises(JournalError, match="expired"):
            joiner.compare(joiner.screen()["pending"])
        with pytest.raises(JournalError):
            await joiner.prove(PASSWORD)
        assert not home.screen()["code"]
    asyncio.run(run())


def test_removing_signed_matching_method_is_rejected_before_network(devices):
    home, pc = devices
    desk, _ = nearby(devices)
    offer = unpack(desk._value("pairing")["offer"].encode())
    del offer["body"]["method"]
    from lightning.sync.journal.codec import canonical
    with pytest.raises(JournalError):
        pairing.request_pairing(canonical(offer), "123456", pc.identity, str(uuid4()),
                                home_key=home.identity.public_key)
