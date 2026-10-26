"""Nearby discovery and numeric pairing never ask the user for an endpoint."""
import asyncio
import json
import os

import httpx
import pytest

from test_journal_finance import devices, groups
from lightning.runtime.journal_pairing import NearbyPairing
from lightning.runtime.journal_routes import LocalFirstSync
from lightning.security.keys import create_key_file
from lightning.sync.journal.codec import JournalError, seal
from lightning.sync.journal.discovery import LanResponder, nearby_devices
from lightning.sync.journal.local import LocalChannel
from lightning.sync.journal.membership import Membership
from lightning.sync.journal.pairing import normalize_code
from lightning.ui.journal import create_journal_app


def test_numeric_pairing_accepts_arabic_digits_and_refuses_other_shapes():
    assert normalize_code("٠١٢ ٣٤٥") == "012345"
    assert normalize_code("۰۱۲-۳۴۵") == "012345"
    for value in ("12345","1234567","ABCDEF",None):
        with pytest.raises(JournalError):
            normalize_code(value)


def setup(devices):
    home, pc = devices
    home_only = {home.identity.device_id:dict(key=home.identity.public_key,incarnation=home.store.config["incarnation"])}
    secret = os.urandom(32)
    Membership(home).initialize(home_only,secret)
    Membership(pc).initialize(home_only,os.urandom(32))
    home.c.db.execute("DELETE FROM journal_origins WHERE device=?",(pc.identity.device_id,))
    keys = create_key_file(home.c.db.copy_key(),"Pairing password","1234-5678-9012","School?","Cairo")
    hs = NearbyPairing(home,key_document=lambda:keys)
    return hs


def test_nearby_number_and_confirmation_admit_once_then_sync_without_another_prompt(devices):
    home, pc = devices
    hs = setup(devices)
    hs.begin("Pairing password")
    code = hs.screen()["code"]
    assert code.isdecimal() and len(code) == 6
    body = __import__('lightning.sync.journal.codec',fromlist=['unpack']).unpack(hs.advertise("0"*64,47513))["body"]
    candidate = body | dict(endpoint="https://127.0.0.1:47513/pairing/exchange")
    async def search(identity):
        return [candidate]
    def factory(endpoint,certificate,timeout):
        assert certificate == home.identity.cert_path.read_text()
        async def request(wire):
            return hs.exchange(wire)
        return request
    ps = NearbyPairing(pc,search=search,client_factory=factory)
    async def run():
        assert await ps.find() == 1
        identifier = ps.screen()["nearby"][0]["id"]
        await ps.join(identifier,code)
        assert home.c.db.scalar("SELECT COUNT(*) FROM journal_origins WHERE device=?",(pc.identity.device_id,)) == 0
        assert hs.screen()["digits"] == ps.screen()["pending"]
        ps.compare(ps.screen()["pending"])
        hs.confirm(hs.screen()["digits"])
        assert hs.screen()["confirmed"] and hs.screen()["code"]
        with pytest.raises(JournalError):
            await ps.finish()
        await ps.prove("Pairing password")
        await ps.finish()
        assert ps.screen()["paired"]
        assert home.c.db.scalar("SELECT revoked FROM journal_origins WHERE device=?",(pc.identity.device_id,)) == 0
        assert home.c.db.scalar("SELECT value FROM journal_local WHERE name='transport'") == pc.c.db.scalar("SELECT value FROM journal_local WHERE name='transport'")
        assert home.identity.name in ps.screen()["members"]
        secret = bytes.fromhex(home.c.db.scalar("SELECT value FROM journal_local WHERE name='transport'"))
        server = LocalChannel(home,transport_key=secret,peers={pc.identity.device_id:pc.identity.public_key})
        client = LocalChannel(pc,transport_key=secret,peers={home.identity.device_id:home.identity.public_key})
        Membership(home).bind(server)
        Membership(pc).bind(client)
        def local_factory(endpoint,certificate,timeout):
            async def request(wire):
                return server.handle(wire)
            return request
        pc.save(groups(pc))
        router = LocalFirstSync(pc,client,home_id=home.identity.device_id,certificate=candidate["certificate"],client_factory=local_factory)
        assert await router.synchronize()
        assert not pc.store.pending()
        assert home.store.fingerprint() == pc.store.fingerprint()
    asyncio.run(run())


def test_nearby_discovery_only_advertises_while_home_pairing_is_open(devices):
    home, pc = devices
    hs = setup(devices)
    secret = bytes.fromhex(home.c.db.scalar("SELECT value FROM journal_local WHERE name='transport'"))
    channel = LocalChannel(home,transport_key=secret,peers={})
    async def run():
        loop = asyncio.get_running_loop()
        transport,_ = await loop.create_datagram_endpoint(lambda:LanResponder(channel,tls_port=47513,nearby=hs.advertise),local_addr=("127.0.0.1",0))
        try:
            port = transport.get_extra_info("sockname")[1]
            assert await nearby_devices(pc.identity,port=port,timeout=0.1,destinations=("127.0.0.1",)) == []
            hs.begin("Pairing password")
            found = await nearby_devices(pc.identity,port=port,timeout=0.1,destinations=("127.0.0.1",))
            assert len(found) == 1 and found[0]["name"] == home.identity.name
            assert "code" not in found[0] and "verifier" not in found[0]
            hs.stop()
            assert await nearby_devices(pc.identity,port=port,timeout=0.1,destinations=("127.0.0.1",)) == []
        finally:
            transport.close()
    asyncio.run(run())


