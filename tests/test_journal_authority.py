"""Owner proof, durable home fencing, retirement and transport-key revocation."""
import asyncio
import json
import os
from itertools import combinations
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from test_journal_finance import devices, groups
from lightning.runtime.session import AttemptGuard, ProfileError
from lightning.sync.identity import load_or_create
from lightning.sync.journal.authority import AuthorityMemory, AuthorityRegistry, transfer_home_state
from lightning.sync.journal.codec import JournalError, digest, seal, unpack
from lightning.sync.journal.home import JournalHome
from lightning.sync.journal.membership import Membership
from lightning.sync.journal.owner import OwnerCredential, public_key


def memories(devices, tmp_path):
    home, pc = devices
    owner = OwnerCredential(ec.generate_private_key(ec.SECP256R1()))
    config = home.store.config
    wire = seal(dict(type="authority-enrollment", version=1, profile=config["profile"], generation=config["generation"],
                     home=config["device"], home_key=config["home_key"], owner_key=owner.public_key), owner.sign)
    result = [AuthorityMemory.enroll(tmp_path / f"control-{i}.db", wire) for i in range(2)]
    for device, memory in zip(devices, result):
        memory.bind(device.store)
    return owner, result


def change(home, pc, owner, *, mode="move"):
    return seal(dict(profile=home.store.config["profile"], previous=home.store.config["generation"],
                     generation=str(uuid4()), home=pc.identity.device_id, home_key=public_key(pc.identity),
                     owner_key=owner.public_key, version=2, mode=mode, nonce=os.urandom(32).hex(), cutoff=pc.store.cursor()), owner.sign)


def test_each_two_secret_pair_opens_independent_owner_key_but_one_secret_and_data_key_do_not(tmp_path, monkeypatch):
    import lightning.sync.journal.owner as module
    monkeypatch.setattr(module, "RECOVERY_MEMORY_KIB", 32768)
    monkeypatch.setattr(module, "RECOVERY_ITERATIONS", 2)
    values = dict(password="profile password", recovery="1234-5678-9012", answer="First school")
    original, document = OwnerCredential.create(str(uuid4()), **values)
    guard = AttemptGuard(tmp_path / "attempts.json")
    for pair in combinations(values, 2):
        opened = OwnerCredential.unlock(document, {name: values[name] for name in pair}, guard=guard)
        assert opened.public_key == original.public_key
    with pytest.raises(JournalError):
        OwnerCredential.unlock(document, dict(password=values["password"]), guard=guard)
    wrong = dict(password=values["password"], answer="wrong answer")
    for _ in range(4):
        with pytest.raises(JournalError):
            OwnerCredential.unlock(document, wrong, guard=guard)
    with pytest.raises(ProfileError, match="Too many"):
        OwnerCredential.unlock(document, dict(password=values["password"], answer=values["answer"]), guard=guard)
    assert "private" not in json.dumps(document)
    changed = dict(document, profile=str(uuid4()))
    with pytest.raises(JournalError):
        OwnerCredential.unlock(changed, dict(password=values["password"], recovery=values["recovery"]), guard=AttemptGuard(tmp_path / "other.json"))


def test_frozen_home_cannot_confirm_or_review_and_missing_control_never_resets(devices, tmp_path):
    home, pc = devices
    owner, controls = memories(devices, tmp_path)
    try:
        home.save(groups(home))
        controls[0].freeze(home.store)
        with pytest.raises(JournalError, match="frozen|retired"):
            home.home.process()
        home.store.authority = None
        with pytest.raises(JournalError, match="required"):
            home.home.process()
        with pytest.raises(JournalError, match="missing"):
            AuthorityMemory(tmp_path / "missing.db", profile=home.store.config["profile"])
    finally:
        for control in controls:
            control.close()


