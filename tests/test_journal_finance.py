"""Experimental real cash services: pending overlays never enter reports."""
import os
import asyncio
import re
from datetime import datetime
from uuid import uuid4

import pytest

from lightning.bootstrap import build, ReadOnlyCopyError
from lightning.sync.identity import load_or_create
from lightning.sync.journal.codec import JournalError, unpack, origin_id
from lightning.sync.journal.device import JournalDevice
from lightning.sync.journal.finance import initialize, attach
from lightning.sync.journal.home import JournalHome


@pytest.fixture
def devices(tmp_path):
    from lightning.sync.journal.snapshots import checkpoint_replica
    profile, generation = str(uuid4()), str(uuid4())
    identities = [load_or_create(tmp_path / f"id-{i}", f"Device {i}") for i in range(2)]
    c = build(tmp_path / "ledger-0.db", key=os.urandom(32))
    c.account_flows.open_account("Bank", "BANK", "2026-01-01", "1000")
    c.account_flows.open_account("Wallet", "CASH", "2026-01-01", "100")
    stores = [initialize(c, profile=profile, generation=generation, device=identities[0].device_id,
        incarnation=str(uuid4()), home_key=identities[0].public_key, origin_key=identities[0].public_key,
        role="home", dummy_profile=True)]
    containers = [c]
    # The replica starts from the home's checkpoint, then gets different local
    # account ids, so replay must go through UUIDs, never physical row ids.
    checkpoint_replica(stores[0], tmp_path / "ledger-1.db", identities[0].sign, device=identities[1].device_id,
                       incarnation=str(uuid4()), origin_key=identities[1].public_key)
    replica = build(tmp_path / "ledger-1.db", key=c.db.copy_key(), experimental_journal=True)
    replica.db.conn.execute("PRAGMA foreign_keys=OFF")
    with replica.db.transaction():
        replica.db.execute("UPDATE accounts SET id=id+100")
        replica.db.execute("UPDATE ledger_entries SET account_id=account_id+100")
        replica.db.execute("UPDATE journal_ids SET local_id=local_id+100 WHERE entity='accounts'")
    replica.db.conn.execute("PRAGMA foreign_keys=ON")
    containers.append(replica)
    stores.append(attach(replica))
    home = JournalHome(stores[0], identities[0].sign)
    for store, identity in zip(stores, identities):
        home.approve_origin(identity.device_id, store.config["incarnation"], identity.public_key)
    result = [JournalDevice(stores[0], identities[0], home), JournalDevice(stores[1], identities[1])]
    yield result
    for c in containers:
        c.db.close()


def groups(device, amount="-10.00", *, transfer=False, splits=None):
    a = device.adapter
    accounts = device.c.accounts.list()
    bank = next(item for item in accounts if item.name == "Bank")
    wallet = next(item for item in accounts if item.name == "Wallet")
    category = device.c.categories.get_by_code("EXP.PERSONAL.FOOD")
    return dict(money=dict(account=a.uid("accounts", bank.id), other_account=a.uid("accounts", wallet.id) if transfer else None,
                           date="2026-09-01", amount=amount),
                category=dict(category=None if transfer else a.uid("categories", category.id), splits=splits or []),
                details=dict(counterparty="", notes="", description=""))


def test_pending_money_does_not_enter_reports_and_exact_replay_uses_uuid_references(devices, monkeypatch):
    hd, pc = devices
    assert hd.store.fingerprint() == pc.store.fingerprint()
    before = pc.balances()
    pc.save(groups(pc))
    assert pc.balances() == before
    assert pc.view()[0]["state"] == "Pending"
    monkeypatch.setattr(pc.c.transactions, "record_in_account", lambda **kwargs: pytest.fail("Replay reran a service"))
    pc.sync_with(hd.home)
    assert pc.view()[0]["state"] == "Confirmed"
    assert hd.store.fingerprint() == pc.store.fingerprint()
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 990


