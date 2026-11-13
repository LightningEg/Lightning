"""NF-4M: two digits pair a PC safely (lightning.sync.passkey). The rounds run here over in-memory channels, with an
honest pair, wrong digits, a relay that sees another certificate, and the best known attack on passkey entry: a device
in the middle that learns each bit from the PC and passes it on to the phone. It wins about one time in 128."""
from __future__ import annotations

import queue
import random
import threading

import pytest

from lightning.sync.domain import PasskeyCommit, PasskeyReveal, decode_message, encode_message
from lightning.sync.passkey import (BITS, PasskeyMismatch, commitment, new_passkey, normalize_passkey, run_initiator,
                                    run_responder)

T = b"lightning-pair-v1\npairing\nphone-cert\npc\npc-key"


class Wire:
    """One direction of a link, through the real encoding."""
    def __init__(self):
        self.q = queue.Queue()

    def send(self, message):
        self.q.put(encode_message(message))

    def receive(self):
        item = self.q.get(timeout=5)
        if item is None:
            raise ConnectionError("closed")
        return decode_message(item)

    def close(self):
        self.q.put(None)


def run_pair(pc_digits, phone_digits, pc_transcript=T, phone_transcript=T):
    up, down, out = Wire(), Wire(), {}

    def phone():
        try:
            out["phone"] = run_responder(down.send, up.receive, phone_digits, phone_transcript)
        except (PasskeyMismatch, ConnectionError) as error:
            out["phone"] = error
        finally:
            down.close()

    thread = threading.Thread(target=phone)
    thread.start()
    try:
        out["pc"] = run_initiator(up.send, down.receive, pc_digits, pc_transcript)
    except (PasskeyMismatch, ConnectionError) as error:
        out["pc"] = error
    finally:
        up.close()
    thread.join(5)
    return out["pc"], out["phone"]


def test_the_same_digits_give_both_sides_the_same_key():
    for digits in ("00", "07", "42", "99"):
        pc, phone = run_pair(digits, digits)
        assert isinstance(pc, bytes) and pc == phone and len(pc) == 32


def test_every_wrong_pair_of_digits_fails_on_both_sides():
    for typed in range(100):
        if typed == 37:
            continue
        pc, phone = run_pair(f"{typed:02d}", "37")
        assert not isinstance(pc, bytes) and not isinstance(phone, bytes), typed


def test_a_relay_with_another_certificate_fails_even_with_the_right_digits():
    pc, phone = run_pair("58", "58", pc_transcript=T.replace(b"phone-cert", b"relay-cert"))
    assert not isinstance(pc, bytes) and not isinstance(phone, bytes)


def test_the_phone_reveals_nothing_until_the_pc_proved_the_bit():
    """A PC that guesses wrong at the first bit never sees the phone's first nonce."""
    up, down = Wire(), Wire()
    sent = []
    def phone():
        try:
            run_responder(lambda m: (sent.append(m), down.send(m)), up.receive, "01", T)
        except PasskeyMismatch:
            pass
    thread = threading.Thread(target=phone)
    thread.start()
    import os
    nonce = os.urandom(32)
    up.send(PasskeyCommit(0, commitment(nonce, "pc", T, 0, 0)))  # bit 0 of "01" is 1: a wrong guess
    down.receive()
    up.send(PasskeyReveal(0, nonce.hex()))
    thread.join(5)
    assert [type(m) for m in sent] == [PasskeyCommit]


def test_a_device_in_the_middle_wins_about_one_time_in_128():
    """The bit-relay attack: to the PC it plays the phone, to the phone the PC. In each round it commits a guess to the
    PC, learns the real bit from the PC's reveal, and uses that bit with the phone. Only its guesses to the PC can
    fail, one half per round."""
    rng = random.Random(4)
    import os
    wins, trials = 0, 1200
    for _ in range(trials):
        digits = f"{rng.randrange(100):02d}"
        T_pc, T_phone = T.replace(b"phone-cert", b"attacker-cert"), T.replace(b"pc-key", b"attacker-key")
        alive = True
        for index in range(BITS):
            bit = (int(digits) >> index) & 1
            # PC commits; the attacker answers with a commitment to a guess
            pc_nonce = os.urandom(32)
            pc_commit = commitment(pc_nonce, "pc", T_pc, index, bit)
            guess, attacker_nonce = rng.randrange(2), os.urandom(32)
            to_pc = commitment(attacker_nonce, "phone", T_pc, index, guess)
            # the PC reveals; the attacker learns the bit by trying both
            learned = 0 if commitment(pc_nonce, "pc", T_pc, index, 0) == pc_commit else 1
            assert learned == bit  # so with the phone it commits to the real bit, and the phone's check passes
            # the PC checks the attacker's commitment against the real bit
            if to_pc != commitment(attacker_nonce, "phone", T_pc, index, bit):
                alive = False
                break
        wins += alive
    assert wins / trials < 0.02, wins  # 1/128 = 0.0078 expected


def test_digits_are_drawn_evenly_and_typed_forgivingly():
    seen = {new_passkey() for _ in range(3000)}
    assert len(seen) == 100 and all(len(d) == 2 and d.isdigit() for d in seen)
    assert normalize_passkey("4 2") == "42" and normalize_passkey("٠٧") == "07"
    with pytest.raises(ValueError, match="two digits"):
        normalize_passkey("123")


def test_round_messages_are_strict():
    for bad in (dict(index=7, commitment="a" * 64), dict(index=0, commitment="A" * 64), dict(index=-1, commitment="a" * 64)):
        with pytest.raises(ValueError):
            PasskeyCommit(**bad)
    with pytest.raises(PasskeyMismatch):
        run_initiator(lambda m: None, lambda: PasskeyReveal(0, "a" * 64), "11", T)  # out of order
