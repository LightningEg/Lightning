"""Cloud delivery fault tests with real encrypted cash journals and signed wires."""
import asyncio
import base64
import hashlib
import json
import os

import pytest

from test_journal_finance import devices, groups
from lightning.sync.journal.cloud import (CheckpointTransfer, CloudUnavailable, MailboxExchange,
                                          MailboxPeer, RetryWindow)
from lightning.sync.journal.codec import JournalError
from lightning.sync.journal.local import LocalChannel
from lightning.sync.journal.snapshots import export, repair


class Carrier:
    """The carrier can duplicate/drop opaque bytes but cannot decrypt or decide."""
    def __init__(self):
        self.messages, self.snapshots, self.downloads, self.uploads = {}, {}, [], []
        self.registry, self.membership_updates = None, {}

    def client(self, device):
        carrier = self
        class Client:
            async def call(self, route, data=None):
                data = data or {}
                identity = device.store.config["device"]
                if route == "/authority":
                    if carrier.registry is None:
                        from lightning.sync.journal.membership import Membership
                        from lightning.sync.journal.owner import public_key
                        from types import SimpleNamespace
                        carrier.registry = dict(generation=device.store.config["generation"], membership=1,key_version=1,
                            members={identifier:public_key(SimpleNamespace(public_key=member["key"])) for identifier,member in Membership(device).state()["members"].items()})
                    return json.loads(json.dumps(carrier.registry))
                if route == "/membership":
                    assert data["previous"] == carrier.registry["membership"]
                    carrier.registry.update(membership=data["version"],members=data["members"])
                    if "key_update" in data:
                        carrier.registry["key_version"] = data["key_version"]
                        carrier.membership_updates[data["key_version"]] = data["key_update"]
                    return dict(updated=True)
                if route == "/membership/update":
                    return dict(update=carrier.membership_updates[data["version"]+1],latest=carrier.registry["key_version"])
                if route == "/send":
                    carrier.messages[(data["recipient"], data["id"])] = dict(id=data["id"], sender=identity, wire=data["wire"])
                    return dict(stored=True)
                if route == "/receive":
                    return dict(messages=[value for (recipient, _), value in list(carrier.messages.items()) if recipient == identity][:20])
                if route == "/ack":
                    for message in data["messages"]:
                        carrier.messages.pop((identity, message["id"]), None)
                    return dict(acknowledged=True)
                if route == "/snapshot/start":
                    carrier.snapshots.setdefault(data["id"], data | dict(chunks={}, complete=False))
                    return dict(chunk_size=32768)
                saved = carrier.snapshots[data["id"]]
                if route == "/snapshot/status":
                    return saved | dict(chunks=list(saved["chunks"]))
                if route == "/snapshot/put":
                    saved["chunks"][data["index"]] = dict(bytes=data["bytes"], sha256=data["sha256"])
                    carrier.uploads.append(data["index"])
                    return dict(stored=True)
                if route == "/snapshot/finish":
                    saved["complete"] = True
                    return dict(complete=True)
                if route == "/snapshot/get":
                    assert saved["complete"]
                    carrier.downloads.append(data["index"])
                    return saved["chunks"][data["index"]]
                pytest.fail(route)
        return Client()


def peers(devices, carrier):
    home, pc = devices
    secret = os.urandom(32)
    home_channel = LocalChannel(home, transport_key=secret, peers={pc.identity.device_id: pc.identity.public_key})
    pc_channel = LocalChannel(pc, transport_key=secret, peers={home.identity.device_id: home.identity.public_key})
    return MailboxPeer(home_channel, carrier.client(home)), MailboxPeer(pc_channel, carrier.client(pc))


def test_offline_durable_rpc_and_later_home_edits_converge_without_cached_empty_reply(devices):
    home, pc = devices
    carrier = Carrier()
    hp, pp = peers(devices, carrier)
    pc.save(groups(pc))
    async def sync():
        exchange = MailboxExchange(pp)
        with pytest.raises(CloudUnavailable, match="Queued"):
            await pp.channel.synchronize(exchange, home_id=home.identity.device_id)
        assert pc.store.pending()
        # Restart the local transport objects against their encrypted durable state.
        for _ in range(30):
            await hp.pump()
            try:
                await pp.channel.synchronize(MailboxExchange(pp), home_id=home.identity.device_id)
                break
            except CloudUnavailable:
                continue
        else:
            pytest.fail("Mailbox did not converge after restoring communication")
        assert home.store.fingerprint() == pc.store.fingerprint()
        assert not pc.store.pending()
        home.save(groups(home, "-17"))
        for _ in range(30):
            await hp.pump()
            try:
                await pp.channel.synchronize(MailboxExchange(pp), home_id=home.identity.device_id)
                break
            except CloudUnavailable:
                continue
        assert home.store.fingerprint() == pc.store.fingerprint()
    asyncio.run(sync())