def test_add_edit_delete_before_upload_preserves_queue_and_money(devices):
    hd, pc = devices
    wire = pc.save(groups(pc))
    record = unpack(wire)["body"]["record"]
    pc.save({"details": dict(counterparty="", notes="offline edit", description="")}, record=record)
    pc.sync_with(hd.home)
    assert pc.view()[0]["groups"]["details"]["notes"] == "offline edit"
    pc.save({}, record=record, delete=True)
    assert pc.view()[0]["state"] == "Awaiting deletion"
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 990
    pc.sync_with(hd.home)
    assert pc.view() == []
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 1000


def test_transfer_and_split_are_atomic_and_validation_refusal_advances_sequence(devices):
    hd, pc = devices
    pc.save(groups(pc, "-25.00", transfer=True))
    pc.sync_with(hd.home)
    assert {item["name"]: item["balance"] for item in pc.balances()} == {"Bank": 975, "Wallet": 125}
    food = pc.c.categories.get_by_code("EXP.PERSONAL.FOOD")
    health = pc.c.categories.get_by_code("EXP.PERSONAL.HEALTH")
    splits = [dict(category=pc.adapter.uid("categories", food.id), amount="6.00"),
              dict(category=pc.adapter.uid("categories", health.id), amount="4.00")]
    pc.save(groups(pc, splits=splits))
    pc.sync_with(hd.home)
    assert len(pc.c.db.all("SELECT * FROM ledger_entries WHERE transaction_id=(SELECT MAX(id) FROM transactions)")) == 2
    bad = pc.save(groups(pc, splits=[splits[0]]))
    pc.sync_with(hd.home)
    # A manual same-day repeat is not a duplicate suspect; the bad split is refused outright.
    assert hd.home.status(origin_id(unpack(bad)["body"]["origin"])) == dict(status="rejected", reason="financial-validation")
    assert hd.store.fingerprint() == pc.store.fingerprint()


def test_uncovered_writes_and_legacy_reopen_are_blocked(devices):
    hd, pc = devices
    for device in devices:
        with pytest.raises(device.c.db.driver.DatabaseError):
            device.c.settings.set("uncovered", "write")
    with pytest.raises(ReadOnlyCopyError, match="journal runtime"):
        build(pc.c.db.path, key=pc.c.db.copy_key())
    hd.save(groups(hd))
    with pytest.raises(hd.c.db.driver.DatabaseError):
        # The service's previously prepared INSERT cannot escape the authorizer.
        hd.c.transactions.record_in_account(account_id=hd.adapter.local("accounts", groups(hd)["money"]["account"]),
            date="2026-09-01", amount="-1", category_id=hd.c.categories.get_by_code("EXP.PERSONAL.FOOD").id)


def test_proven_import_retry_aliases_once_and_dependent_edit_uses_canonical_payment(devices):
    hd, pc = devices
    values = groups(pc) | {"source": dict(namespace="bank:sample", id="payment-1")}
    hd.save(values)
    retry = pc.save(values)
    retry_record = unpack(retry)["body"]["record"]
    pc.sync_with(hd.home)
    assert hd.home.status(origin_id(unpack(retry)["body"]["origin"]))["status"] == "accepted-as-existing"
    assert len(pc.view()) == 1
    pc.save({"details": dict(counterparty="", notes="Linked import", description="")}, record=retry_record)
    pc.sync_with(hd.home)
    assert len(pc.view()) == 1
    assert pc.view()[0]["groups"]["details"]["notes"] == "Linked import"
    assert pc.store.fingerprint() == hd.store.fingerprint()


def test_fuzzy_duplicate_waits_before_second_posting_and_home_can_link(devices):
    hd, pc = devices
    hd.save(groups(hd))
    duplicate = pc.save(groups(pc) | {"source": dict(namespace="sms:sample", id="sms-1")})
    pc.sync_with(hd.home)
    assert any(item["state"] == "Needs review" for item in pc.view())
    proposal_id = origin_id(unpack(duplicate)["body"]["origin"])
    state = hd.home.review_state(proposal_id)
    hd.home.review(command_id=str(uuid4()), proposal_id=proposal_id, token=state["token"],
                   choice="link", existing=state["matches"][0]["record"])
    pc.sync_with(hd.home)
    assert len(pc.view()) == 1
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 990


