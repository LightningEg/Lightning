"""NF-4M: the PC finds a phone with a pairing screen open, so nobody types its address."""
from __future__ import annotations

import json
import socket

from lightning.sync.nearby import NearbyResponder, destinations, find_phones


def responder(state):
    return NearbyResponder(state, host="127.0.0.1", port=0).start()


def test_a_phone_answers_only_while_pairing_is_open():
    state = {"open": None}
    phone = responder(lambda: state["open"])
    try:
        assert find_phones(timeout=0.3, port=phone.port, targets=["127.0.0.1"]) == []
        state["open"] = ("Mohab's phone", 47513, "pair")
        assert find_phones(timeout=0.6, port=phone.port, targets=["127.0.0.1"]) == [
            {"name": "Mohab's phone", "endpoint": "127.0.0.1:47513", "mode": "pair"}]
        state["open"] = ("Mohab's phone", 47513, "move")
        assert find_phones(timeout=0.6, port=phone.port, targets=["127.0.0.1"])[0]["mode"] == "move"
    finally:
        phone.stop()


def test_garbage_and_wrong_answers_are_ignored():
    phone = responder(lambda: ("Phone", 47513, "pair"))
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.settimeout(0.3)
            for wire in (b"\xff" * 2000, b"not json", json.dumps({"type": "lightning-pairing-ask", "nonce": "short"}).encode()):
                probe.sendto(wire, ("127.0.0.1", phone.port))
            try:
                probe.recvfrom(2048)
                answered = True
            except TimeoutError:
                answered = False
        assert not answered
        assert find_phones(timeout=0.6, port=phone.port, targets=["127.0.0.1"])  # still answers a real question
    finally:
        phone.stop()


def test_a_reply_with_a_bad_port_or_mode_is_not_listed():
    phone = responder(lambda: ("Phone", 80, "pair"))
    try:
        assert find_phones(timeout=0.3, port=phone.port, targets=["127.0.0.1"]) == []
    finally:
        phone.stop()


def test_the_question_reaches_every_address_of_the_network():
    hosts = destinations()
    assert hosts[0] == "255.255.255.255" and len(hosts) == len(set(hosts)) and len(hosts) <= 3 + 2 * 254
