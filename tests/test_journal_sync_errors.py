"""BT-4J: sync and pairing say what went wrong instead of looking offline forever."""
import asyncio
import os

import pytest

from test_journal_finance import devices, groups  # noqa: F401  (devices is a fixture)
from lightning.runtime.journal_pairing import NearbyPairing
from lightning.runtime.journal_routes import LocalFirstSync
from lightning.sync.journal.errors import DeviceRevoked
from lightning.sync.journal.local import LocalChannel
from lightning.sync.journal.membership import Membership


def paired(devices):
    home, pc = devices
    members = {d.identity.device_id: dict(key=d.identity.public_key, incarnation=d.store.config["incarnation"]) for d in devices}
    secret = os.urandom(32)
    hm, pm = Membership(home), Membership(pc)
    hm.initialize(members, secret)
    pm.initialize(members, secret)
    server = LocalChannel(home, transport_key=secret, peers={pc.identity.device_id: pc.identity.public_key})
    client = LocalChannel(pc, transport_key=secret, peers={home.identity.device_id: home.identity.public_key})
    hm.bind(server)
    pm.bind(client)

    def factory(endpoint, certificate, timeout):
        async def request(wire):
            return hm.control(wire) if "/membership/" in endpoint else server.handle(wire)
        return request

    router = LocalFirstSync(pc, client, home_id=home.identity.device_id, certificate="saved certificate",
                            endpoints=["https://127.0.0.1:47513/exchange"], client_factory=factory)
    return NearbyPairing(home), NearbyPairing(pc), router


def test_a_removed_device_learns_it_on_contact_and_stops_saying_paired(devices):
    home, pc = devices
    hs, ps, router = paired(devices)
    assert ps.screen()["paired"]
    hs.revoke(pc.identity.device_id)
    # Before contact its own copy still lists it: that is all it can know.
    assert ps.screen()["paired"]
    pc.save(groups(pc))
    with pytest.raises(DeviceRevoked):
        asyncio.run(router.synchronize())
    screen = ps.screen()
    assert not screen["paired"] and screen["revoked"]
    assert Membership(pc).revoked()
    assert pc.store.pending(), "a removed device's unsent edit is kept here, not admitted"


def test_a_device_still_paired_after_another_is_removed_keeps_syncing(devices, tmp_path):
    from uuid import uuid4
    from lightning.sync.identity import load_or_create
    home, pc = devices
    hs, ps, router = paired(devices)
    other = load_or_create(tmp_path / "other", "Other device")
    hm = Membership(home)
    members = dict(hm.state()["members"])
    hm.rotate(members | {other.device_id: dict(key=other.public_key, incarnation=str(uuid4()))})
    hs.revoke(other.device_id)
    pc.save(groups(pc))
    assert asyncio.run(router.synchronize())
    assert ps.screen()["paired"] and not ps.screen()["revoked"]
    assert not pc.store.pending()


def test_over_http_the_home_asks_for_a_membership_update_instead_of_refusing(devices, tmp_path):
    import httpx
    from lightning.sync.identity import load_or_create
    from lightning.sync.journal.codec import seal
    from lightning.ui.journal import create_journal_app
    home, pc = devices
    hs, ps, router = paired(devices)
    hs.revoke(pc.identity.device_id)
    server = LocalChannel(home, transport_key=os.urandom(32), peers={})
    Membership(home).bind(server)
    app = create_journal_app(home, session_token="s" * 40, channel=server)
    removed = router.channel.protect(dict(operation="capabilities", value=None), home.identity.device_id)
    stranger = load_or_create(tmp_path / "stranger", "Stranger")
    forged = seal(__import__("lightning.sync.journal.codec", fromlist=["unpack"]).unpack(removed)["body"]
                  | dict(sender=stranger.device_id), stranger.sign)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            answer = await client.post("/exchange", content=removed)
            assert answer.status_code == 409 and answer.headers["X-Journal-Action"] == "membership"
            assert (await client.post("/exchange", content=forged)).status_code == 403
    asyncio.run(run())


def native_app(device, pairing, **journal):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from lightning.runtime.journal_ui_routes import journal_ui_router
    session = SimpleNamespace(token="dummy-native-token", container=None,
                              journal=SimpleNamespace(device=device, pairing=pairing, trust=None, **journal))
    app = FastAPI()
    app.include_router(journal_ui_router(session))
    return app, session


def page(app, path="/journal/devices"):
    import httpx

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            return (await client.get(path)).text
    return asyncio.run(run())


def test_the_removed_devices_own_screen_says_so_and_keeps_the_reason(devices):
    home, pc = devices
    hs, ps, router = paired(devices)
    hs.revoke(pc.identity.device_id)
    with pytest.raises(DeviceRevoked) as raised:
        asyncio.run(router.synchronize())
    assert pc.record_sync_error(raised.value) == "revoked"
    assert pc.sync_status()["error"]["kind"] == "revoked"
    app, _ = native_app(pc, ps)
    text = page(app)
    assert "The home removed this device, so it no longer syncs." in text
    assert "This device is paired" not in text and "Last tried" in text