def test_csv_is_local_review_then_idempotent_per_payment_capture(devices):
    from lightning.sync.journal.capture import JournalCapture
    hd, pc = devices
    values = groups(pc)
    capture = JournalCapture(pc)
    data = b'Date,Amount,Reference\n2026-09-01,-10.00,one\n2026-09-02,-20.00,two\n'
    kwargs = dict(account=values["money"]["account"], category=values["category"]["category"],
                  mapping=dict(date="Date", amount="Amount", reference="Reference"))
    batch, candidates = capture.csv(data, **kwargs)
    assert len(capture.waiting()) == 2 and not pc.store.pending()
    _, repeated = capture.csv(data, **kwargs)
    assert repeated == candidates
    first = capture.save(candidates[0])
    assert capture.save(candidates[0]) == first
    capture.save(candidates[1])
    assert capture.progress(batch) == dict(total=2, saved=2, decided=0)
    pc.sync_with(hd.home)
    assert capture.progress(batch) == dict(total=2, saved=2, decided=2)
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 970
    undo = capture.undo_batch(batch)
    assert len(undo) == 2 and capture.undo_batch(batch) == undo
    pc.sync_with(hd.home)
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 1000


def test_sms_capture_on_non_home_does_not_post_money(devices):
    from lightning.sync.journal.capture import JournalCapture
    _, pc = devices
    values = groups(pc)
    capture = JournalCapture(pc)
    text = "تم خصم 10.00 EGP من بطاقة الخصم المباشر رقم 1234 عند متجر يوم 01/09/26 الساعه 11:13 المتاح 990.00EGP"
    candidate = capture.sms(text, sender="NBE", received=datetime(2026, 9, 1, 11, 14),
                           account=values["money"]["account"], category=values["category"]["category"], source_id="os:1")
    assert candidate is not None
    assert not pc.store.pending() and len(capture.waiting()) == 1
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 1000


def test_verified_snapshot_repairs_replica_without_erasing_pending_or_decisions(devices, tmp_path):
    from lightning.sync.journal.snapshots import export, repair
    hd, pc = devices
    accepted = pc.save(groups(pc))
    pc.sync_with(hd.home)
    pending = pc.save(groups(pc, "-20.00"))
    target = tmp_path / "checkpoint.db"
    manifest = export(hd.store, target, hd.identity.sign)
    repair(pc.store, target, manifest, source_key=hd.c.db.copy_key())
    assert pc.store.pending() == [pending]
    assert len(pc.store.decisions()) == 1
    assert pc.store.fingerprint() == hd.store.fingerprint()
    pc.sync_with(hd.home)
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 970
    assert len(pc.store.decisions()) == 2


@pytest.mark.parametrize("phase", ["snapshot_domain", "snapshot_cursor"])
def test_snapshot_failure_rolls_back_domain_and_cursor_together(devices, tmp_path, phase):
    from lightning.sync.journal.snapshots import export, repair
    hd, pc = devices
    hd.save(groups(hd))
    target = tmp_path / "checkpoint.db"
    manifest = export(hd.store, target, hd.identity.sign)
    pending = pc.save(groups(pc, "-20.00"))
    before = pc.store.fingerprint(), pc.store.cursor()
    def fault(point):
        if point == phase:
            raise RuntimeError("Injected snapshot interruption")
    with pytest.raises(RuntimeError):
        repair(pc.store, target, manifest, source_key=hd.c.db.copy_key(), fault=fault)
    assert (pc.store.fingerprint(), pc.store.cursor()) == before
    assert pc.store.pending() == [pending]