def test_cooperative_move_retires_old_home_before_activation_and_keeps_original_pending_ids(devices, tmp_path):
    home, pc = devices
    owner, controls = memories(devices, tmp_path)
    try:
        home.save(groups(home))
        pc.sync_with(home.home)
        queued = pc.save(groups(pc, "-8"))
        controls[0].freeze(home.store)
        transfer_home_state(home.store, pc.store)
        wire = change(home, pc, owner)
        prepared = controls[1].prepare(pc.store, wire, pc.identity.sign)
        with pytest.raises(JournalError):
            controls[1].activate_move(pc.store, wire, prepared, prepared, old_home_key=home.identity.public_key)
        assert controls[1].state()["phase"] == "prepared"
        retired = controls[0].retire(home.store, wire, prepared, home.identity.sign)
        assert controls[0].state()["phase"] == "retired"
        controls[1].activate_move(pc.store, wire, prepared, retired, old_home_key=home.identity.public_key)
        pc.home = JournalHome(pc.store, pc.identity.sign)
        pc.flush_home()
        assert not pc.store.pending()
        assert pc.store.cursor()["revision"] == 2
        assert pc.store.db.scalar("SELECT wire FROM journal_outbox WHERE seq=1") == queued
        with pytest.raises(JournalError):
            home.home.process()
        with pytest.raises(JournalError, match="Stale|competing"):
            controls[1].observe(wire, local_device=pc.identity.device_id)
    finally:
        for control in controls:
            control.close()


def test_signed_lan_move_transfers_checkpoint_and_retires_before_target_activation(devices, tmp_path, monkeypatch):
    """Exercise the bounded exchange protocol end to end without opening a socket."""
    import json
    from types import SimpleNamespace
    import lightning.runtime.journal_move as move_module
    from lightning.runtime.journal_move import JournalMoveRuntime
    from lightning.sync.journal.codec import JournalError
    from lightning.sync.journal.membership import Membership

    home, pc = devices
    owner, controls = memories(devices, tmp_path)
    try:
        members = {
            item.identity.device_id: dict(key=item.identity.public_key, incarnation=item.store.config["incarnation"])
            for item in devices
        }
        shared = os.urandom(32)
        for item in devices:
            Membership(item)._save(dict(version=1, epoch=1, members=members, retired=[]), shared)
        for identifier, member in members.items():
            home.home.approve_origin(identifier, member["incarnation"], member["key"])
        large_command = pc.command("bank_imports.confirm", batch_id=str(uuid4()),
                                   decisions={str(index): {"notes": "x" * 150} for index in range(200)})
        assert len(large_command) > 20 * 1024
        assert home.home.receive(large_command) == "staged"
        pc.sync_with(home.home)  # Drain the replica outbox before the move safety gate.
        assert not pc.store.pending()
        assert home.store.db.scalar("SELECT status FROM journal_inbox") == "rejected"
        home_path, pc_path = tmp_path / "home-profile", tmp_path / "replica-profile"
        home_path.mkdir(); pc_path.mkdir()
        home_runtime = SimpleNamespace(device=home, identity=home.identity, paths=SimpleNamespace(data_dir=home_path))
        pc_runtime = SimpleNamespace(device=pc, identity=pc.identity, paths=SimpleNamespace(data_dir=pc_path))
        source = JournalMoveRuntime(home_runtime)
        pc.store.db.execute("INSERT OR REPLACE INTO journal_local VALUES('local_endpoints',?)",
                            (json.dumps(["https://127.0.0.1:47513/exchange"]),))
        pc.store.db.execute("INSERT OR REPLACE INTO journal_local VALUES('home_certificate',?)",
                            (home.identity.cert_path.read_text(),))
        pc_runtime.trust = SimpleNamespace(_owner_credential=lambda proofs: owner)

        class LocalRequest:
            def __init__(self, endpoint, certificate, timeout):
                assert endpoint == "https://127.0.0.1:47513/authority/exchange"
                assert certificate == home.identity.cert_path.read_text()

            async def __call__(self, wire):
                return source.exchange(wire)

        monkeypatch.setattr(move_module, "PinnedLocalClient", LocalRequest)
        target = JournalMoveRuntime(pc_runtime)
        result = asyncio.run(target.move_home(password="owner password", answer="owner answer"))
        assert "old home retired" in result
        assert home.store.authority.state()["phase"] == "retired"
        assert pc.store.authority.state()["phase"] == "active"
        assert pc.home is not None and pc.store.config["role"] == "home"
        assert home.store.fingerprint() == pc.store.fingerprint()
        assert pc.store.cursor() == home.store.cursor()
        assert pc.store.db.scalar("SELECT wire FROM journal_inbox") == large_command
    finally:
        for control in controls:
            control.close()


