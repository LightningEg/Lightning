"""Pairing compares the digits on both screens before any password-derived value leaves the joining device."""
import asyncio
import hashlib
import hmac
import time
from pathlib import Path
from uuid import uuid4

import pytest

from test_journal_finance import devices, groups
from test_journal_nearby import setup
from lightning.runtime.journal_enrollment import NewJournalReplica
from lightning.runtime.journal_pairing import NearbyPairing
from lightning.sync.identity import load_or_create
from lightning.sync.journal.codec import JournalError, canonical, digest, seal, unpack
from lightning.sync.journal.pairing import _password_proof, request_pairing

PASSWORD = "Pairing password"


def home_candidate(hs):
    return unpack(hs.advertise("0"*64, 47513))["body"] | dict(endpoint="https://127.0.0.1:47513/pairing/exchange")


def nearby(devices, wires=None):
    home, pc = devices
    hs = setup(devices)
    hs.begin(PASSWORD)
    candidate = home_candidate(hs)
    async def search(identity):
        return [candidate]
    def factory(endpoint, certificate, timeout):
        async def request(wire):
            if wires is not None:
                wires.append(wire)
            return hs.exchange(wire)
        return request
    return hs, lambda: NearbyPairing(pc, search=search, client_factory=factory)


async def started(devices, wires=None):
    hs, make = nearby(devices, wires)
    ps = make()
    await ps.find()
    await ps.join(ps.screen()["nearby"][0]["id"], hs.screen()["code"])
    return hs, make, ps


def admitted(home, device):
    return home.c.db.scalar("SELECT COUNT(*) FROM journal_origins WHERE device=? AND revoked=0", (device.identity.device_id,))


def other_digits(digits):
    return "000000" if digits != "000000" else "000001"


def test_fake_home_receives_nothing_derived_from_the_password_when_the_user_stops_at_the_digits(tmp_path):
    fake = load_or_create(tmp_path/"fake", "Kitchen laptop")
    salt = bytes(range(16))
    offer = seal(dict(type="journal-pairing", profile=str(uuid4()), generation=1, home=fake.device_id, home_key=fake.public_key,
                      nonce="1"*64, salt=salt.hex(), expires=int(time.time())+600), fake.sign).decode()
    candidate = dict(type="journal-nearby-home", nonce="0"*64, name="Kitchen laptop", home=fake.device_id, offer=offer, port=47513,
                     certificate="fake certificate", endpoint="https://127.0.0.1:47513/pairing/exchange")
    seen = []
    async def search(identity):
        return [candidate]
    def factory(endpoint, certificate, timeout):
        async def request(wire):
            seen.append(wire)
            return seal(dict(type="pairing-wait", request=digest(unpack(wire)["body"])), fake.sign)
        return request
    replica = NewJournalReplica(tmp_path/"new", "New laptop", search=search, client_factory=factory)
    code = "123456"
    async def run():
        found = await replica.find()
        digits = await replica.join(found[0]["id"], code)
        assert len(seen) == 1
        # The attacker's best offline attack: every value it saw, against every password it can guess.
        body = unpack(seen[0])["body"]
        unsigned = {key: value for key, value in body.items() if key != "proof"}
        assert set(body) == {"type", "offer", "device", "name", "key", "incarnation", "proof"}
        assert body["proof"] == hmac.new(code.encode(), canonical(unsigned), hashlib.sha256).hexdigest()
        wire_text = seen[0].decode()
        offered = unpack(offer.encode())["body"]
        for guess in (PASSWORD, "wrong guess"):
            secret = _password_proof(guess, salt)
            for message in (code.encode() + canonical(unsigned), canonical(unsigned), canonical(dict(offer=digest(offered), request=digest(body)))):
                assert hmac.new(secret, message, hashlib.sha256).hexdigest() not in wire_text
            assert secret.hex() not in wire_text and guess not in wire_text
        # The user sees other digits than the real home shows, rejects them, and nothing else is sent.
        with pytest.raises(JournalError):
            replica.compare(other_digits(digits))
        with pytest.raises(JournalError, match="Compare"):
            await replica.prove(PASSWORD)
        with pytest.raises(JournalError):
            await replica.finish(PASSWORD)
        assert len(seen) == 1
        with pytest.raises(JournalError):
            await replica.cancel()
        assert replica.state()["stage"] == "cancelling"
    asyncio.run(run())


def test_mismatched_digits_never_send_the_password_proof_on_a_compatible_replica(devices):
    wires = []
    async def run():
        hs, make, ps = await started(devices, wires)
        assert len(wires) == 2
        with pytest.raises(JournalError, match="same six"):
            ps.compare(other_digits(ps.screen()["pending"]))
        with pytest.raises(JournalError, match="Compare"):
            await ps.prove(PASSWORD)
        assert len(wires) == 2 and ps.screen()["stage"] == "compare"
        await ps.cancel()
        assert ps.screen()["pending"] is None
    asyncio.run(run())


def test_wrong_password_is_refused_and_counts_toward_the_three_attempts(devices):
    home, pc = devices
    async def run():
        hs, make, ps = await started(devices)
        ps.compare(ps.screen()["pending"])
        hs.confirm(hs.screen()["digits"])
        hs.confirm(hs.screen()["digits"])
        for _ in range(2):
            with pytest.raises(JournalError, match="password"):
                await ps.prove("wrong password")
            assert ps.screen()["stage"] == "password" and admitted(home, pc) == 0
        with pytest.raises(JournalError, match="password"):
            await ps.prove("wrong password")
        assert hs.advertise("0"*64, 47513) is None
        with pytest.raises(JournalError, match="expired"):
            await ps.prove(PASSWORD)
        assert admitted(home, pc) == 0 and hs.screen()["code"]
    asyncio.run(run())