def test_encrypted_local_delta_exchange_and_revoked_sender(devices):
    from lightning.sync.journal.local import LocalChannel
    hd, pc = devices
    secret = os.urandom(32)
    channels = [LocalChannel(device, transport_key=secret, peers={other.identity.device_id: other.identity.public_key})
                for device, other in ((hd, pc), (pc, hd))]
    pending = pc.save(groups(pc))
    wire = channels[1].protect(dict(operation="changes", value=pc.store.cursor()), hd.identity.device_id)
    assert b'"operation"' not in wire and b'"amount"' not in wire
    async def request(wire):
        return channels[0].handle(wire)
    asyncio.run(channels[1].synchronize(request, home_id=hd.identity.device_id))
    assert not pc.store.pending() and pc.store.fingerprint() == hd.store.fingerprint()
    hd.home.revoke_origin(pc.identity.device_id, pc.store.config["incarnation"])
    with pytest.raises(JournalError, match="trusted"):
        channels[0].handle(wire)


def test_pc_phone_forms_keep_pending_out_of_balances_and_guard_csrf(devices):
    import httpx
    from lightning.ui.journal import create_journal_app
    hd, pc = devices
    token = "test-session-" + "s" * 40
    app = create_journal_app(pc, session_token=token)
    choices = pc.choices()
    category = next(label for label in choices["categories"] if label.startswith("Food"))
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            assert (await client.get("/")).status_code == 401
            client.cookies.set("journal_session", token)
            desktop = await client.get("/")
            assert "Confirmed balances" in desktop.text and "phone-tabbar" not in desktop.text
            phone = await client.get("/", headers={"user-agent": "Android Mobile"})
            assert "phone-tabbar" in phone.text and "phone.css" in phone.text
            draft = re.search(r'name="draft" value="([^"]+)"', desktop.text).group(1)
            data = dict(__session=token, draft=draft, account="Bank", category=category, date="2026-09-01", amount="-10.00")
            assert (await client.post("/save", data=data)).status_code == 403
            result = await client.post("/save", data=data, headers={"origin": "http://testserver"})
            assert result.status_code == 200 and "Saved on this device · Pending" in result.text
            assert "1,000" in result.text and "Needs review" not in result.text
            assert (await client.post("/review", data=data, headers={"origin": "http://testserver"})).status_code == 403
    asyncio.run(run())
    assert len(pc.store.pending()) == 1


def test_queued_add_edit_delete_before_any_upload_has_no_missing_field_bases(devices):
    hd, pc = devices
    add = pc.save(groups(pc))
    record = unpack(add)["body"]["record"]
    pc.save({"details": dict(counterparty="", notes="Edited offline", description="")}, record=record)
    pc.save({}, record=record, delete=True)
    pc.sync_with(hd.home)
    assert not pc.store.pending() and not pc.view()
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 1000


def test_source_identity_cannot_be_reused_for_another_amount_even_after_explicit_review(devices):
    hd, pc = devices
    source = dict(source=dict(namespace="bank:sample", id="bank-ref"))
    hd.save(groups(hd) | source)
    altered = pc.save(groups(pc, "-20.00") | source)
    pc.sync_with(hd.home)
    identifier = origin_id(unpack(altered)["body"]["origin"])
    state = hd.home.review_state(identifier)
    with pytest.raises(JournalError):
        hd.home.review(command_id=str(uuid4()), proposal_id=identifier, token=state["token"], choice="link", existing=state["matches"][0]["record"])
    hd.home.review(command_id=str(uuid4()), proposal_id=identifier, token=state["token"], choice="apply")
    pc.sync_with(hd.home)
    assert hd.home.status(identifier)["status"] == "rejected"
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 990


