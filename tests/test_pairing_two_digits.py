"""NF-4N: two typed digits confirm a bounded, signed handshake; never replace approval or password proof."""
import asyncio

import pytest

from test_journal_finance import devices  # noqa: F401
from test_journal_pairing import PASSWORD, admitted, nearby, other_digits, started
from lightning.runtime.journal_pairing import NearbyPairing
from lightning.sync.journal.codec import JournalError, unpack
from lightning.sync.journal.pairing import normalize_matching_digits


@pytest.mark.parametrize(("typed", "expected"), [("00", "00"), ("٠٧", "07"), ("۰۷", "07"), (" 09 ", "09")])
def test_two_digit_input_preserves_zero_and_accepts_arabic_keyboards(typed, expected):
    assert normalize_matching_digits(typed) == expected


@pytest.mark.parametrize("typed", [None, 7, "", "7", "007", "12.0", "a7", "1 2", "１２", "²³"])
def test_two_digit_input_refuses_other_shapes(typed):
    with pytest.raises(JournalError, match="two digits"):
        normalize_matching_digits(typed)


def test_two_digits_are_bound_to_the_offer_and_keep_both_admission_gates(devices, monkeypatch):
    # Deliberately exercise a leading zero; the protocol still exchanges real signed messages.
    monkeypatch.setattr("lightning.sync.journal.pairing.check_digits", lambda value: "123400")
    home, pc = devices

    async def run():
        wires = []
        hs, _, ps = await started(devices, wires)
        assert ps.screen()["pending"] == hs.screen()["digits"] == "00"
        assert ps.screen()["typed_digits"] and ps.screen()["choices"] == []
        assert [unpack(wire)["body"]["type"] for wire in wires] == [
            "journal-pairing-request", "journal-pairing-reveal"]
        with pytest.raises(JournalError, match="Compare"):
            await ps.prove(PASSWORD)
        assert len(wires) == 2 and admitted(home, pc) == 0
        ps.compare("٠٠")
        await ps.prove(PASSWORD)
        assert admitted(home, pc) == 0  # a correct password still needs named home approval
        hs.confirm("00")
        await ps.finish()
        assert admitted(home, pc) == 1
    asyncio.run(run())


def test_three_rejected_requests_close_the_offer_even_across_driver_restarts(devices):
    home, _ = devices

    async def run():
        wires = []
        hs, make = nearby(devices, wires)
        for attempt in range(3):
            ps = make()
            await ps.find()
            await ps.join(ps.screen()["nearby"][0]["id"])
            digits = ps.screen()["pending"]
            with pytest.raises(JournalError, match="same two"):
                ps.compare(other_digits(digits))
            with pytest.raises(JournalError, match="Compare"):
                await ps.prove(PASSWORD)
            await ps.cancel()
            # Reopening the runtime does not reset the durable request count.
            restarted = NearbyPairing(home, key_document=hs.keys)
            state, _ = restarted.desk.current()
            assert state["attempts"] == attempt + 1
        assert restarted.advertise("0" * 64, 47513) is None
        assert restarted.screen()["exhausted"] and restarted.screen()["code"] is None
        fourth = make()
        await fourth.find()  # even a stale, otherwise correctly signed discovery response cannot bypass the cap
        with pytest.raises(JournalError, match="budget exhausted"):
            await fourth.join(fourth.screen()["nearby"][0]["id"])
        assert all(unpack(wire)["body"]["type"] != "journal-pairing-proof" for wire in wires)
    asyncio.run(run())


def test_older_six_digit_number_match_offers_keep_their_exact_handshake(devices):
    async def run():
        hs, make = nearby(devices, method="number-match")
        ps = make()
        await ps.find()
        await ps.join(ps.screen()["nearby"][0]["id"])
        digits = hs.screen()["digits"]
        assert len(digits) == 6 and ps.screen()["pending"] == digits
        assert not ps.screen()["typed_digits"]
        assert len(set(ps.screen()["choices"])) == 3 and digits in ps.screen()["choices"]
        ps.compare(digits)
        hs.confirm(digits)
        await ps.prove(PASSWORD)
        await ps.finish()
        assert admitted(*devices) == 1
    asyncio.run(run())


def test_old_approval_cannot_admit_a_new_request_even_when_two_digits_repeat(devices, monkeypatch):
    monkeypatch.setattr("lightning.sync.journal.pairing.check_digits", lambda value: "000000")

    async def run():
        hs, make, ps = await started(devices)
        old_request = hs.screen()["request_id"]
        await ps.cancel()
        ps = make()
        await ps.find()
        await ps.join(ps.screen()["nearby"][0]["id"])
        assert hs.screen()["digits"] == "00"
        ps.compare("00")
        await ps.prove(PASSWORD)
        with pytest.raises(JournalError, match="request changed"):
            hs.confirm("00", request_id=old_request)
        assert admitted(*devices) == 0
        hs.confirm("00", request_id=hs.screen()["request_id"])
        await ps.finish()
        assert admitted(*devices) == 1
    asyncio.run(run())