@pytest.mark.parametrize("phase", ["delivery_durable", "delivery_acknowledged", "delivery_processed"])
def test_crash_around_mailbox_ack_cannot_lose_a_proposal(devices, phase):
    home, pc = devices
    carrier = Carrier()
    hp, pp = peers(devices, carrier)
    wire = pc.save(groups(pc))
    request = pp.channel.protect(dict(operation="proposal", value=[base64.b64encode(wire).decode()]), home.identity.device_id)
    pp.enqueue(request)
    class Exit(Exception):
        pass
    def crash(at):
        if at == phase:
            raise Exit
    async def run():
        await pp.pump()
        with pytest.raises(Exit):
            await hp.pump(fault=crash)
        for _ in range(3):
            await hp.pump()
        assert home.store.cursor()["revision"] == 1
        assert next(item for item in home.balances() if item["name"] == "Bank")["balance"] == 990
        assert hp.db.scalar("SELECT COUNT(*) FROM journal_mail_in WHERE processed=0") == 0
    asyncio.run(run())


def test_ciphertext_checkpoint_resumes_verified_chunks_and_preserves_pending(devices, tmp_path):
    home, pc = devices
    home.save(groups(home, "-13"))
    pc.save(groups(pc, "-15"))
    source = tmp_path / "export.db"
    manifest = export(home.store, source, home.identity.sign)
    carrier = Carrier()
    upload = CheckpointTransfer(carrier.client(home), tmp_path / "upload-cache")
    download = CheckpointTransfer(carrier.client(pc), tmp_path / "download-cache")
    async def run():
        while not (await upload.upload(source, manifest, recipient=pc.identity.device_id, public_key=home.identity.public_key, budget=2))["complete"]:
            pass
        assert len(carrier.uploads) == len(set(carrier.uploads))
        while True:
            result = await download.download(manifest, public_key=home.identity.public_key, budget=2)
            if result:
                break
        assert len(carrier.downloads) == len(set(carrier.downloads))
        assert hashlib.sha256(result.read_bytes()).digest() == hashlib.sha256(source.read_bytes()).digest()
        repair(pc.store, result, manifest, source_key=home.c.db.copy_key())
        assert len(pc.store.pending()) == 1
        assert home.store.fingerprint() == pc.store.fingerprint()
    asyncio.run(run())


def test_invalid_manifest_is_refused_before_any_download(devices, tmp_path):
    home, pc = devices
    carrier = Carrier()
    transfer = CheckpointTransfer(carrier.client(pc), tmp_path / "cache")
    with pytest.raises(JournalError):
        asyncio.run(transfer.download(b"{}", public_key=home.identity.public_key))
    assert not carrier.downloads


def test_backoff_uses_bounded_background_windows_and_foreground_can_check_ready():
    now = [0]
    retry = RetryWindow(clock=lambda: now[0], jitter=lambda _: 0)
    assert retry.ready()
    retry.result(False)
    assert not retry.ready()
    now[0] = 10
    assert retry.ready()
    for _ in range(20):
        retry.result(False)
        assert retry.next_attempt - now[0] <= 3600
        now[0] = retry.next_attempt
    retry.result(True)
    assert retry.failures == 0 and retry.next_attempt == now[0] + 30


def test_capability_mismatch_keeps_origin_queue_and_does_not_advance_home(devices, monkeypatch):
    from lightning.sync.journal import compatibility
    from lightning.sync.journal.compatibility import UpdateRequired
    home, pc = devices
    carrier = Carrier()
    hp, pp = peers(devices, carrier)
    original = pc.save(groups(pc))
    real = compatibility.capabilities
    monkeypatch.setattr(compatibility, "capabilities", lambda store: real(store) | (
        dict(entry_kinds={"commands": []}) if store is home.store else {}))
    async def request(wire):
        return hp.channel.handle(wire)
    with pytest.raises(UpdateRequired) as error:
        asyncio.run(pp.channel.synchronize(request, home_id=home.identity.device_id))
    assert error.value.target == "home"
    assert pc.store.pending() == [original]
    assert home.store.cursor()["revision"] == 0
    assert home.c.db.scalar("SELECT COUNT(*) FROM journal_inbox") == 0  # Refused before receiving anything.


def test_forged_reply_capabilities_are_checked_before_any_commit_is_applied(devices):
    from lightning.sync.journal.compatibility import UpdateRequired
    home, pc = devices
    carrier = Carrier()
    hp, pp = peers(devices, carrier)
    original = pc.save(groups(pc))
    async def request(wire):
        _, payload = pp.channel.open(hp.channel.handle(wire))
        payload["result"]["capabilities"]["entry_kinds"]["transaction.add"] = 2
        return hp.channel.protect(payload, pc.identity.device_id)
    with pytest.raises(UpdateRequired) as error:
        asyncio.run(pp.channel.synchronize(request, home_id=home.identity.device_id))
    assert error.value.target == "home"
    assert pc.store.pending() == [original] and pc.store.cursor()["revision"] == 0


