"""Number matching commits both peers before revealing a transcript number."""
import asyncio
import hashlib
import os
from uuid import uuid4

import pytest

from test_journal_finance import devices
from test_journal_pairing import PASSWORD, home_candidate, nearby, started
from lightning.runtime.journal_enrollment import NewJournalReplica
from lightning.sync.journal.codec import JournalError, digest, seal, unpack
from lightning.sync.journal.pairing import complete_number_match, request_pairing


def test_public_request_cannot_choose_number_after_the_home_challenge(devices):
    home, pc = devices
    hs, _ = nearby(devices)
    offer = hs._value("pairing")["offer"].encode()
    secret = os.urandom(32)
    wire, digits = request_pairing(offer, "", pc.identity, str(uuid4()), home_key=home.identity.public_key, secret=secret)
    assert digits is None
    assert unpack(wire)["body"]["commitment"] == hashlib.sha256(secret).hexdigest()
    first = unpack(hs.exchange(wire))
    challenge = first["body"]["challenge"]
    assert hs.screen()["digits"] is None
    assert unpack(hs.exchange(wire))["body"]["challenge"] == challenge
    with pytest.raises(JournalError):
        hs.confirm("123456")
    reveal = dict(type="journal-pairing-reveal",request=digest(unpack(wire)["body"]),challenge=challenge,secret=(b"x"*32).hex())
    with pytest.raises(JournalError,match="transcript"):
        hs.exchange(seal(reveal,pc.identity.sign))
    assert hs.screen()["digits"] is None
    async def run():
        async def exchange(message):
            return hs.exchange(message)
        result = await complete_number_match(offer,wire,first,secret,pc.identity,exchange)
        assert result == hs.screen()["digits"]
        # A substituted challenge cannot be replayed into the reserved request.
        changed = dict(reveal,secret=secret.hex(),challenge="0"*64)
        with pytest.raises(JournalError,match="transcript"):
            hs.exchange(seal(changed,pc.identity.sign))
    asyncio.run(run())


def test_choices_persist_across_refresh_and_wrong_choice_cannot_be_retried(devices):
    async def run():
        hs, make, ps = await started(devices)
        screen = ps.screen()
        choices = screen["choices"]
        assert len(choices) == len(set(choices)) == 3
        assert all(len(choice)==6 and choice.isascii() and choice.isdigit() for choice in choices)
        assert choices.count(hs.screen()["digits"]) == 1
        assert make().screen()["choices"] == choices
        wrong = next(choice for choice in choices if choice != screen["pending"])
        with pytest.raises(JournalError):
            ps.compare(wrong)
        with pytest.raises(JournalError):
            ps.compare(screen["pending"])
        with pytest.raises(JournalError):
            await ps.prove(PASSWORD)
    asyncio.run(run())


def test_legacy_saved_comparison_gets_persistent_choices(devices):
    async def run():
        _, make, ps = await started(devices)
        state = ps._value("pairing_client")
        del state["choices"]
        ps._save("pairing_client",state)
        choices = make().screen()["choices"]
        assert len(choices) == 3
        assert make().screen()["choices"] == choices
    asyncio.run(run())