def test_device_screen_has_numeric_pairing_and_no_address_or_port_fields(devices):
    home,_ = devices
    hs = setup(devices)
    app = create_journal_app(home,session_token="s"*40,pairing=hs)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test",cookies={"journal_session":"s"*40}) as client:
            response = await client.post("/devices/open",headers={"origin":"http://test"},data=dict(__session="s"*40,password="Pairing password"))
            assert response.status_code == 303
            page = await client.get("/devices",headers={"user-agent":"Android Mobile"})
            assert page.status_code == 200
            assert "Pair a device" in page.text and "Nearby devices" in page.text
            assert hs.screen()["code"] not in page.text
            assert 'name="port"' not in page.text and 'name="address"' not in page.text
            response = await client.post("/pairing/exchange",content=b'{}')
            assert response.status_code == 403
            assert "s"*40 not in response.text and "Confirmed balances" not in response.text
            response = await client.post("/pairing/exchange",content=b"x"*4097)
            assert response.status_code == 413
    asyncio.run(run())


def test_existing_pair_gets_rotated_key_automatically_without_repairing(devices, tmp_path):
    from lightning.sync.identity import load_or_create
    home, pc = devices
    members = {d.identity.device_id:dict(key=d.identity.public_key,incarnation=d.store.config["incarnation"]) for d in devices}
    secret = os.urandom(32)
    hm, pm = Membership(home),Membership(pc)
    hm.initialize(members,secret)
    pm.initialize(members,secret)
    server = LocalChannel(home,transport_key=secret,peers={pc.identity.device_id:pc.identity.public_key})
    client = LocalChannel(pc,transport_key=secret,peers={home.identity.device_id:home.identity.public_key})
    hm.bind(server); pm.bind(client)
    newcomer = load_or_create(tmp_path/'new','New device')
    from uuid import uuid4
    hm.rotate(members | {newcomer.device_id:dict(key=newcomer.public_key,incarnation=str(uuid4()))})
    pc.save(groups(pc))
    def factory(endpoint,certificate,timeout):
        async def request(wire):
            return hm.control(wire) if '/membership/' in endpoint else server.handle(wire)
        return request
    router = LocalFirstSync(pc,client,home_id=home.identity.device_id,certificate="saved certificate",
                          endpoints=['https://127.0.0.1:47513/exchange'],client_factory=factory)
    assert asyncio.run(router.synchronize())
    assert hm.state()["epoch"] == pm.state()["epoch"] == 2
    assert not pc.store.pending() and home.store.fingerprint() == pc.store.fingerprint()


def test_saved_device_discovers_changed_home_address_after_key_rotation_but_revoked_device_cannot(devices, tmp_path):
    from lightning.sync.identity import load_or_create
    from lightning.sync.journal.discovery import discover
    from uuid import uuid4
    home, pc = devices
    members = {d.identity.device_id:dict(key=d.identity.public_key,incarnation=d.store.config["incarnation"]) for d in devices}
    secret = os.urandom(32)
    hm,pm = Membership(home),Membership(pc)
    hm.initialize(members,secret); pm.initialize(members,secret)
    server = LocalChannel(home,transport_key=secret,peers={pc.identity.device_id:pc.identity.public_key})
    client = LocalChannel(pc,transport_key=secret,peers={home.identity.device_id:home.identity.public_key})
    hm.bind(server); pm.bind(client)
    newcomer = load_or_create(tmp_path/'new','New device')
    hm.rotate(members | {newcomer.device_id:dict(key=newcomer.public_key,incarnation=str(uuid4()))})
    async def run():
        loop = asyncio.get_running_loop()
        transport,_ = await loop.create_datagram_endpoint(lambda:LanResponder(server,tls_port=47513),local_addr=("127.0.0.1",0))
        try:
            port = transport.get_extra_info("sockname")[1]
            # There is no cached address and the client still has epoch one.
            found = await discover(client,home.identity.device_id,port=port,timeout=0.1,destinations=("127.0.0.1",))
            assert found == ["https://127.0.0.1:47513/exchange"]
            assert pm.state()["epoch"] == 1
            await pm.catch_up(lambda wire:async_answer(hm.control(wire)),home.identity.device_id)
            assert pm.state()["epoch"] == 2
            hm.rotate({home.identity.device_id:members[home.identity.device_id]})
            assert await discover(client,home.identity.device_id,port=port,timeout=0.1,destinations=("127.0.0.1",)) == []
        finally:
            transport.close()
    async def async_answer(value):
        return value
    asyncio.run(run())
