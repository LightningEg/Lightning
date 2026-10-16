"""First-device enrollment publishes only verified ciphertext and a fresh identity."""
import asyncio
from pathlib import Path

import pytest

from test_journal_finance import devices, groups
from test_journal_nearby import setup
from lightning.bootstrap import build
from lightning.runtime.journal_enrollment import NewJournalReplica
from lightning.runtime.session import read_slot
from lightning.security.keys import unwrap_key
from lightning.sync.journal.codec import JournalError, unpack
from lightning.sync.journal.device import JournalDevice
from lightning.sync.journal.finance import attach
from lightning.sync.journal.local import LocalChannel
from lightning.sync.journal.membership import Membership


@pytest.mark.parametrize("failure",[None,"corrupt","publication","owner","identity"])
def test_first_device_pairs_once_resumes_ciphertext_download_and_joins_exact_ledger(devices,tmp_path,monkeypatch,failure):
    home,_ = devices
    hs = setup(devices)
    control = None
    if failure == "owner":
        from lightning.sync.journal.authority import AuthorityMemory
        from lightning.sync.journal.owner import OwnerCredential
        from lightning.sync.journal.codec import seal
        import lightning.sync.journal.owner as module
        monkeypatch.setattr(module,"RECOVERY_MEMORY_KIB",32768)
        monkeypatch.setattr(module,"RECOVERY_ITERATIONS",2)
        owner,wrapper = OwnerCredential.create(home.store.config["profile"],password="Pairing password",recovery="1234-5678-9012",answer="Cairo")
        config = home.store.config
        root_wire = seal(dict(type="authority-enrollment",version=1,profile=config["profile"],generation=config["generation"],home=config["device"],home_key=config["home_key"],owner_key=owner.public_key),owner.sign)
        control = AuthorityMemory.enroll(tmp_path/'home-control.db',root_wire)
        control.bind(home.store)
        hs.enrollment.owner = lambda:wrapper
    home.save(groups(home))
    hs.begin("Pairing password")
    candidate = unpack(hs.advertise("0"*64,47513))["body"] | dict(endpoint="https://127.0.0.1:47513/pairing/exchange")
    async def search(identity):
        return [candidate]
    downloads = []
    def factory(endpoint,certificate,timeout):
        assert certificate == home.identity.cert_path.read_text()
        async def request(wire):
            if endpoint.endswith('/enrollment/exchange'):
                body = unpack(wire)["body"]
                if body["operation"] == "chunk":
                    downloads.append(body["index"])
                return hs.enrollment.exchange(wire)
            return hs.exchange(wire)
        return request
    root = tmp_path/'new-device'
    client = NewJournalReplica(root,"New laptop",search=search,client_factory=factory)
    async def run():
        found = await client.find()
        digits = await client.join(found[0]["id"],hs.screen()["code"],"Pairing password")
        assert not (root/'ledger.db').exists()
        with pytest.raises(JournalError):
            await client.finish("Pairing password")
        assert digits == hs.screen()["digits"]
        hs.confirm(digits)
        assert not await client.finish("Pairing password",budget=1)
        first_chunk = downloads[0]
        if failure == "identity":
            private = root/'identity'/'device-key.pem'
            private.unlink()
            with pytest.raises(JournalError,match="identity is missing"):
                NewJournalReplica(root,"New laptop",search=search,client_factory=factory)
            assert not private.exists()
            assert not (root/'ledger.db').exists()
            return
        if failure == "corrupt":
            checkpoint = next((Path(home.c.db.path).parent/'.journal-enrollment').glob('*.db'))
            with checkpoint.open('r+b') as handle:
                handle.seek(-1,2)
                value = handle.read(1)
                handle.seek(-1,2)
                handle.write(bytes([value[0]^1]))
            with pytest.raises(JournalError,match="hash mismatch"):
                await client.finish("Pairing password",budget=2000)
            assert not (root/'ledger.db').exists()
            return
        if failure == "publication":
            import lightning.runtime.journal_enrollment as module
            publish = module.write_slot
            def interrupt(path,*args,**kwargs):
                if path.name == "complete.json":
                    raise OSError("Process stopped before completion marker")
                return publish(path,*args,**kwargs)
            monkeypatch.setattr(module,'write_slot',interrupt)
        # A new process can resume with its saved identity, without a new code.
        restarted = NewJournalReplica(root,"New laptop",search=search,client_factory=factory)
        for _ in range(20):
            try:
                if await restarted.finish("Pairing password",budget=50):
                    break
            except OSError:
                assert failure == "publication" and (root/'ledger.db').exists()
                monkeypatch.setattr(module,'write_slot',publish)
                def offline(*args,**kwargs):
                    pytest.fail("Publication repair should use its verified local intent")
                restarted = NewJournalReplica(root,"New laptop",client_factory=offline)
                assert await restarted.finish("Pairing password")
                break
        else:
            pytest.fail("Enrollment did not finish")
        assert downloads.count(first_chunk) == 1
        assert await restarted.finish("Pairing password")
        key = unwrap_key(read_slot(root/'keys.json'),"Pairing password")
        container = build(root/'ledger.db',key=key,experimental_journal=True)
        memory = None
        try:
            replica = JournalDevice(attach(container),restarted.identity)
            assert replica.store.fingerprint() == home.store.fingerprint()
            assert not replica.store.pending()
            if failure == "owner":
                from lightning.runtime.session import AttemptGuard
                from lightning.sync.journal.authority import AuthorityMemory
                from lightning.sync.journal.owner import OwnerCredential
                copied = read_slot(root/'owner-authority.json')
                reopened_owner = OwnerCredential.unlock(copied,dict(password="Pairing password",answer="Cairo"),guard=AttemptGuard(root/'attempts.json'))
                assert reopened_owner.public_key == owner.public_key
                marker = read_slot(root/'complete.json')
                assert Path(marker["authority"]).parent != root
                memory = AuthorityMemory(marker["authority"],profile=replica.store.config["profile"])
                assert memory.state()["generation"] == home.store.config["generation"]
                memory.bind(replica.store)
                assert replica.c.db.scalar("SELECT value FROM journal_local WHERE name='authority_enrolled'") == '1'
            assert replica.store.config["device"] != home.store.config["device"]
            assert replica.c.db.scalar("SELECT next_seq FROM journal_meta") == 1
            assert not replica.c.db.scalar("SELECT COUNT(*) FROM journal_local WHERE name LIKE 'pairing%'")
            secret = bytes.fromhex(home.c.db.scalar("SELECT value FROM journal_local WHERE name='transport'"))
            server = LocalChannel(home,transport_key=secret,peers={replica.identity.device_id:replica.identity.public_key})
            channel = LocalChannel(replica,transport_key=secret,peers={home.identity.device_id:home.identity.public_key})
            Membership(home).bind(server); Membership(replica).bind(channel)
            replica.save(groups(replica,"-7"))
            async def exchange(wire):
                return server.handle(wire)
            await channel.synchronize(exchange,home_id=home.identity.device_id)
            assert not replica.store.pending()
            assert replica.store.fingerprint() == home.store.fingerprint()
        finally:
            if memory:
                memory.close()
            container.db.close()
    try:
        asyncio.run(run())
    finally:
        if control:
            control.close()


def test_enrollment_refuses_unrelated_directory_without_creating_an_identity(tmp_path):
    saved = tmp_path/'keep.txt'
    saved.write_text('Keep this file')
    with pytest.raises(JournalError,match="empty private directory"):
        NewJournalReplica(tmp_path,"New laptop")
    assert saved.read_text() == 'Keep this file'
    assert not (tmp_path/'identity').exists()