def test_a_refusal_is_kept_with_its_class_message_and_time_and_cleared_by_a_good_round(devices):
    from lightning.runtime.journal_profile import JournalRuntime
    from lightning.sync.journal.codec import JournalError
    from lightning.sync.journal.errors import HomeRefused
    _, pc = devices
    runtime = object.__new__(JournalRuntime)
    runtime.closed, runtime.device = False, pc
    outcomes = [JournalError("Verified checkpoint required"), DeviceRevoked("The home removed this device"), "idle"]

    async def round_():
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    runtime._round = round_
    with pytest.raises(JournalError):
        asyncio.run(runtime._sync_round())
    saved = pc.sync_status()["error"]
    assert saved["kind"] == "error" and saved["error"] == "JournalError" and saved["message"] == "Verified checkpoint required"
    assert saved["shown"][:4].isdigit()
    assert asyncio.run(runtime._sync_round()) == "revoked"
    assert pc.sync_status()["error"]["kind"] == "revoked"
    assert asyncio.run(runtime._sync_round()) == "idle"
    assert pc.sync_status()["error"] is None
    assert pc.record_sync_error(HomeRefused("Home frozen")) == "refused"


def test_android_says_refused_or_revoked_instead_of_offline(tmp_path):
    from lightning.runtime import journal_android
    from lightning.sync.journal.codec import JournalError

    async def run():
        loop = asyncio.get_running_loop()
        owner = object()

        async def refused():
            raise JournalError("The local home refused this sync request")

        async def revoked():
            return "revoked"
        try:
            journal_android.register(tmp_path, owner, loop, refused)
            assert await journal_android.sync_once(tmp_path) == "refused"
            journal_android.register(tmp_path, owner, loop, revoked)
            assert await journal_android.sync_once(tmp_path) == "revoked"
        finally:
            journal_android.unregister(tmp_path, owner)
    asyncio.run(run())


def test_a_screen_that_cannot_be_read_says_so_instead_of_pairing_disabled(devices):
    _, pc = devices

    class Broken:
        def screen(self):
            raise ValueError("damaged pairing state")
    app, session = native_app(pc, Broken(), discovery_error="OSError: [Errno 98] Address already in use")
    text = page(app)
    assert "Pairing could not read this device&#39;s saved state." in text and "damaged pairing state" in text
    assert "Nearby pairing is unavailable." not in text
    session.journal.pairing = None
    text = page(app)
    assert "Nearby pairing is unavailable." in text
    assert "Nearby search could not start on this device." in text


def test_a_joiner_whose_pairing_expires_part_way_is_told_and_offered_cancel(devices, monkeypatch):
    import time
    from test_journal_pairing import PASSWORD, started
    from lightning.runtime import journal_pairing
    from lightning.sync.journal.codec import unpack

    async def run():
        hs, make, ps = await started(devices)
        ps.compare(ps.screen()["pending"])
        await ps.prove(PASSWORD)
        assert ps.screen()["stage"] == "waiting" and not ps.screen()["expired"]
        app, session = native_app(devices[1], ps)
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            await client.post("/journal/devices/poll", data={"__session": session.token})
            assert ps.screen()["problem"] is None  # waiting for approval is not a problem
            expires = unpack(hs._value("pairing")["offer"].encode())["body"]["expires"]
            hs.desk.clock = lambda: expires + 61
            monkeypatch.setattr(journal_pairing.time, "time", lambda: expires + 61)
            await client.post("/journal/devices/poll", data={"__session": session.token})
            screen = ps.screen()
            assert screen["expired"] and screen["problem"]
            text = (await client.get("/journal/devices")).text
            assert "ten minutes are up" in text and "/journal/devices/cancel" in text
        assert time.time() == expires + 61
    asyncio.run(run())


def test_every_new_line_has_its_arabic():
    from lightning.ui.journal_i18n import AR, translate_journal
    from lightning.runtime.journal_pairing import DIFFERENT_LEDGER
    from lightning.runtime.journal_ui_routes import REMOVED
    from lightning.sync.journal.pairing import CLOCKS_DIFFER, OFFER_EXPIRED
    for line in (REMOVED, DIFFERENT_LEDGER, CLOCKS_DIFFER, OFFER_EXPIRED, "Last tried",
                 "The home refused the last sync. Your edits stay saved here, and it tries again.",
                 "The last sync did not finish. Your edits stay saved here, and it tries again.",
                 "Pairing could not read this device's saved state.",
                 "Nearby search could not start on this device. Close Lightning and open it again to retry.",
                 "This pairing's ten minutes are up. If the home no longer shows it, cancel here and start again.",
                 "The last step did not go through:"):
        assert line in AR and translate_journal(line, "ar") == AR[line] and not any("a" <= c <= "z" for c in AR[line].replace("Lightning", ""))
