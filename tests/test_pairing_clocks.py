"""A small PC/phone clock difference must not reject every fresh offer."""
import os
from uuid import uuid4

import pytest

from test_journal_finance import devices
from test_journal_pairing import nearby
from lightning.sync.journal.codec import JournalError, seal, unpack
from lightning.sync.journal.pairing import request_pairing


def test_fresh_offer_tolerates_small_positive_home_clock_skew(devices):
    home, pc = devices
    desk, _ = nearby(devices)
    offer = desk._value("pairing")["offer"].encode()
    expiration = unpack(offer)["body"]["expires"]
    # The home generated the offer thirty seconds ahead of the PC clock.
    wire, _ = request_pairing(offer, "", pc.identity, str(uuid4()), home_key=home.identity.public_key,
                             secret=os.urandom(32), now=lambda: expiration - 630)
    desk.exchange(wire)
    assert desk.screen()["digits"] is None
    for observed in (expiration + 1, expiration - 700):
        with pytest.raises(JournalError, match="expired"):
            request_pairing(offer, "", pc.identity, str(uuid4()), home_key=home.identity.public_key,
                            secret=os.urandom(32), now=lambda: observed)
    malformed = unpack(offer)["body"] | {"expires": str(expiration)}
    with pytest.raises(JournalError):
        request_pairing(seal(malformed, home.identity.sign), "", pc.identity, str(uuid4()),
                        home_key=home.identity.public_key, secret=os.urandom(32))