def test_reviewed_sms_csv_link_remembers_both_sources_and_decimal_spelling_is_equivalent(devices):
    hd, pc = devices
    hd.save(groups(hd) | {"source": dict(namespace="sms:bank", id="sms-1")})
    imported = groups(pc, "-10.0") | {"source": dict(namespace="bank:csv", id="csv-1")}
    wire = pc.save(imported)
    pc.sync_with(hd.home)
    identifier = origin_id(unpack(wire)["body"]["origin"])
    state = hd.home.review_state(identifier)
    hd.home.review(command_id=str(uuid4()), proposal_id=identifier, token=state["token"], choice="link", existing=state["matches"][0]["record"])
    pc.sync_with(hd.home)
    repeated = pc.save(imported)
    pc.sync_with(hd.home)
    assert hd.home.status(origin_id(unpack(repeated)["body"]["origin"]))["status"] == "accepted-as-existing"
    assert len(pc.view()) == 1


def test_old_encrypted_reply_cannot_acknowledge_a_new_request(devices, monkeypatch):
    from lightning.sync.journal import local
    from lightning.sync.journal.local import LocalChannel
    hd, pc = devices
    monkeypatch.setattr(local, "REPLY_BUDGET", 1)  # One commit per reply forces a second request.
    hd.save(groups(hd, "-3"))
    key = os.urandom(32)
    client = LocalChannel(pc, transport_key=key, peers={hd.identity.device_id: hd.identity.public_key})
    server = LocalChannel(hd, transport_key=key, peers={pc.identity.device_id: pc.identity.public_key})
    saved = pc.save(groups(pc))
    first = None
    async def replay_response(wire):
        nonlocal first
        if first is None:
            first = server.handle(wire)
        return first
    with pytest.raises(JournalError, match="earlier request"):
        asyncio.run(client.synchronize(replay_response, home_id=hd.identity.device_id))
    assert pc.store.pending() == [saved]


def test_persistent_dummy_lab_reopens_the_original_queued_identity(tmp_path):
    from lightning.runtime.journal_lab import open_lab
    devices, secret = open_lab(tmp_path, "dummy-test-password")
    hd, pc = devices
    from lightning.core.dates import today
    values = groups(pc)
    values["money"]["date"] = today().isoformat()
    wire = pc.save(values)
    config = dict(pc.store.config)
    for device in devices:
        device.store.close()
    devices, restored_secret = open_lab(tmp_path, "dummy-test-password")
    try:
        hd, pc = devices
        assert pc.store.config == config
        assert pc.store.pending() == [wire] and secret == restored_secret
        pc.sync_with(hd.home)
        assert not pc.store.pending() and pc.store.fingerprint() == hd.store.fingerprint()
        assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 990
    finally:
        for device in devices:
            device.store.close()


def test_real_pinned_tls_local_exchange(devices):
    import socket
    from lightning.runtime.journal_lab import LabServer
    from lightning.ui.journal import create_journal_app
    from lightning.sync.journal.local import LocalChannel, PinnedLocalClient
    import uvicorn
    hd, pc = devices
    transport_key = os.urandom(32)
    server_channel = LocalChannel(hd, transport_key=transport_key, peers={pc.identity.device_id: pc.identity.public_key})
    client_channel = LocalChannel(pc, transport_key=transport_key, peers={hd.identity.device_id: hd.identity.public_key})
    app = create_journal_app(hd, session_token="s" * 40, channel=server_channel)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    server = LabServer(hd.identity.configure_uvicorn_tls(uvicorn.Config(
        app, host="127.0.0.1", port=port, access_log=False, log_level="error")))
    pc.save(groups(pc))
    async def run():
        task = asyncio.create_task(server.serve())
        try:
            for _ in range(100):
                if server.started:
                    break
                await asyncio.sleep(0.05)
            assert server.started
            request = PinnedLocalClient(f"https://127.0.0.1:{port}/exchange", hd.identity.cert_path.read_text())
            await client_channel.synchronize(request, home_id=hd.identity.device_id)
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, timeout=10)
    asyncio.run(run())
    assert not pc.store.pending() and hd.store.fingerprint() == pc.store.fingerprint()


