"""Find the phone that has Pair a PC open, so nobody types an address (NF-4M, owner 2026-11-12).

The PC asks the local network "is a phone pairing?"; a phone answers only while its pairing screen is open, with its
name, its TLS port and what it is waiting for. Nothing secret is in either packet and nothing here is trusted: the
answer only says where to connect. The two digits, proven in the passkey rounds over TLS, decide who pairs.

The question goes to every broadcast address of this PC and also, one packet each, to every address of its /24 networks,
because many phones drop broadcasts while the screen is on another app and Lightning holds no multicast lock.
Answers are accepted from private addresses only; the responder answers at most 64 packets a second.
"""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import threading
import time
from typing import Callable

NEARBY_PORT = 47515
SEARCH_SECONDS = 1.5
_ASK, _HERE = "lightning-pairing-ask", "lightning-pairing-here"
MAX_PACKET = 1024


def _private(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (address.is_private or address.is_link_local or address.is_loopback) and not (
        address.is_unspecified or address.is_multicast)


def _own_addresses() -> list[str]:
    found = set()
    try:
        found |= {info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        pass
    try:  # the address of the default route (a UDP connect sends nothing)
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("10.255.255.255", 9))
            found.add(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    return sorted(a for a in found if _private(a) and not a.startswith(("127.", "169.254.")))


def destinations() -> list[str]:
    """Broadcast addresses, then every host of each /24 this PC is on (at most two networks)."""
    hosts = ["255.255.255.255"]
    networks = [ipaddress.ip_network(f"{a}/24", strict=False) for a in _own_addresses()][:2]
    hosts += [str(n.broadcast_address) for n in networks]
    for network, own in zip(networks, _own_addresses()):
        hosts += [str(h) for h in network.hosts() if str(h) != own]
    return list(dict.fromkeys(hosts))


def _parse(wire: bytes) -> dict | None:
    if len(wire) > MAX_PACKET:
        return None
    try:
        data = json.loads(wire.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


class NearbyResponder:
    """On the phone. `state()` returns None, or (name, tls_port, mode) while a pairing screen is open."""

    def __init__(self, state: Callable[[], tuple[str, int, str] | None], *, host: str = "0.0.0.0", port: int = NEARBY_PORT):
        self.state = state
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((host, port))
        self.socket.settimeout(1.0)
        self.port = self.socket.getsockname()[1]
        self._stopping = threading.Event()
        self._window, self._packets = 0.0, 0
        self.thread = threading.Thread(target=self._serve, name="lightning-pairing-nearby", daemon=True)

    def start(self) -> "NearbyResponder":
        self.thread.start()
        return self

    def stop(self) -> None:
        self._stopping.set()
        self.socket.close()
        self.thread.join(3)

    def _serve(self) -> None:
        while not self._stopping.is_set():
            try:
                wire, address = self.socket.recvfrom(MAX_PACKET + 1)
            except TimeoutError:
                continue
            except OSError:
                return
            now = time.monotonic()
            if now - self._window >= 1:
                self._window, self._packets = now, 0
            self._packets += 1
            if self._packets > 64 or not _private(address[0]):
                continue
            ask = _parse(wire)
            nonce = ask.get("nonce") if ask else None
            if not ask or ask.get("type") != _ASK or not isinstance(nonce, str) or len(nonce) != 32:
                continue
            try:
                state = self.state()
            except Exception:  # noqa: BLE001 - a question about pairing never takes the listener down
                state = None
            if state is None:
                continue
            name, tls_port, mode = state
            reply = json.dumps(dict(type=_HERE, nonce=nonce, name=name[:60], port=tls_port, mode=mode)).encode("utf-8")
            try:
                self.socket.sendto(reply, address)
            except OSError:
                continue


def find_phones(*, timeout: float | None = None, port: int | None = None, targets: list[str] | None = None) -> list[dict]:
    """On the PC: the phones that have a pairing screen open, as dicts with name, endpoint and mode ("pair" or "move").
    Asks three times within `timeout`, as one datagram on a busy Wi-Fi may be lost."""
    targets = destinations() if targets is None else targets
    timeout = SEARCH_SECONDS if timeout is None else timeout
    port = NEARBY_PORT if port is None else port
    nonce = os.urandom(16).hex()
    found: dict[str, dict] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("0.0.0.0", 0))
        ask = json.dumps(dict(type=_ASK, nonce=nonce)).encode("utf-8")
        deadline = time.monotonic() + timeout
        for attempt in range(3):
            for host in targets:
                try:
                    sock.sendto(ask, (host, port))
                except OSError:
                    continue
            until = min(deadline, time.monotonic() + timeout / 3)
            while (left := until - time.monotonic()) > 0:
                sock.settimeout(left)
                try:
                    wire, address = sock.recvfrom(MAX_PACKET + 1)
                except (TimeoutError, OSError):
                    break
                reply = _parse(wire)
                if (not reply or reply.get("type") != _HERE or reply.get("nonce") != nonce or not _private(address[0])
                        or type(reply.get("port")) is not int or not 1024 <= reply["port"] <= 65535
                        or reply.get("mode") not in ("pair", "move") or not isinstance(reply.get("name"), str)):
                    continue
                name = " ".join(reply["name"].split())[:60] or "Phone"
                endpoint = f"{address[0]}:{reply['port']}"
                found[endpoint] = dict(name=name, endpoint=endpoint, mode=reply["mode"])
            if found and attempt:
                break
    finally:
        sock.close()
    return sorted(found.values(), key=lambda item: (item["name"], item["endpoint"]))[:8]