def test_bounded_catchup_resumes_without_reapplying_an_edit(devices, monkeypatch):
    from lightning.sync.journal import local
    from lightning.sync.journal.local import CatchupPaused
    monkeypatch.setattr(local, "REPLY_BUDGET", 1)  # One commit per reply.
    home, pc = devices
    carrier = Carrier()
    hp, pp = peers(devices, carrier)
    for amount in ("-5", "-6", "-7"):
        home.save(groups(home, amount))
    async def request(wire):
        return hp.channel.handle(wire)
    with pytest.raises(CatchupPaused):
        asyncio.run(pp.channel.synchronize(request, home_id=home.identity.device_id, max_requests=1))
    assert pc.store.cursor()["revision"] == 1
    asyncio.run(pp.channel.synchronize(request, home_id=home.identity.device_id, max_requests=10))
    assert pc.store.cursor()["revision"] == 3
    assert pc.store.fingerprint() == home.store.fingerprint()


@pytest.mark.parametrize("paired",[False,True])
def test_enrolled_dummy_lab_reopens_with_the_same_authority_and_no_raw_secrets(tmp_path, monkeypatch,paired):
    from lightning.runtime.journal_lab import open_lab
    from lightning.runtime.journal_setup import enroll
    import lightning.sync.journal.owner as owner_module
    monkeypatch.setattr(owner_module, "RECOVERY_MEMORY_KIB", 32768)
    monkeypatch.setattr(owner_module, "RECOVERY_ITERATIONS", 2)
    devices, secret = open_lab(tmp_path, "Dummy password")
    if paired:
        from lightning.sync.journal.membership import Membership
        members = {d.identity.device_id:dict(key=d.identity.public_key,incarnation=d.store.config["incarnation"]) for d in devices}
        for device in devices:
            Membership(device).initialize(members,secret)
    for device in devices:
        device.store.close()
    provision, recovery = enroll(tmp_path, "Dummy password", "Private answer")
    assert "private" not in json.dumps(provision).lower()
    assert recovery not in (tmp_path / "owner-authority.json").read_text()
    devices, _ = open_lab(tmp_path, "Dummy password")
    try:
        assert devices[0].store.authority.can_confirm(devices[0].store)
        assert devices[0].store.config["profile"] == provision["profile"]
        devices[0].save(groups(devices[0]))
    finally:
        for device in devices:
            device.store.authority.close()
            device.store.close()


def test_internet_runtime_coalesces_wakes_and_releases_key_on_close(devices):
    from lightning.runtime.journal_internet import JournalInternet
    from lightning.sync.journal.membership import Membership
    home, pc = devices
    secret = os.urandom(32)
    members = {device.identity.device_id:dict(key=device.identity.public_key,incarnation=device.store.config["incarnation"]) for device in devices}
    for device in devices:
        Membership(device).initialize(members, secret)
    carrier = Carrier()
    runtime = JournalInternet(home, "https://configured.example", client=carrier.client(home))
    async def run():
        assert await runtime.catch_up(foreground=True)
        assert not await runtime.catch_up()
        await runtime.close()
        assert not runtime.channel.key
        assert not await runtime.catch_up(foreground=True)
    asyncio.run(run())


def test_cloud_membership_rotation_keeps_existing_pair_and_original_pending_edit(devices, tmp_path):
    from lightning.runtime.journal_internet import JournalInternet
    from lightning.sync.journal.membership import Membership
    from lightning.sync.identity import load_or_create
    from uuid import uuid4
    home, pc = devices
    members = {d.identity.device_id:dict(key=d.identity.public_key,incarnation=d.store.config["incarnation"]) for d in devices}
    secret = os.urandom(32)
    for device in devices:
        Membership(device).initialize(members,secret)
    carrier = Carrier()
    hr = JournalInternet(home,"https://configured.example",client=carrier.client(home))
    pr = JournalInternet(pc,"https://configured.example",client=carrier.client(pc))
    original = pc.save(groups(pc))
    async def run():
        # Persist an old-epoch request while the home is unavailable.
        assert not await pr.catch_up(foreground=True)
        newcomer = load_or_create(tmp_path/'new','New device')
        Membership(home).rotate(members | {newcomer.device_id:dict(key=newcomer.public_key,incarnation=str(uuid4()))})
        for _ in range(12):
            await hr.catch_up(foreground=True)
            await pr.catch_up(foreground=True)
            if not pc.store.pending():
                break
        assert not pc.store.pending()
        assert Membership(pc).state()["epoch"] == 2
        assert home.store.fingerprint() == pc.store.fingerprint()
        assert home.c.db.scalar("SELECT COUNT(*) FROM journal_inbox WHERE wire=?",(original,)) == 1
        await hr.close()
        await pr.close()
    asyncio.run(run())