def test_transport_errors_never_render_the_home_session_or_financial_ui(devices):
    import httpx
    from lightning.ui.journal import create_journal_app
    from lightning.sync.journal.local import LocalChannel, encode
    hd, pc = devices
    transport_key = os.urandom(32)
    client = LocalChannel(pc, transport_key=transport_key, peers={hd.identity.device_id: hd.identity.public_key})
    server = LocalChannel(hd, transport_key=transport_key, peers={pc.identity.device_id: pc.identity.public_key})
    token = "private-home-session-" + "s" * 40
    app = create_journal_app(hd, session_token=token, channel=server)
    invalid = groups(pc)
    invalid["money"]["amount"] = "0"
    proposal = pc.store.save(kind="transaction.add", record=str(uuid4()), groups=invalid,
                            bases=dict.fromkeys(invalid), signer=pc.identity.sign)
    wire = client.protect(dict(operation="proposal", value=encode(proposal)), hd.identity.device_id)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://testserver") as http:
            response = await http.post("/exchange", content=wire)
            assert response.status_code == 403
            assert token not in response.text and "Bank" not in response.text and "<html" not in response.text
    asyncio.run(run())
    assert hd.store.db.scalar("SELECT COUNT(*) FROM journal_inbox") == 0


def test_csv_upload_stages_candidates_without_plaintext_disk_spooling(devices, monkeypatch):
    import httpx
    import starlette.formparsers
    from lightning.ui.journal import create_journal_app
    _, pc = devices
    token = "upload-session-" + "s" * 40
    app = create_journal_app(pc, session_token=token)
    created = []
    original = starlette.formparsers.SpooledTemporaryFile
    def tracked(*args, **kwargs):
        value = original(*args, **kwargs)
        created.append(value)
        return value
    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", tracked)
    category = next(label for label in pc.choices()["categories"] if label.startswith("Food"))
    data = dict(__session=token, account="Bank", category=category, date="Date", amount="Amount")
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver",
            cookies={"journal_session": token}, headers={"origin": "http://testserver"}) as client:
            too_many_rows = b"Date,Amount\n" + b"2026-09-01,-10.00\n" * 70000
            response = await client.post("/capture/csv", data=data, files={"file": ("large.csv", too_many_rows, "text/csv")})
            assert response.status_code == 400
            assert pc.store.db.scalar("SELECT COUNT(*) FROM journal_candidates") == 0
            response = await client.post("/capture/csv", data=data, files={"file": ("small.csv", b"Date,Amount\n2026-09-01,-10.00\n", "text/csv")})
            assert response.status_code == 303
    asyncio.run(run())
    assert created and not any(value._rolled for value in created)
    assert not pc.store.pending() and pc.store.db.scalar("SELECT COUNT(*) FROM journal_candidates") == 1


def test_a_form_keeps_its_original_preconditions_after_sync(devices):
    hd, pc = devices
    add = hd.save(groups(hd))
    record = unpack(add)["body"]["record"]
    pc.sync_with(hd.home)
    draft = pc.draft(record)
    hd.save({"money": groups(hd, "-20.00")["money"]}, record=record)
    pc.sync_with(hd.home)
    wire = pc.submit_draft(draft, groups(pc, "-30.00"))
    pc.sync_with(hd.home)
    assert hd.home.status(origin_id(unpack(wire)["body"]["origin"]))["status"] == "review"
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 980


def test_double_submit_of_one_form_has_one_identity_and_one_effect(devices):
    hd, pc = devices
    draft = pc.draft()
    values = groups(pc)
    wire = pc.submit_draft(draft, values)
    assert pc.submit_draft(draft, values) == wire
    with pytest.raises(JournalError, match="already saved"):
        pc.submit_draft(draft, groups(pc, "-20.00"))
    assert len(pc.store.pending()) == 1
    pc.sync_with(hd.home)
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 990


