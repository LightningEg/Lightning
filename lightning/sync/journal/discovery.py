"""Bounded IPv4 LAN discovery of an already paired home, with no user prompt.

Probes reveal no financial payload. Normal discovery uses the transport key;
a saved-signature control locator also works before receiving a key rotation.
Both bind public scope, recipient and a fresh challenge before using an endpoint.
The subsequent TCP connection still verifies the saved TLS certificate.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import os
import socket
import time

from .codec import JournalError, authenticate, canonical, fields, seal, unpack

DISCOVERY_PORT = 47514


def local_address(host):
    try:
        address = ipaddress.ip_address(host)
        return (address.is_private or address.is_link_local or address.is_loopback) and not (address.is_unspecified or address.is_multicast)
    except ValueError:
        return False


def broadcast_destinations():
    """Where a search is announced: the limited broadcast, and the /24 broadcast of every private address this computer has.
    A limited broadcast (255.255.255.255) leaves through one adapter only, so a computer with a VPN, a virtual switch or a
    phone's hotspot often announced on the wrong network and never reached the device sitting on the right one."""
    found = ["255.255.255.255"]
    addresses = set()
    try:
        addresses |= {info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        pass
    try:   # the address the default route uses (a UDP connect sends nothing)
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("10.255.255.255", 9))
            addresses.add(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    for address in sorted(addresses):
        if local_address(address) and not address.startswith(("127.", "169.254.")):
            found.append(".".join(address.split(".")[:3] + ["255"]))
    return tuple(dict.fromkeys(found))[:8]


def _scope(channel):
    if hasattr(channel, "membership"):
        channel.membership.refresh(channel)
    config = channel.device.store.config
    return hmac.new(channel.key, canonical(dict(type="journal-discovery", profile=config["profile"],
                    generation=config["generation"], epoch=channel.epoch)), hashlib.sha256).hexdigest()


def _open(channel, wire, *, kind, recipient, nonce=None):
    if len(wire) > 2048:
        raise JournalError("Discovery packet limit exceeded")
    envelope = unpack(wire)
    body = envelope["body"]
    fields(body, {"type", "scope", "sender", "recipient", "nonce"} | ({"port"} if kind == "journal-found" else set()))
    public_key = channel.peers.get(body["sender"])
    if public_key is None:
        raise JournalError("Discovery sender is not paired")
    authenticate(envelope, public_key)
    if (body["type"] != kind or body["recipient"] != recipient or body["scope"] != _scope(channel)
            or type(body["nonce"]) is not str or len(body["nonce"]) != 64 or (nonce is not None and body["nonce"] != nonce)):
        raise JournalError("Discovery routing or challenge mismatch")
    return body


def _locate_open(channel, wire, *, kind, recipient, nonce=None):
    """Saved signing keys can locate a home even before a group-key update.

    This control probe carries public scope only; it conveys no membership
    admission or financial payload. TLS and the membership protocol follow.
    """
    if len(wire) > 2048:
        raise JournalError("Discovery packet limit exceeded")
    if hasattr(channel,"membership"):
        channel.membership.refresh(channel)
    envelope = unpack(wire)
    body = envelope["body"]
    fields(body,{"type","profile","generation","sender","recipient","nonce"} | ({"port"} if kind == "journal-located" else set()))
    key = channel.peers.get(body["sender"])
    if key is None:
        raise JournalError("Discovery sender is not paired")
    authenticate(envelope,key)
    channel.device.store._scope(body)
    from .codec import hash_value
    hash_value(body["nonce"])
    if body["type"] != kind or body["recipient"] != recipient or (nonce is not None and body["nonce"] != nonce):
        raise JournalError("Discovery routing or challenge mismatch")
    return body


class LanResponder(asyncio.DatagramProtocol):
    def __init__(self, channel, *, tls_port=47513, clock=time.monotonic, nearby=None):
        if type(tls_port) is not int or not 1024 <= tls_port <= 65535:
            raise JournalError("Invalid home TLS port")
        self.channel, self.port, self.clock = channel, tls_port, clock
        self.nearby = nearby
        self.window, self.packets, self.replied = 0, 0, {}

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, wire, address):
        now = self.clock()
        if now - self.window >= 1:
            self.window, self.packets = now, 0
        self.packets += 1
        if self.packets > 64 or len(wire) > 4096 or not local_address(address[0]):
            return
        device = self.channel.device
        if device.home is None:
            return
        try:
            device.store.require_confirmation_authority()
            if self.nearby is not None:
                envelope = unpack(wire)
                if envelope["body"].get("type") == "journal-nearby":
                    fields(envelope["body"], ("type", "nonce"))
                    nonce = envelope["body"]["nonce"]
                    from .codec import hash_value
                    hash_value(nonce)
                    reply = self.nearby(nonce, self.port)
                    if reply is not None:
                        self.transport.sendto(reply, address)
                    return
            locating = unpack(wire)["body"].get("type") == "journal-locate"
            body = (_locate_open(self.channel,wire,kind="journal-locate",recipient=device.identity.device_id) if locating else
                    _open(self.channel, wire, kind="journal-discover", recipient=device.identity.device_id))
            if not device.store.db.scalar("SELECT 1 FROM journal_origins WHERE device=? AND revoked=0", (body["sender"],)):
                return
            if self.replied.get(body["sender"], -1) + 0.2 > now:   # a repeated probe (the searcher announces three times) is answered again
                return
            self.replied[body["sender"]] = now
            reply = dict(type="journal-found", scope=body.get("scope"), sender=device.identity.device_id,
                         recipient=body["sender"], nonce=body["nonce"], port=self.port)
            if locating:
                reply.pop("scope")
                reply.update(type="journal-located",profile=device.store.config["profile"],generation=device.store.config["generation"])
            self.transport.sendto(seal(reply, device.identity.sign), address)
        except (JournalError, ValueError, KeyError, TypeError):
            return


