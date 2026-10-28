"""PC and phone clocks may differ by up to 15 minutes and still pair; the home's own deadline decides."""
import os
from uuid import uuid4

import pytest

from test_journal_finance import devices  # noqa: F401  (fixture)
from test_journal_pairing import nearby
from lightning.sync.journal.codec import JournalError, seal, unpack
from lightning.sync.journal.pairing import MAX_CLOCK_DIFFERENCE, OFFER_SECONDS, ClocksDiffer, request_pairing


def _request(home, pc, offer, observed):
    return request_pairing(offer, "", pc.identity, str(uuid4()), home_key=home.identity.public_key,
                           secret=os.urandom(32), now=lambda: observed)


@pytest.mark.parametrize("difference", [30, 5 * 60, 14 * 60, -5 * 60, -14 * 60])
def test_a_fresh_offer_pairs_when_the_clocks_differ_by_less_than_fifteen_minutes(devices, difference):
    home, pc = devices
    desk, _ = nearby(devices)
    offer = desk._value("pairing")["offer"].encode()
    issued = unpack(offer)["body"]["expires"] - OFFER_SECONDS
    # A positive difference: the joining device's clock is behind the home's; negative: ahead.
    wire, _ = _request(home, pc, offer, issued - difference)
    desk.exchange(wire)
    assert desk.screen()["digits"] is None  # the home took it by its own clock


def test_clocks_an_hour_apart_are_named_and_an_old_offer_says_it_expired(devices):
    home, pc = devices
    desk, _ = nearby(devices)
    offer = desk._value("pairing")["offer"].encode()
    expiration = unpack(offer)["body"]["expires"]
    issued = expiration - OFFER_SECONDS
    for behind in (MAX_CLOCK_DIFFERENCE + 1, 60 * 60):
        with pytest.raises(ClocksDiffer, match="clocks on these devices differ"):
            _request(home, pc, offer, issued - behind)
    for ahead in (OFFER_SECONDS + MAX_CLOCK_DIFFERENCE, 60 * 60):
        with pytest.raises(JournalError, match="expired") as raised:
            _request(home, pc, offer, issued + ahead)
        assert not isinstance(raised.value, ClocksDiffer)
    malformed = unpack(offer)["body"] | {"expires": str(expiration)}
    with pytest.raises(JournalError):
        request_pairing(seal(malformed, home.identity.sign), "", pc.identity, str(uuid4()),
                        home_key=home.identity.public_key, secret=os.urandom(32))


def test_the_home_still_enforces_its_exact_deadline(devices):
    home, pc = devices
    desk, _ = nearby(devices)
    offer = desk._value("pairing")["offer"].encode()
    expiration = unpack(offer)["body"]["expires"]
    # The offer's ten minutes are up; the joining clock is ten minutes behind, so it still sees ten left...
    wire, _ = _request(home, pc, offer, expiration - 10 * 60)
    # ...but by the home's clock the offer has ended: the home refuses.
    desk.desk.clock = lambda: expiration
    with pytest.raises(JournalError, match="expired"):
        desk.exchange(wire)