def test_candidate_can_be_corrected_to_a_transfer_before_any_posting(devices):
    from lightning.sync.journal.capture import JournalCapture
    hd, pc = devices
    capture = JournalCapture(pc)
    original = groups(pc)
    kwargs = dict(namespace="bank:sample", source_id="transfer-1", batch="sample")
    candidate = capture.candidate(original, **kwargs)
    corrected = groups(pc, transfer=True)
    identifier = capture.save(candidate, groups=corrected)
    assert capture.save(candidate, groups=corrected) == identifier
    assert capture.candidate(original, **kwargs) == candidate
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 1000
    pc.sync_with(hd.home)
    assert {item["name"]: item["balance"] for item in pc.balances()} == {"Bank": 990, "Wallet": 110}


def test_child_of_a_duplicate_uses_the_alias_decision_tokens_not_later_values(devices):
    hd, pc = devices
    source = dict(source=dict(namespace="bank:sample", id="original"))
    original = hd.save(groups(hd) | source)
    canonical = unpack(original)["body"]["record"]
    duplicate = pc.save(groups(pc) | source)
    hd.home.receive(duplicate)
    hd.home.process()
    proposed_record = unpack(duplicate)["body"]["record"]
    child = pc.save({"money": groups(pc, "-20.00")["money"]}, record=proposed_record)
    hd.save({"money": groups(hd, "-15.00")["money"]}, record=canonical)
    pc.sync_with(hd.home)
    assert hd.home.status(origin_id(unpack(child)["body"]["origin"]))["status"] == "review"
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 985



def test_undo_reverses_only_its_own_change_and_a_later_change_goes_to_review(devices):
    hd, pc = devices
    record = unpack(pc.save(groups(pc)))["body"]["record"]
    pc.sync_with(hd.home)
    edit = pc.save({"money": groups(pc, "-25.00")["money"]}, record=record)
    pc.sync_with(hd.home)
    health = hd.adapter.uid("categories", hd.c.categories.get_by_code("EXP.PERSONAL.HEALTH").id)
    hd.save({"category": dict(category=health, splits=[])}, record=record)
    pc.sync_with(hd.home)
    pc.undo(origin_id(unpack(edit)["body"]["origin"]))
    pc.sync_with(hd.home)
    current = hd.store.record(record)["groups"]
    assert current["money"]["amount"] == "-10.00" and current["category"]["category"] == health
    # Undoing the addition after another device changed it waits for review instead of deleting.
    hd.save({"money": groups(hd, "-30.00")["money"]}, record=record)
    first = hd.store.db.scalar("SELECT proposal_id FROM journal_commits ORDER BY revision LIMIT 1")
    pc.sync_with(hd.home)
    undo = pc.undo(first)
    pc.sync_with(hd.home)
    assert hd.home.status(origin_id(unpack(undo)["body"]["origin"]))["status"] == "review"
    assert not hd.store.record(record)["deleted"]


def test_manual_same_day_repeats_post_without_review(devices):
    hd, pc = devices
    pc.save(groups(pc, "-50.00"))
    pc.save(groups(pc, "-50.00"))
    pc.sync_with(hd.home)
    assert [item["state"] for item in pc.view()] == ["Confirmed", "Confirmed"]
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 900


def test_unexpected_service_error_holds_only_its_origin(devices, monkeypatch):
    hd, pc = devices
    real = hd.c.transactions.record_in_account
    def flaky(**values):
        if values["amount"] == "-13.00":
            raise RuntimeError("unexpected")
        return real(**values)
    monkeypatch.setattr(hd.c.transactions, "record_in_account", flaky)
    stuck = pc.save(groups(pc, "-13.00"))
    pc.sync_with(hd.home)
    assert hd.home.status(origin_id(unpack(stuck)["body"]["origin"])) == dict(status="review", reason="home-error")
    hd.save(groups(hd, "-7.00"))
    assert next(item for item in hd.balances() if item["name"] == "Bank")["balance"] == 993
    state = hd.home.review_state(origin_id(unpack(stuck)["body"]["origin"]))
    hd.home.review(command_id=str(uuid4()), proposal_id=state["proposal_id"], token=state["token"], choice="reject")
    pc.save(groups(pc, "-2.00"))
    pc.sync_with(hd.home)
    assert hd.store.fingerprint() == pc.store.fingerprint()
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 991


