"""Two digits instead of a twelve-letter code (NF-4M, owner 2026-11-12): passkey entry, as Bluetooth pairing does it.

The phone shows two digits; the person types them on the PC. Two digits alone would be guessed in a moment if they
were a key (anyone on the Wi-Fi could try all hundred offline), so they never are one. They are seven bits, and each
bit is proven in its own round over the TLS link, inside a transcript that binds the phone's certificate as the PC
sees it and the PC's identity key:

    PC    -> phone   commit   C_pc  = HMAC(N_pc,  "pc"    | transcript | round | bit)
    phone -> PC      commit   C_ph  = HMAC(N_ph,  "phone" | transcript | round | bit)
    PC    -> phone   reveal   N_pc        the phone checks C_pc with its own bit
    phone -> PC      reveal   N_ph        the PC checks C_ph with the typed bit

Whoever does not know a bit must commit to a guess before learning it, so a device in the middle survives each round
with a chance of one half: about one in a hundred for the whole code, online, and a failed try is seen on both
screens. The phone shows new digits after every failed or broken try, so what a failed try reveals is never reused.
Both sides then hold the same key over the transcript, the code and every nonce, and the phone's reply is bound to it.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Callable

BITS = 7                    # 0..99 fits in seven bits
V2_MARKER = hashlib.sha256(b"lightning-pair-v2").hexdigest()  # PairRequest/MoveBegin.proof: "I speak passkey entry"
_ARABIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


class PasskeyMismatch(Exception):
    """A round's commitment did not open to the expected bit: the typed digits are not the phone's, or someone sits
    between the two devices."""


def new_passkey() -> str:
    return f"{secrets.randbelow(100):02d}"


def normalize_passkey(text: str) -> str:
    """The two digits as typed: spaces and Arabic-Indic digits are fine."""
    digits = "".join(str(text or "").translate(_ARABIC).split())
    if len(digits) != 2 or not digits.isascii() or not digits.isdigit():
        raise ValueError("Type the two digits shown on the phone.")
    return digits


def _bit(passkey: str, index: int) -> int:
    return (int(passkey) >> index) & 1


def commitment(nonce: bytes, role: str, transcript: bytes, index: int, bit: int) -> str:
    return hmac.new(nonce, b"\n".join((role.encode("ascii"), transcript, str(index).encode("ascii"),
                                       str(bit).encode("ascii"))), hashlib.sha256).hexdigest()


def session_key(transcript: bytes, passkey: str, nonces: list[bytes]) -> bytes:
    digest = hashlib.sha256(b"lightning-pair-v2-key\n" + transcript + b"\n" + passkey.encode("ascii"))
    for nonce in nonces:
        digest.update(nonce)
    return digest.digest()


def seal(key: bytes, role: str, data: bytes) -> str:
    """The proof on the phone's reply, under the key both sides now share."""
    return hmac.new(key, role.encode("ascii") + b"\n" + data, hashlib.sha256).hexdigest()


def _nonce(message, index: int) -> bytes:
    from .domain import PasskeyReveal
    if not isinstance(message, PasskeyReveal) or message.index != index:
        raise PasskeyMismatch("The pairing exchange went out of order.")
    return bytes.fromhex(message.nonce)


def _commit(message, index: int) -> str:
    from .domain import PasskeyCommit
    if not isinstance(message, PasskeyCommit) or message.index != index:
        raise PasskeyMismatch("The pairing exchange went out of order.")
    return message.commitment


def run_initiator(send: Callable, receive: Callable, passkey: str, transcript: bytes) -> bytes:
    """The PC, with the digits the person typed. Returns the shared key, or raises PasskeyMismatch."""
    from .domain import PasskeyCommit, PasskeyReveal
    passkey, nonces = normalize_passkey(passkey), []
    for index in range(BITS):
        bit, mine = _bit(passkey, index), secrets.token_bytes(32)
        send(PasskeyCommit(index, commitment(mine, "pc", transcript, index, bit)))
        theirs_commit = _commit(receive(), index)
        send(PasskeyReveal(index, mine.hex()))
        theirs = _nonce(receive(), index)
        if not hmac.compare_digest(commitment(theirs, "phone", transcript, index, bit), theirs_commit):
            raise PasskeyMismatch(index)
        nonces += [mine, theirs]
    return session_key(transcript, passkey, nonces)


def run_responder(send: Callable, receive: Callable, passkey: str, transcript: bytes) -> bytes:
    """The phone, with the digits it shows. It reveals each round's nonce only after the PC proved that bit."""
    from .domain import PasskeyCommit, PasskeyReveal
    nonces = []
    for index in range(BITS):
        bit, mine = _bit(passkey, index), secrets.token_bytes(32)
        theirs_commit = _commit(receive(), index)
        send(PasskeyCommit(index, commitment(mine, "phone", transcript, index, bit)))
        theirs = _nonce(receive(), index)
        if not hmac.compare_digest(commitment(theirs, "pc", transcript, index, bit), theirs_commit):
            raise PasskeyMismatch(index)
        send(PasskeyReveal(index, mine.hex()))
        nonces += [theirs, mine]
    return session_key(transcript, passkey, nonces)