def test_home_recovery_reuses_saved_transition_after_registry_reply_loss(devices, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from lightning.runtime.journal_trust import JournalTrustRuntime
    from lightning.runtime.session import read_slot, write_slot
    from lightning.sync.journal.cloud import CloudUnavailable
    from lightning.sync.journal.owner import OwnerCredential

    import lightning.sync.journal.owner as owner_module
    monkeypatch.setattr(owner_module, "RECOVERY_MEMORY_KIB", 32768)
    monkeypatch.setattr(owner_module, "RECOVERY_ITERATIONS", 2)
    home, pc = devices
    profile = pc.store.config["profile"]
    owner, document = OwnerCredential.create(profile, password="password", answer="school", recovery="1234-5678-9012")
    from lightning.sync.journal.codec import seal
    config = home.store.config
    enrollment = seal(dict(type="authority-enrollment", version=1, profile=profile, generation=config["generation"],
                          home=home.identity.device_id, home_key=home.identity.public_key, owner_key=owner.public_key), owner.sign)
    memory = AuthorityMemory.enroll(tmp_path / "recovery-control.db", enrollment)
    memory.bind(pc.store)
    members = {item.identity.device_id: dict(key=item.identity.public_key, incarnation=item.store.config["incarnation"])
               for item in devices}
    Membership(pc).initialize(members, os.urandom(32))
    owner_path = tmp_path / "owner.json"
    write_slot(owner_path, document)

    class RegistryClient:
        def __init__(self):
            self.certificate = None
            self.lose_reply = True
            self.lose_read = False
            self.wires = []

        async def call(self, route, data=None):
            if route == "/authority/transition":
                if self.certificate is None:
                    self.certificate = data
                elif self.certificate != data:
                    raise AssertionError("retry published a competing transition")
                self.wires.append(data)
                if self.lose_reply:
                    self.lose_reply = False
                    self.lose_read = True
                    raise CloudUnavailable("registry accepted transition but its read reply was lost")
                return dict(updated=True)
            if route == "/authority":
                if self.certificate is None:
                    raise AssertionError("registry has no accepted transition")
                if self.lose_read:
                    self.lose_read = False
                    raise CloudUnavailable("registry read was lost")
                return dict(generation=self.certificate["body"]["generation"],
                            version=self.certificate["body"]["version"], certificate=self.certificate)
            raise AssertionError(route)

    client = RegistryClient()
    internet = SimpleNamespace(configured=True, peer=SimpleNamespace(client=client))
    trust = JournalTrustRuntime(pc, None, SimpleNamespace(data_dir=tmp_path), document,
                                owner_path=owner_path, internet=internet)
    intent_path = tmp_path / f".journal-home-recovery-{profile}.json"

    async def recover_twice():
        with pytest.raises(CloudUnavailable):
            await trust.recover_home(password="password", answer="school")
        saved = read_slot(intent_path)["wire"]
        assert memory.state()["generation"] == config["generation"]
        await trust.recover_home(password="password", answer="school")
        assert len(client.wires) == 2 and client.wires[0] == client.wires[1]
        assert not intent_path.exists()
        assert pc.home is not None and memory.state()["phase"] == "active"
        assert memory.state()["generation"] != config["generation"]
        assert read_slot(owner_path) == document
        assert unpack(saved.encode())["body"]["generation"] == client.wires[0]["body"]["generation"]

    try:
        asyncio.run(recover_twice())
    finally:
        memory.close()


def test_unconfigured_cloud_recovery_fails_with_clear_unavailable_error(devices, tmp_path):
    from types import SimpleNamespace
    from lightning.runtime.journal_profile import CloudPlaceholder
    from lightning.runtime.journal_trust import JournalTrustRuntime
    from lightning.sync.journal.cloud import CloudUnavailable

    home, pc = devices
    owner, controls = memories(devices, tmp_path)
    try:
        trust = JournalTrustRuntime(pc, None, SimpleNamespace(data_dir=tmp_path), {}, internet=CloudPlaceholder())
        with pytest.raises(CloudUnavailable, match="Reconnect to the authority registry"):
            asyncio.run(trust.recover_home(password="ignored", answer="ignored"))
    finally:
        for control in controls:
            control.close()


def test_recovery_requires_live_registry_publication_and_preserves_old_branch(devices, tmp_path):
    home, pc = devices
    owner, controls = memories(devices, tmp_path)
    wire = change(home, pc, owner, mode="recover")
    class Unavailable:
        async def publish(self, request):
            raise OSError("offline")
    class Registry:
        async def publish(self, request):
            assert request == wire
    try:
        with pytest.raises(OSError):
            asyncio.run(controls[1].recover(pc.store, wire, Unavailable()))
        assert controls[1].state()["generation"] == home.store.config["generation"]
        asyncio.run(controls[1].recover(pc.store, wire, Registry()))
        assert controls[1].can_confirm(pc.store)
        # An offline old home can still make a branch until it learns retirement.
        home.save(groups(home, "-12"))
        original = bytes(home.store.db.scalar("SELECT wire FROM journal_outbox WHERE seq=1"))
        controls[0].observe(wire, local_device=home.identity.device_id)
        with pytest.raises(JournalError):
            home.home.process()
        pc.home = JournalHome(pc.store, pc.identity.sign)
        # Production must reapprove surviving origins in new registry membership.
        pc.home.approve_origin(home.identity.device_id, home.store.config["incarnation"], home.identity.public_key)
        pc.home.receive(original)
        pc.home.process()
        assert pc.store.cursor()["revision"] == 1
        assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 988
    finally:
        for control in controls:
            control.close()


def test_registry_checks_the_winning_certificate_instead_of_trusting_a_reply(devices, tmp_path):
    home, pc = devices
    owner, controls = memories(devices, tmp_path)
    wire = change(home, pc, owner, mode="recover")
    class ForgedReply:
        async def call(self, route, data=None):
            return dict(activated=True) if route.endswith("transition") else dict(generation=str(uuid4()),version=2)
    try:
        with pytest.raises(JournalError, match="another successor"):
            asyncio.run(AuthorityRegistry(ForgedReply()).publish(wire))
        assert not controls[1].can_confirm(pc.store)
    finally:
        for control in controls:
            control.close()


def test_revoked_device_cannot_derive_rotated_transport_secret_from_old_key_or_data_key(devices, tmp_path):
    home, pc = devices
    members = {device.identity.device_id: dict(key=device.identity.public_key,incarnation=device.store.config["incarnation"]) for device in devices}
    secret = os.urandom(32)
    hm, pm = Membership(home), Membership(pc)
    hm.initialize(members, secret)
    pm.initialize(members, secret)
    newcomer = load_or_create(tmp_path / "new-device", "New device")
    expanded = members | {newcomer.device_id: dict(key=newcomer.public_key,incarnation=str(uuid4()))}
    wire = hm.rotate(expanded)
    pm.accept(wire)
    assert home.c.db.scalar("SELECT value FROM journal_local WHERE name='transport'") == pc.c.db.scalar("SELECT value FROM journal_local WHERE name='transport'")
    assert bytes.fromhex(pc.c.db.scalar("SELECT value FROM journal_local WHERE name='transport'")) != secret
    revoked = hm.rotate({home.identity.device_id:members[home.identity.device_id]})
    assert pc.identity.device_id not in unpack(revoked)["body"]["wrapped"]
    with pytest.raises(JournalError, match="no longer"):
        pm.accept(revoked)
    with pytest.raises(JournalError, match="retired"):
        hm.rotate(members)
    assert bytes.fromhex(home.c.db.scalar("SELECT value FROM journal_local WHERE name='transport'")) != home.c.db.copy_key()


def test_pairing_requires_code_password_both_keys_and_explicit_matching_digits(devices):
    from lightning.security.keys import create_key_file
    from lightning.sync.journal.pairing import PairingDesk, prove_pairing, request_pairing
    home, pc = devices
    hm, pm = Membership(home), Membership(pc)
    home_only = {home.identity.device_id:dict(key=home.identity.public_key,incarnation=home.store.config["incarnation"])}
    hm.initialize(home_only, os.urandom(32))
    password = "Dummy pairing password"
    key_file = create_key_file(home.c.db.copy_key(), password, "1234-5678-9012", "First school?", "Cairo")
    desk = PairingDesk(home, hm)
    offer, code = desk.begin(key_file, password)
    incarnation, key = pc.store.config["incarnation"], home.identity.public_key
    bad, _ = request_pairing(offer, "000000" if code != "000000" else "000001", pc.identity, incarnation, home_key=key)
    with pytest.raises(JournalError, match="wrong"):
        desk.accept(bad)
    request, digits = request_pairing(offer, code, pc.identity, incarnation, home_key=key)
    assert desk.accept(request) == digits
    assert pc.identity.device_id not in hm.state()["members"]
    # The home's confirmation alone admits nobody; the password proof is also required.
    with pytest.raises(JournalError, match="same six"):
        desk.confirm("000000" if digits != "000000" else "000001")
    assert desk.confirm(digits) is None and pc.identity.device_id not in hm.state()["members"]
    wrong = prove_pairing(offer, request, "wrong password", pc.identity, home_key=key)
    with pytest.raises(JournalError, match="password"):
        desk.prove(wrong)
    assert pc.identity.device_id not in hm.state()["members"]
    update = desk.prove(prove_pairing(offer, request, password, pc.identity, home_key=key))
    pm.accept(update, initial=True)
    assert hm.state() == pm.state()
    assert home.c.db.scalar("SELECT value FROM journal_local WHERE name='transport'") == pc.c.db.scalar("SELECT value FROM journal_local WHERE name='transport'")
    with pytest.raises(JournalError):
        desk.accept(request)


@pytest.mark.parametrize("phase",["freeze","prepare","retire","authority_observed","authority_profile_committed","authority_activated"])
def test_move_resumes_from_reopened_control_and_profile_without_two_active_homes(devices,tmp_path,phase):
    from lightning.bootstrap import build
    from lightning.sync.journal.finance import attach
    from lightning.sync.journal.device import JournalDevice
    home,pc = devices
    owner,controls = memories(devices,tmp_path)
    reopened = None
    try:
        home.save(groups(home))
        pc.sync_with(home.home)
        original = pc.save(groups(pc,"-8"))
        cutoff = controls[0].freeze(home.store)
        if phase == "freeze":
            controls[0].close()
            controls[0] = AuthorityMemory(tmp_path/'control-0.db',profile=home.store.config["profile"])
            controls[0].bind(home.store)
            assert controls[0].freeze(home.store) == cutoff
        transfer_home_state(home.store,pc.store)
        wire = change(home,pc,owner)
        prepared = controls[1].prepare(pc.store,wire,pc.identity.sign)
        if phase == "prepare":
            controls[1].close()
            controls[1] = AuthorityMemory(tmp_path/'control-1.db',profile=pc.store.config["profile"])
            controls[1].bind(pc.store)
            assert controls[1].prepare(pc.store,wire,pc.identity.sign) == prepared
        retired = controls[0].retire(home.store,wire,prepared,home.identity.sign)
        if phase == "retire":
            controls[0].close()
            controls[0] = AuthorityMemory(tmp_path/'control-0.db',profile=home.store.config["profile"])
            controls[0].bind(home.store)
            assert controls[0].retire(home.store,wire,prepared,home.identity.sign) == retired
        class Interrupted(BaseException):
            pass
        def stop(at):
            if at == phase:
                raise Interrupted
        if phase.startswith("authority_"):
            with pytest.raises(Interrupted):
                controls[1].activate_move(pc.store,wire,prepared,retired,old_home_key=home.identity.public_key,fault=stop)
        key,path,identity = pc.c.db.copy_key(),pc.c.db.path,pc.identity
        controls[1].close()
        pc.store.close()
        reopened = build(path,key=key,experimental_journal=True)
        pc = JournalDevice(attach(reopened),identity)
        controls[1] = AuthorityMemory(tmp_path/'control-1.db',profile=pc.store.config["profile"])
        controls[1].bind(pc.store)
        assert not controls[0].can_confirm(home.store)
        controls[1].activate_move(pc.store,wire,prepared,retired,old_home_key=home.identity.public_key)
        assert controls[1].can_confirm(pc.store)
        pc.home = JournalHome(pc.store,pc.identity.sign)
        pc.flush_home()
        assert not pc.store.pending() and pc.store.cursor()["revision"] == 2
        assert pc.c.db.scalar("SELECT wire FROM journal_outbox WHERE seq=1") == original
        with pytest.raises(JournalError):
            home.home.process()
    finally:
        for control in controls:
            control.close()
        if reopened:
            reopened.db.close()


def test_move_rejects_retirement_signed_by_successor_instead_of_pinned_old_home(devices,tmp_path):
    home,pc = devices
    owner,controls = memories(devices,tmp_path)
    try:
        controls[0].freeze(home.store)
        transfer_home_state(home.store,pc.store)
        wire = change(home,pc,owner)
        prepared = controls[1].prepare(pc.store,wire,pc.identity.sign)
        forged = seal(dict(type="authority-retired",transition=digest(unpack(wire)["body"]),prepared=digest(unpack(prepared)["body"])),pc.identity.sign)
        with pytest.raises(JournalError,match="pinned old home"):
            controls[1].activate_move(pc.store,wire,prepared,forged,old_home_key=pc.identity.public_key)
        assert controls[0].state()["phase"] == "frozen"
        assert not controls[1].can_confirm(pc.store)
    finally:
        for control in controls:
            control.close()


@pytest.mark.parametrize("tamper",[None,"skip","signature","owner"])
def test_offline_peer_verifies_every_authority_link_and_pins_valid_prefix(devices,tmp_path,tamper):
    from lightning.sync.journal.cloud import raw_signature
    home,pc = devices
    owner,controls = memories(devices,tmp_path)
    replacement = OwnerCredential(ec.generate_private_key(ec.SECP256R1()))
    first = unpack(change(home,pc,owner,mode="recover"))["body"]
    first["owner_key"] = replacement.public_key
    second = first | dict(previous=first["generation"],generation=str(uuid4()),version=3,nonce=os.urandom(32).hex())
    certificates = [dict(body=first,signature=raw_signature(owner,first)),dict(body=second,signature=raw_signature(replacement,second))]
    if tamper == "skip":
        certificates = certificates[1:]
    elif tamper == "signature":
        certificates[1]["signature"] = "00"*64
    elif tamper == "owner":
        certificates[1]["signature"] = raw_signature(owner,second)
    class Registry:
        async def call(self,route,data):
            assert route == "/authority/chain" and data == dict(after=1)
            return dict(certificates=certificates,latest=3)
    try:
        request = AuthorityRegistry(Registry()).catch_up(controls[0],local_device=home.identity.device_id)
        if tamper:
            with pytest.raises(JournalError):
                asyncio.run(request)
            assert controls[0].state()["version"] == (1 if tamper == "skip" else 2)
        else:
            assert asyncio.run(request)["generation"] == second["generation"]
            controls[0].close()
            controls[0] = AuthorityMemory(tmp_path/'control-0.db',profile=home.store.config["profile"])
            controls[0].bind(home.store)
            assert controls[0].state()["version"] == 3
            assert not controls[0].can_confirm(home.store)
        assert home.store.config["generation"] == first["previous"]
    finally:
        for control in controls:
            control.close()


@pytest.mark.parametrize("interrupt",[False,True])
def test_successor_rotates_transport_in_same_profile_commit_and_retry_keeps_the_new_key(devices,tmp_path,interrupt):
    home,pc = devices
    secret = os.urandom(32)
    members = {d.identity.device_id:dict(key=d.identity.public_key,incarnation=d.store.config["incarnation"]) for d in devices}
    for device in devices:
        Membership(device).initialize(members,secret)
    owner,controls = memories(devices,tmp_path)
    try:
        controls[0].freeze(home.store)
        transfer_home_state(home.store,pc.store)
        wire = change(home,pc,owner)
        prepared = controls[1].prepare(pc.store,wire,pc.identity.sign)
        retired = controls[0].retire(home.store,wire,prepared,home.identity.sign)
        with pytest.raises(JournalError,match="signing key is required"):
            controls[1].activate_move(pc.store,wire,prepared,retired,old_home_key=home.identity.public_key)
        assert pc.store.config["generation"] == home.store.config["generation"]
        class Interrupted(BaseException):
            pass
        def fault(phase):
            if phase == "authority_profile_committed":
                raise Interrupted
        if interrupt:
            with pytest.raises(Interrupted):
                controls[1].activate_move(pc.store,wire,prepared,retired,old_home_key=home.identity.public_key,home_signer=pc.identity.sign,fault=fault)
            stored = pc.c.db.scalar("SELECT value FROM journal_local WHERE name='transport'")
        controls[1].activate_move(pc.store,wire,prepared,retired,old_home_key=home.identity.public_key,home_signer=pc.identity.sign)
        current = pc.c.db.scalar("SELECT value FROM journal_local WHERE name='transport'")
        assert current != secret.hex()
        if interrupt:
            assert current == stored
        assert Membership(pc).state()["version"] == 1
        update = pc.c.db.scalar("SELECT value FROM journal_local WHERE name='membership_wire:1'").encode()
        body = unpack(update)["body"]
        assert body["generation"] == pc.store.config["generation"] and body["previous"] == 0
        assert controls[1].can_confirm(pc.store)
        # A newly enrolled peer can consume this generation's initial wrap.
        with home.c.db.transaction():
            home.c.db.execute("DELETE FROM journal_local WHERE name='membership'")
            home.store.config = dict(home.store.config,generation=pc.store.config["generation"],home_key=pc.store.config["home_key"])
            Membership(home).accept(update,initial=True)
        assert home.c.db.scalar("SELECT value FROM journal_local WHERE name='transport'") == current
    finally:
        for control in controls:
            control.close()


def test_recovered_home_answers_a_resent_prefix_proposal_with_its_original_decision(devices, tmp_path):
    home, pc = devices
    owner, controls = memories(devices, tmp_path)
    original = home.save(groups(home, "-40"))
    pc.sync_with(home.home)
    wire = change(home, pc, owner, mode="recover")
    class Registry:
        async def publish(self, request):
            pass
    try:
        asyncio.run(controls[1].recover(pc.store, wire, Registry()))
        pc.home = JournalHome(pc.store, pc.identity.sign)
        pc.home.approve_origin(home.identity.device_id, home.store.config["incarnation"], home.identity.public_key)
        identifier = unpack(original)["body"]["origin"]
        assert pc.home.receive(original) == "accepted"
        assert pc.home.process() == []
        assert pc.home.status(f'{identifier["device"]}/{identifier["incarnation"]}/{identifier["seq"]}')["status"] == "accepted"
        later = home.store.save(kind="transaction.add", record=str(uuid4()), groups=groups(home, "-5"),
                                bases=dict.fromkeys(("money", "category", "details")), signer=home.identity.sign)
        pc.home.receive(later)
        assert len(pc.home.process()) == 1
        assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 955
    finally:
        for control in controls:
            control.close()