def test_a_held_upload_on_the_home_is_saved_not_an_error(devices, monkeypatch):
    from lightning.sync.journal import home as home_module
    hd, pc = devices
    record = unpack(hd.save(groups(hd)))["body"]["record"]
    draft = hd.draft(record)
    pc.sync_with(hd.home)
    pc.save({"money": groups(pc, "-20.00")["money"]}, record=record)
    pc.sync_with(hd.home)
    hd.submit_draft(draft, groups(hd, "-30.00"))  # Conflicts: its origin now waits for review.
    monkeypatch.setattr(home_module, "MAX_GAP", 2)
    for amount in ("-1.00", "-2.00", "-3.00"):
        hd.save(groups(hd, amount))
    assert len(hd.store.pending()) == 4


def test_confirmation_reads_only_the_touched_transactions(devices):
    hd, pc = devices
    for index in range(40):
        hd.save(groups(hd, f"-{index + 1}.00"))
    statements = []
    hd.store.db.conn.set_trace_callback(statements.append)
    hd.save(groups(hd, "-99.00"))
    hd.store.db.conn.set_trace_callback(None)
    assert len(statements) < 400
    pc.sync_with(hd.home)
    assert hd.store.fingerprint() == pc.store.fingerprint() == hd.adapter.fingerprint(full=True) == pc.adapter.fingerprint(full=True)


def test_persistent_launcher_opens_both_windows_and_auto_syncs_over_tls(tmp_path, monkeypatch):
    import httpx
    import socket
    from lightning.runtime import journal_lab
    from lightning.core.dates import today
    devices, secret = journal_lab.open_lab(tmp_path, "dummy-launcher-password")
    home, pc = devices
    links = []
    monkeypatch.setattr(journal_lab.webbrowser, "open", lambda url: links.append(url))
    for _ in range(20):
        sockets = []
        try:
            first = socket.socket()
            first.bind(("127.0.0.1", 0))
            port = first.getsockname()[1]
            sockets.append(first)
            for number in (port + 1, port + 2):
                other = socket.socket()
                sockets.append(other)
                other.bind(("127.0.0.1", number))
            break
        except OSError:
            continue
        finally:
            for listener in sockets:
                listener.close()
    else:
        pytest.fail("No local port range available")
    async def run():
        task = asyncio.create_task(journal_lab.serve(devices, secret, port))
        try:
            for _ in range(100):
                if len(links) == 2:
                    break
                await asyncio.sleep(0.05)
            assert len(links) == 2
            async with httpx.AsyncClient(follow_redirects=True, trust_env=False) as client:
                page = await client.get(links[1])
                assert page.status_code == 200
                draft = re.search(r'name="draft" value="([^"]+)"', page.text).group(1)
                csrf = client.cookies.get("journal_session")
                category = next(label for label in pc.choices()["categories"] if label.startswith("Food"))
                origin = f"http://127.0.0.1:{port + 1}"
                response = await client.post(origin + "/save", headers={"origin": origin}, data=dict(
                    __session=csrf, draft=draft, account="Bank", category=category, date=today().isoformat(), amount="-10.00"))
                assert response.status_code == 200
                for _ in range(100):
                    if not pc.store.pending():
                        break
                    await asyncio.sleep(0.05)
                assert not pc.store.pending()
                assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 990
                assert pc.store.fingerprint() == home.store.fingerprint()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    try:
        asyncio.run(run())
    finally:
        for device in devices:
            device.store.close()


def test_missing_authority_table_cannot_fall_back_to_a_legacy_writer(devices):
    _, pc = devices
    key = pc.c.db.copy_key()
    pc.c.db.conn.set_authorizer(None)  # Simulate damaged authority metadata.
    pc.c.db.execute("DROP TABLE journal_meta")
    with pytest.raises(ReadOnlyCopyError, match="journal runtime"):
        build(pc.c.db.path, key=key)
