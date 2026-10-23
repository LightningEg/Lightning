"""Short-lived pairing bound to device identities, number matching and password proof.

Number-match offers commit the joining secret before the home supplies a fresh
challenge. The signed reveal binds both contributions to the authentication
number, preventing either peer from grinding a matching transcript offline.
The joining user selects the home's number before sending a password proof;
admission also requires explicit home approval. Legacy offers still require a
six-digit bootstrap code. Passwords and data keys never enter pairing messages.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time

from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from lightning.security.keys import unwrap_key, _password_bytes
from lightning.sync.identity import check_digits
from .codec import JournalError, authenticate, canonical, digest, fields, hash_value, seal, unpack, uuid


def _password_proof(password, salt):
    return Argon2id(salt=salt, length=32, iterations=4, lanes=4, memory_cost=131072).derive(_password_bytes(password))


def normalize_code(value):
    if type(value) is not str or len(value) > 32:
        raise JournalError("Enter the six-digit number shown on the home")
    value = value.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "0123456789" * 2))
    code = "".join(char for char in value if char not in " -\t\r\n")
    if len(code) != 6 or any(char not in "0123456789" for char in code):
        raise JournalError("Enter the six-digit number shown on the home")
    return code


def _request_proof(offer, request, code):
    # This public binding only reserves a request. Authentication still requires
    # out-of-band number matching, explicit home approval and the password proof.
    key = (b"lightning-number-match-v1" if offer.get("method") == "number-match"
           else normalize_code(code).encode("ascii"))
    return hmac.new(key, canonical(request), hashlib.sha256).hexdigest()


def number_choices(digits):
    choices = [digits]
    while len(choices) < 3:
        candidate = f"{secrets.randbelow(1000000):06d}"
        if candidate not in choices:
            choices.append(candidate)
    secrets.SystemRandom().shuffle(choices)
    return choices


def require_live_offer(candidate):
    offer = unpack(candidate["offer"].encode())["body"]
    return _offer(candidate["offer"].encode(), offer["home_key"], time.time)


def _offer(offer, home_key, now):
    envelope = unpack(offer)
    authenticate(envelope, home_key)
    body = envelope["body"]
    fields(body, ("type", "profile", "generation", "home", "home_key", "nonce", "salt", "expires") + (("method",) if "method" in body else ()))
    if "method" in body and body["method"] != "number-match":
        raise JournalError("Unsupported pairing method")
    if body["type"] != "journal-pairing" or body["home_key"] != home_key or not now() < body["expires"] <= now() + 600:
        raise JournalError("Pairing offer expired or home identity changed")
    return body


def request_pairing(offer, code, identity, incarnation, *, home_key, now=time.time, secret=None):
    """Begin without password-derived values; commit a secret for number matching."""
    body = _offer(offer, home_key, now)
    uuid(incarnation)
    request = dict(type="journal-pairing-request", offer=digest(body), device=identity.device_id, name=identity.name,
                   key=identity.public_key, incarnation=incarnation)
    if body.get("method") == "number-match":
        if not isinstance(secret, bytes) or len(secret) != 32:
            raise JournalError("Number matching requires a fresh secret")
        request["commitment"] = hashlib.sha256(secret).hexdigest()
    request["proof"] = _request_proof(body, request, code)
    return seal(request, identity.sign), (None if secret is not None else check_digits(canonical(dict(offer=body, request=request))))


def matching_digits(offer, request, challenge, secret):
    return check_digits(canonical(dict(offer=offer, request=request, challenge=challenge, secret=secret)))


async def complete_number_match(offer_wire, request_wire, answer, secret, identity, exchange):
    """Commit before the home's unpredictable challenge; reveal only after its signed reply.

    Neither peer can grind a chosen matching number after learning the other's
    random contribution. No password-derived value is sent by this handshake.
    """
    offer = unpack(offer_wire)["body"]
    request = unpack(request_wire)["body"]
    authenticate(answer, offer["home_key"])
    body = answer["body"]
    fields(body, ("type", "request", "challenge"))
    hash_value(body["challenge"])
    if body["type"] != "pairing-wait" or body["request"] != digest(request):
        raise JournalError("Pairing transcript changed")
    reveal = dict(type="journal-pairing-reveal", request=digest(request), challenge=body["challenge"], secret=secret.hex())
    reply = unpack(await exchange(seal(reveal, identity.sign)))
    authenticate(reply, offer["home_key"])
    if reply["body"] != dict(type="pairing-matched", request=digest(request), challenge=body["challenge"], reveal=digest(reveal)):
        raise JournalError("Pairing transcript changed")
    return matching_digits(offer, request, body["challenge"], secret.hex())


def prove_pairing(offer, request, password, identity, *, home_key, now=time.time):
    """Phase 2: call only after the user confirmed the check digits on this device."""
    body = _offer(offer, home_key, now)
    sent = unpack(request)["body"]
    if sent.get("offer") != digest(body) or sent.get("device") != identity.device_id or sent.get("key") != identity.public_key:
        raise JournalError("Pairing request does not match this offer")
    try:
        salt = bytes.fromhex(body["salt"])
        if len(salt) != 16:
            raise ValueError
    except (ValueError, TypeError) as error:
        raise JournalError("Invalid pairing salt") from error
    proof = hmac.new(_password_proof(password, salt), canonical(dict(offer=digest(body), request=digest(sent))), hashlib.sha256).hexdigest()
    return seal(dict(type="journal-pairing-proof", offer=digest(body), request=digest(sent), device=identity.device_id, proof=proof), identity.sign)


class PairingDesk:
    def __init__(self, device, membership, *, clock=time.time, on_admit=None):
        if device.home is None:
            raise JournalError("Pair on the home")
        self.device, self.membership, self.db, self.clock, self.on_admit = device, membership, device.store.db, clock, on_admit

    def begin(self, key_file, password, *, method=None):
        if method not in (None, "number-match"):
            raise JournalError("Unsupported pairing method")
        self.device.store.require_confirmation_authority()
        if not hmac.compare_digest(unwrap_key(key_file, password), self.db.copy_key()):
            raise JournalError("Password belongs to a different profile")
        salt, code = os.urandom(16), f"{secrets.randbelow(1000000):06d}"
        config = self.device.store.config
        body = dict(type="journal-pairing", profile=config["profile"], generation=config["generation"],
                    home=config["device"], home_key=config["home_key"], nonce=os.urandom(32).hex(),
                    salt=salt.hex(), expires=int(self.clock()) + 600)
        if method is not None:
            body["method"] = method
        offer = seal(body, self.device.identity.sign)
        # Temporary proof verifier lives only in the encrypted profile and expires.
        state = dict(offer=offer.decode(), code=code, verifier=_password_proof(password, salt).hex(), attempts=0, proof_attempts=0,
                     request=None, proof=None, confirmed=False, challenge=None, reveal=None)
        with self.db.transaction():
            self.db.execute("INSERT OR REPLACE INTO journal_local VALUES('pairing',?)", (canonical(state).decode(),))
        return offer, code

    def _state(self):
        value = self.db.scalar("SELECT value FROM journal_local WHERE name='pairing'")
        if value is None:
            raise JournalError("Open pairing on the home first")
        state = json.loads(value)
        return state, unpack(state["offer"].encode())["body"]

    def _save(self, state):
        with self.db.transaction():
            self.db.execute("UPDATE journal_local SET value=? WHERE name='pairing'", (canonical(state).decode(),))

    def accept(self, wire):
        """Phase 1: verify the code proof and keep the request. No password is involved yet."""
        state, offer = self._state()
        if self.clock() >= offer["expires"] or state["attempts"] >= 3:
            raise JournalError("Pairing expired; open a new code on the home")
        if state["request"]:
            if state["request"] != wire.decode():
                raise JournalError("Another device is already pairing; stop and open a new code on the home")
            return self.digits(state, offer)
        # Persist every attempt before interpreting the request, including malformed ones.
        state["attempts"] += 1
        self._save(state)
        envelope = unpack(wire)
        body = envelope["body"]
        fields(body, ("type", "offer", "device", "name", "key", "incarnation", "proof") + (("commitment",) if offer.get("method") == "number-match" else ()))
        if offer.get("method") == "number-match":
            hash_value(body["commitment"])
        if type(body["name"]) is not str or not 1 <= len(body["name"].strip()) <= 60:
            raise JournalError("Invalid nearby device name")
        uuid(body["device"])
        uuid(body["incarnation"])
        authenticate(envelope, body["key"])
        if body["type"] != "journal-pairing-request" or body["offer"] != digest(offer):
            raise JournalError("Pairing transcript changed")
        unsigned = {key: value for key, value in body.items() if key != "proof"}
        expected = _request_proof(offer, unsigned, state["code"])
        if type(body["proof"]) is not str or not hmac.compare_digest(body["proof"], expected):
            raise JournalError("Pairing code is wrong")
        state["request"] = wire.decode()
        if offer.get("method") == "number-match":
            state["challenge"] = os.urandom(32).hex()
        self._save(state)
        return self.digits(state, offer)

    def digits(self, state, offer):
        request = unpack(state["request"].encode())["body"]
        if offer.get("method") == "number-match":
            if not state.get("reveal"):
                return None
            return matching_digits(offer, request, state["challenge"], state["reveal"])
        return check_digits(canonical(dict(offer=offer, request=request)))

    def waiting(self):
        state, offer = self._state()
        request = unpack(state["request"].encode())["body"]
        body = dict(type="pairing-wait", request=digest(request))
        if offer.get("method") == "number-match":
            body["challenge"] = state["challenge"]
        return body

    def reveal(self, wire):
        state, offer = self._state()
        if offer.get("method") != "number-match" or not state.get("request") or self.clock() >= offer["expires"]:
            raise JournalError("Pairing expired; start again")
        request = unpack(state["request"].encode())["body"]
        envelope = unpack(wire)
        authenticate(envelope, request["key"])
        body = envelope["body"]
        fields(body, ("type", "request", "challenge", "secret"))
        hash_value(body["secret"])
        if (body["type"] != "journal-pairing-reveal" or body["request"] != digest(request)
                or body["challenge"] != state["challenge"]
                or not hmac.compare_digest(hashlib.sha256(bytes.fromhex(body["secret"])).hexdigest(), request["commitment"])):
            raise JournalError("Pairing transcript changed")
        state["reveal"] = body["secret"]
        self._save(state)
        return seal(dict(type="pairing-matched", request=digest(request), challenge=state["challenge"],
                         reveal=digest(body)), self.device.identity.sign)

    def prove(self, wire):
        """Phase 2: the password proof, sent only after the joiner confirmed the digits.

        Returns the membership update once the home has also confirmed, else None.
        """
        state, offer = self._state()
        if not state["request"] or (offer.get("method") == "number-match" and not state.get("reveal")):
            raise JournalError("No verified pairing request")
        if self.clock() >= offer["expires"] or state["proof_attempts"] >= 3:
            raise JournalError("Pairing expired; open a new code on the home")
        envelope = unpack(wire)
        body = envelope["body"]
        if state["proof"] and type(body) is dict and state["proof"] == digest(body):
            return None
        state["proof_attempts"] += 1
        self._save(state)
        request = unpack(state["request"].encode())["body"]
        fields(body, ("type", "offer", "request", "device", "proof"))
        authenticate(envelope, request["key"])
        if (body["type"] != "journal-pairing-proof" or body["offer"] != digest(offer) or body["request"] != digest(request)
                or body["device"] != request["device"]):
            raise JournalError("Pairing transcript changed")
        expected = hmac.new(bytes.fromhex(state["verifier"]), canonical(dict(offer=body["offer"], request=body["request"])), hashlib.sha256).hexdigest()
        if type(body["proof"]) is not str or not hmac.compare_digest(body["proof"], expected):
            raise JournalError("Profile password is wrong")
        state["proof"] = digest(body)
        self._save(state)
        return self._admit(state) if state["confirmed"] else None

    def confirm(self, digits):
        """The home owner's comparison. Returns the membership update once the password proof exists, else None."""
        self.device.store.require_confirmation_authority()
        state, offer = self._state()
        if not state.get("request"):
            raise JournalError("No verified pairing request")
        body = unpack(state["request"].encode())["body"]
        expected = self.digits(state, offer)
        if not expected or self.clock() >= offer["expires"] or type(digits) is not str or not hmac.compare_digest(digits, expected):
            raise JournalError("Check that both devices show the same six digits")
        state["confirmed"] = True
        self._save(state)
        return self._admit(state) if state["proof"] else None

    def _admit(self, state):
        self.device.store.require_confirmation_authority()
        body = unpack(state["request"].encode())["body"]
        members = dict(self.membership.state()["members"])
        if body["device"] in members:
            raise JournalError("This device is already paired; use its saved identity")
        members[body["device"]] = dict(key=body["key"], incarnation=body["incarnation"])
        with self.db.transaction():
            result = self.membership.rotate(members)
            self.db.execute("DELETE FROM journal_local WHERE name='pairing'")
            if self.on_admit:
                self.on_admit(state["request"], result)
        return result