@pytest.mark.parametrize("home_first", [True, False])
def test_full_flow_admits_once_in_either_home_order(devices, home_first):
    home, pc = devices
    async def run():
        hs, make, ps = await started(devices)
        assert admitted(home, pc) == 0
        ps.compare(ps.screen()["pending"])
        if home_first:
            hs.confirm(hs.screen()["digits"])
            assert admitted(home, pc) == 0
        await ps.prove(PASSWORD)
        if not home_first:
            assert admitted(home, pc) == 0
            with pytest.raises(JournalError, match="not available"):
                await ps.finish()
            hs.confirm(hs.screen()["digits"])
        assert admitted(home, pc) == 1 and hs.screen()["code"] is None
        await ps.finish()
        assert ps.screen()["paired"] and home.identity.name in ps.screen()["members"]
        epoch = hs.membership.state()["epoch"]
        with pytest.raises(JournalError):
            hs.confirm(hs.screen()["digits"])
        assert hs.membership.state()["epoch"] == epoch and admitted(home, pc) == 1
    asyncio.run(run())


def test_second_request_is_refused_and_a_resent_first_request_is_idempotent(devices, tmp_path):
    home, pc = devices
    async def run():
        hs, make, ps = await started(devices)
        wire = ps._value("pairing_client")["wire"].encode()
        assert hs.desk.accept(wire) == ps.screen()["pending"]
        intruder, _ = request_pairing(hs._value("pairing")["offer"].encode(), hs.screen()["code"], load_or_create(tmp_path/"other", "Other phone"),
                                      str(uuid4()), home_key=home.identity.public_key, secret=b"x"*32)
        with pytest.raises(JournalError, match="already pairing"):
            hs.desk.accept(intruder)
    asyncio.run(run())


def test_restart_between_phase_one_and_two_resumes_without_the_code_and_never_stores_the_password(devices):
    home, pc = devices
    async def run():
        hs, make, ps = await started(devices)
        resumed = make()
        assert resumed.screen()["stage"] == "compare"
        resumed.compare(resumed.screen()["pending"])
        again = make()
        assert again.screen()["stage"] == "password"
        await again.prove(PASSWORD)
        hs.confirm(hs.screen()["digits"])
        saved = [row[0] for row in pc.c.db.execute("SELECT value FROM journal_local").fetchall()]
        assert not any(PASSWORD in str(value) for value in saved)
        await make().finish()
        assert admitted(home, pc) == 1
    asyncio.run(run())


def test_first_replica_resumes_between_phases_and_completes(devices, tmp_path):
    home, _ = devices
    hs = setup(devices)
    home.save(groups(home))
    hs.begin(PASSWORD)
    candidate = home_candidate(hs)
    async def search(identity):
        return [candidate]
    def factory(endpoint, certificate, timeout):
        async def request(wire):
            return hs.enrollment.exchange(wire) if endpoint.endswith("/enrollment/exchange") else hs.exchange(wire)
        return request
    root = tmp_path/"new"
    async def run():
        client = NewJournalReplica(root, "New laptop", search=search, client_factory=factory)
        found = await client.find()
        digits = await client.join(found[0]["id"], hs.screen()["code"])
        assert digits == hs.screen()["digits"]
        restarted = NewJournalReplica(root, "New laptop", search=search, client_factory=factory)
        assert restarted.state()["stage"] == "compare"
        restarted.compare(digits)
        again = NewJournalReplica(root, "New laptop", search=search, client_factory=factory)
        assert again.state()["stage"] == "password"
        with pytest.raises(JournalError, match="numbers"):
            await again.finish(PASSWORD)
        await again.prove(PASSWORD)
        assert PASSWORD not in (root/"enrollment.json").read_text()
        hs.confirm(digits)
        for _ in range(40):
            if await again.finish(PASSWORD, budget=50):
                break
        else:
            pytest.fail("Enrollment did not finish")
        assert (root/"complete.json").exists()
    asyncio.run(run())


def test_devices_screen_walks_code_then_digits_then_password_then_waits(devices):
    import httpx
    from lightning.ui.journal import create_journal_app
    home, pc = devices
    token = "s"*40
    hs, make = nearby(devices)
    app = create_journal_app(pc, session_token=token, pairing=make())
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", cookies={"journal_session": token}) as client:
            async def post(action, **data):
                response = await client.post("/devices/" + action, headers={"origin": "http://test"}, data=dict(__session=token, **data))
                assert response.status_code == 303
                return (await client.get("/devices")).text
            page = await post("find")
            assert 'name="code"' not in page and 'name="password"' not in page
            identifier = page.split('name="candidate" value="')[1].split('"')[0]
            page = await post("join", candidate=identifier, code=hs.screen()["code"])
            digits = hs.screen()["digits"]
            assert "Select the number shown on the other device." in page and digits in page and 'name="password"' not in page
            assert page.count('name="digits" value=') == 3
            page = await post("compare", digits=digits)
            assert 'name="password"' in page and "/devices/prove" in page
            page = await post("prove", password=PASSWORD)
            assert "data-pairing-pending" in page and digits in page
            hs.confirm(digits)
            await post("check")
            assert admitted(home, pc) == 1
    asyncio.run(run())
