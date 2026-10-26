"""Durable joining-side pairing states; saves precede every uncertain delivery.

Only fresh random commitment material is temporarily persisted. Passwords,
password proofs and Argon2 verifiers are never written to enrollment state.
"""
from __future__ import annotations

import os

from .codec import JournalError, authenticate, digest, fields, hash_value, seal, unpack
from .pairing import matching_digits, number_choices, prove_pairing, request_pairing, require_live_offer


def begin(candidate, identity, incarnation, code=""):
    offer = unpack(candidate["offer"].encode())["body"]
    secret = os.urandom(32) if offer.get("method") == "number-match" else None
    wire, digits = request_pairing(candidate["offer"].encode(), code, identity, incarnation,
                                   home_key=offer["home_key"], secret=secret)
    return dict(candidate=candidate, wire=wire.decode(), request=digest(unpack(wire)["body"]),
                secret=secret.hex() if secret else None, digits=digits, incarnation=incarnation,
                profile=offer["profile"], generation=offer["generation"], home_key=offer["home_key"], stage="handshake")


def _answer(wire, state):
    envelope = unpack(wire)
    authenticate(envelope, state["home_key"])
    body = envelope["body"]
    if type(body) is not dict or body.get("request") != state["request"]:
        raise JournalError("Pairing response belongs to another request")
    return body


async def handshake(state, identity, exchange, save):
    if state["stage"] != "handshake":
        return
    offer = require_live_offer(state["candidate"])
    request = unpack(state["wire"].encode())["body"]
    if offer.get("method") == "number-match":
        if not state.get("challenge"):
            answer = _answer(await exchange(state["wire"].encode()), state)
            fields(answer, ("type", "request", "challenge"))
            hash_value(answer["challenge"])
            if answer["type"] != "pairing-wait":
                raise JournalError("Pairing transcript changed")
            # This durable FIRST challenge must never be replaced on retries.
            state["challenge"] = answer["challenge"]
            reveal = dict(type="journal-pairing-reveal", request=state["request"],
                          challenge=state["challenge"], secret=state["secret"])
            state["reveal_wire"] = seal(reveal, identity.sign).decode()
            save(state)
        reveal = unpack(state["reveal_wire"].encode())["body"]
        answer = _answer(await exchange(state["reveal_wire"].encode()), state)
        if answer != dict(type="pairing-matched", request=state["request"],
                          challenge=state["challenge"], reveal=digest(reveal)):
            raise JournalError("Pairing transcript changed; cancel and start a fresh pairing")
        state["digits"] = matching_digits(offer, request, state["challenge"], state["secret"])
    else:
        answer = _answer(await exchange(state["wire"].encode()), state)
        if answer != dict(type="pairing-wait", request=state["request"]):
            raise JournalError("Pairing transcript changed")
    state.update(stage="compare", choices=number_choices(state["digits"]))
    state.pop("secret", None)
    state.pop("reveal_wire", None)
    save(state)


async def status(state, identity, exchange, save):
    nonce = os.urandom(32).hex()
    wire = seal(dict(type="journal-pairing-status", request=state["request"], device=identity.device_id, nonce=nonce), identity.sign)
    answer = _answer(await exchange(wire), state)
    if answer.pop("nonce", None) != nonce:
        raise JournalError("Pairing status challenge changed")
    if answer.get("type") == "pairing-approved":
        fields(answer, ("type", "request", "membership"))
        state["stage"] = "waiting"
    elif answer.get("type") == "pairing-pending":
        fields(answer, ("type", "request", "proof"))
        if type(answer["proof"]) is not bool:
            raise JournalError("Invalid pairing status")
        state["stage"] = "waiting" if answer["proof"] else "password"
    else:
        raise JournalError("Pairing approval is not available yet")
    save(state)
    return answer


async def prove(state, identity, password, exchange, save):
    if state.get("failed") or state["stage"] not in ("password", "proving"):
        raise JournalError("Compare the numbers with the home first")
    if state["stage"] == "proving":
        await status(state, identity, exchange, save)
        if state["stage"] == "waiting":
            return
    wire = prove_pairing(state["candidate"]["offer"].encode(), state["wire"].encode(), password,
                         identity, home_key=state["home_key"])
    state["stage"] = "proving"
    save(state)  # No proof wire or password is saved.
    try:
        answer = _answer(await exchange(wire), state)
    except JournalError:
        # A refusal may follow a committed admission with a lost response. Only
        # authenticated status decides whether another password is needed.
        try:
            await status(state, identity, exchange, save)
        except (JournalError, OSError, TimeoutError):
            pass
        raise
    if answer.get("type") == "pairing-approved":
        fields(answer, ("type", "request", "membership"))
    elif answer != dict(type="pairing-wait", request=state["request"]):
        raise JournalError("Pairing response changed")
    state["stage"] = "waiting"
    save(state)


async def cancel(state, identity, exchange, save):
    offer = unpack(state["candidate"]["offer"].encode())["body"]
    state["stage"] = "cancelling"
    save(state)
    wire = seal(dict(type="journal-pairing-cancel", offer=digest(offer), request=state["request"],
                     device=identity.device_id, original=state["wire"], offer_wire=state["candidate"]["offer"]), identity.sign)
    try:
        answer = _answer(await exchange(wire), state)
    except JournalError:
        try:
            await status(state,identity,exchange,save)
        except (JournalError,OSError,TimeoutError):
            pass
        raise
    if answer.get("type") == "pairing-approved":
        fields(answer, ("type","request","membership"))
        state["stage"] = "waiting"
        save(state)
        raise JournalError("This device is already approved. Remove it on the home to revoke access")
    if answer != dict(type="pairing-cancelled", request=state["request"]):
        raise JournalError("Pairing cancellation changed")