class _DiscoveryInbox(asyncio.DatagramProtocol):
    def __init__(self, channel, home_id, nonce, future):
        self.channel, self.home_id, self.nonce, self.future = channel, home_id, nonce, future
        self.packets = 0

    def datagram_received(self, wire, address):
        self.packets += 1
        if self.packets > 64:
            return
        if self.future.done() or not local_address(address[0]):
            return
        try:
            body = (_locate_open(self.channel,wire,kind="journal-located",recipient=self.channel.device.identity.device_id,nonce=self.nonce)
                    if unpack(wire)["body"].get("type") == "journal-located" else
                    _open(self.channel, wire, kind="journal-found", recipient=self.channel.device.identity.device_id, nonce=self.nonce))
            if body["sender"] != self.home_id or type(body["port"]) is not int or not 1024 <= body["port"] <= 65535:
                return
            self.future.set_result(f"https://{address[0]}:{body['port']}/exchange")
        except (JournalError, ValueError, KeyError, TypeError):
            return


async def discover(channel, home_id, *, port=DISCOVERY_PORT, timeout=0.6, destinations=None, tries=3):
    destinations = broadcast_destinations() if destinations is None else destinations
    if home_id not in channel.peers or len(destinations) > 8 or not 0.1 <= timeout <= 2 or not 1 <= tries <= 5:
        raise JournalError("Invalid paired-home discovery request")
    loop = asyncio.get_running_loop()
    nonce, future = os.urandom(32).hex(), loop.create_future()
    body = dict(type="journal-discover", scope=_scope(channel), sender=channel.device.identity.device_id,
                recipient=home_id, nonce=nonce)
    wire = seal(body, channel.device.identity.sign)
    config = channel.device.store.config
    locator = seal(dict(type="journal-locate",profile=config["profile"],generation=config["generation"],
                        sender=config["device"],recipient=home_id,nonce=nonce),channel.device.identity.sign)
    transport, _ = await loop.create_datagram_endpoint(lambda: _DiscoveryInbox(channel, home_id, nonce, future),
                                                      local_addr=("0.0.0.0", 0), allow_broadcast=True)
    try:
        # A broadcast is one datagram that a busy wireless network may drop: announce again within the same window.
        for _ in range(tries):
            for address in destinations:
                transport.sendto(wire, (address, port))
                transport.sendto(locator, (address, port))
            try:
                return [await asyncio.wait_for(asyncio.shield(future), timeout / tries)]
            except asyncio.TimeoutError:
                continue
        return []
    finally:
        transport.close()


class _NearbyInbox(asyncio.DatagramProtocol):
    def __init__(self, nonce):
        self.nonce, self.found, self.packets = nonce, {}, 0

    def datagram_received(self, wire, address):
        self.packets += 1
        if self.packets > 64 or len(wire) > 4096 or not local_address(address[0]):
            return
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import serialization
            envelope = unpack(wire)
            body = envelope["body"]
            fields(body, ("type", "nonce", "name", "home", "offer", "certificate", "port"))
            offer = unpack(body["offer"].encode())["body"]
            authenticate(envelope, offer["home_key"])
            if (body["type"] != "journal-nearby-home" or body["nonce"] != self.nonce or body["home"] != offer["home"]
                    or type(body["name"]) is not str or not 1 <= len(body["name"]) <= 60
                    or type(body["port"]) is not int or not 1024 <= body["port"] <= 65535):
                return
            certificate_key = x509.load_pem_x509_certificate(body["certificate"].encode()).public_key().public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint).hex()
            from cryptography.hazmat.primitives.asymmetric import ec
            offered_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(offer["home_key"])).public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint).hex()
            if certificate_key != offered_key:
                return
            self.found[body["home"]] = body | dict(endpoint=f"https://{address[0]}:{body['port']}/pairing/exchange")
        except (JournalError, ValueError, KeyError, TypeError, AttributeError):
            return


async def nearby_devices(identity, *, port=DISCOVERY_PORT, timeout=0.6, destinations=None, tries=3):
    destinations = broadcast_destinations() if destinations is None else destinations
    if len(destinations) > 8 or not 0.1 <= timeout <= 2 or not 1 <= tries <= 5:
        raise JournalError("Invalid nearby-device search")
    nonce = os.urandom(32).hex()
    inbox = _NearbyInbox(nonce)
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(lambda: inbox, local_addr=("0.0.0.0",0), allow_broadcast=True)
    try:
        wire = seal(dict(type="journal-nearby",nonce=nonce), identity.sign)
        for _ in range(tries):
            for address in destinations:
                transport.sendto(wire,(address,port))
            await asyncio.sleep(timeout / tries)
        return sorted(inbox.found.values(),key=lambda item:(item["name"],item["home"]))[:16]
    finally:
        transport.close()
