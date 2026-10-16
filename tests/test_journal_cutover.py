"""Legacy retirement blocks v1 lending, including after interruption/restart."""
import os
from decimal import Decimal
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from lightning.bootstrap import build
from lightning.database.snapshot import snapshot
from lightning.sync.control import ControlCorrupt, ControlStore, Peer
from lightning.sync.domain import BorrowRequest
from lightning.sync.identity import load_or_create
from lightning.sync.service import HomeNode
from lightning.sync.state import HomeState
from lightning.sync.journal.codec import JournalError, unpack
from lightning.sync.journal.cutover import prepare, retire, retirement
from lightning.sync.journal.cutover import prepare_candidate, verify_ready
from lightning.sync.journal.owner import OwnerCredential


@pytest.fixture
def legacy(tmp_path):
    key = os.urandom(32)
    c = build(tmp_path / 'legacy.db', key=key)
    c.account_flows.open_account('Bank', 'BANK', '2026-01-01', '1000')
    identity = load_or_create(tmp_path / 'home-identity', 'Phone')
    owner = OwnerCredential(ec.generate_private_key(ec.SECP256R1()))
    class Bridge:
        def key(self):
            return key
        def set_mode(self, mode):
            pass
    node = HomeNode.enable(c.db, live_path=c.db.path, control_folder=tmp_path / 'control',
                           home_id=identity.device_id, bridge=Bridge())
    baseline = tmp_path / 'baseline.db'
    snapshot(c.db, baseline)
    yield c, node, identity, owner, baseline
    c.db.close()


def ticket(legacy, **kwargs):
    _, node, identity, owner, baseline = legacy
    return prepare(node, baseline, owner=owner, identity=identity, generation=str(uuid4()), **kwargs)


def test_retirement_is_reviewable_then_permanently_fences_v1_and_keeps_baseline(legacy):
    c, node, identity, owner, baseline = legacy
    wire = ticket(legacy)
    assert node.model.state is HomeState.AT_HOME
    assert retirement(node.store) is None
    body = unpack(wire)['body']
    assert body['home_key'] != body['owner_key']
    assert body['profile'] == node.model.profile_id
    assert retire(node, baseline, wire, owner_key=owner.public_key) == wire
    assert retirement(ControlStore(node.store.path.parent)) == wire
    for operation in (lambda: node.model, node.writable, node.take_back):
        with pytest.raises(ControlCorrupt):
            operation()
    assert retire(node, baseline, wire, owner_key=owner.public_key) == wire
    assert baseline.exists()
    assert c.reporting.account_balance(c.accounts.find_by_text('Bank').id) == 1000


@pytest.mark.parametrize('phase', ['legacy_fence_prepared', 'legacy_fence_committed'])
def test_interrupted_retirement_has_either_the_original_or_durable_retired_state(legacy, phase):
    _, node, identity, owner, baseline = legacy
    wire = ticket(legacy)
    def fault(at):
        if at == phase:
            raise RuntimeError('interrupted retirement')
    with pytest.raises(RuntimeError):
        retire(node, baseline, wire, owner_key=owner.public_key, fault=fault)
    saved = retirement(ControlStore(node.store.path.parent))
    if phase == 'legacy_fence_prepared':
        assert saved is None
        assert node.model.state is HomeState.AT_HOME
    else:
        assert saved == wire
        with pytest.raises(ControlCorrupt):
            node.take_back()
    assert retire(node, baseline, wire, owner_key=owner.public_key) == wire


def test_legacy_changes_after_review_require_a_new_baseline(legacy):
    c, node, _, owner, baseline = legacy
    wire = ticket(legacy)
    bank = c.accounts.find_by_text('Bank').id
    food = c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    c.transactions.record_outflow('2026-09-01', bank, '10.01', food)
    with pytest.raises(JournalError, match='changed after'):
        retire(node, baseline, wire, owner_key=owner.public_key)
    assert retirement(node.store) is None
    assert node.model.state is HomeState.AT_HOME
    assert c.reporting.account_balance(bank) == Decimal('989.99')


def test_unreturned_checkout_needs_exact_explicit_stranded_copy_retention(legacy):
    _, node, identity, owner, baseline = legacy
    peer = str(uuid4())
    node.pair(Peer(peer, 'PC', '', '', ''))
    model = node.model
    checkout = str(uuid4())
    request = BorrowRequest(str(uuid4()), checkout, model.profile_id, model.home_id, model.lineage_id,
                            peer, model.checkpoint_id, model.checkpoint_sha256, model.compatibility)
    node.store.home(lambda home: home.borrow(request, authenticated_peer=peer))
    with pytest.raises(JournalError, match='explicitly retain'):
        ticket(legacy)
    with pytest.raises(JournalError, match='explicitly retain'):
        ticket(legacy, retained_checkout=str(uuid4()))
    wire = ticket(legacy, retained_checkout=checkout)
    assert unpack(wire)['body']['stranded'] == [checkout]
    retire(node, baseline, wire, owner_key=owner.public_key)
    assert retirement(node.store) == wire
    assert baseline.exists()
    with pytest.raises(ControlCorrupt):
        node.take_back()


def test_cutover_needs_both_independent_owner_and_existing_home_signatures(legacy):
    _, node, identity, owner, baseline = legacy
    from lightning.sync.journal.codec import seal
    wire = ticket(legacy)
    body = unpack(wire)['body']
    body['generation'] = str(uuid4())
    forged = seal(body, owner.sign)
    with pytest.raises(JournalError, match='existing home'):
        retire(node, baseline, forged, owner_key=owner.public_key)
    assert retirement(node.store) is None
    assert node.model.state is HomeState.AT_HOME


def test_candidate_preserves_all_legacy_money_and_cannot_confirm_before_retirement_and_authority(legacy, tmp_path):
    from lightning.sync.journal.finance import attach
    from lightning.sync.journal.home import JournalHome
    c, node, identity, owner, baseline = legacy
    bank = c.accounts.find_by_text('Bank').id
    c.transactions.record_outflow('2026-09-01', bank, '10.01', c.categories.get_by_code('EXP.PERSONAL.FOOD').id)
    broker = c.account_flows.open_account('Broker', 'BROKERAGE', '2026-01-01', '1000')
    stock = c.assets.create_investment('Cutover stock', 'STOCK', 'CUT')
    c.investments.buy('2026-09-01', broker.id, stock.id, '1', '100.01')
    baseline = tmp_path / 'full-baseline.db'
    snapshot(c.db, baseline)
    wire = prepare(node, baseline, owner=owner, identity=identity, generation=str(uuid4()))
    target, incarnation = tmp_path / 'candidate.db', str(uuid4())
    manifest = prepare_candidate(baseline, target, wire, key=c.db.copy_key(), identity=identity,
                                 incarnation=incarnation, owner_key=owner.public_key)
    assert node.model.state is HomeState.AT_HOME  # Preflight has no v1 side effects.
    with pytest.raises(JournalError, match='Retire legacy'):
        verify_ready(node, baseline, target, wire, manifest, key=c.db.copy_key(), identity=identity,
                     incarnation=incarnation, owner_key=owner.public_key)
    opened = build(target, key=c.db.copy_key(), experimental_journal=True)
    try:
        store = attach(opened)
        assert store.config['version'] == 3
        assert opened.reporting.account_balance(bank) == Decimal('989.99')
        assert opened.reporting.account_balance(broker.id) == Decimal('899.99')
        assert opened.investments.holding(broker.id, stock.id) == 1
        with pytest.raises(JournalError, match='[Aa]uthority'):
            JournalHome(store, identity.sign).process()
    finally:
        opened.db.close()
    retire(node, baseline, wire, owner_key=owner.public_key)
    ready = verify_ready(node, baseline, target, wire, manifest, key=c.db.copy_key(), identity=identity,
                          incarnation=incarnation, owner_key=owner.public_key)
    assert ready['fingerprint'] == unpack(manifest)['body']['fingerprint']
    assert c.reporting.account_balance(bank) == Decimal('989.99')
    assert baseline.exists()


def test_completed_candidate_resumes_without_overwriting_or_changing_its_identity(legacy, tmp_path):
    c, node, identity, owner, baseline = legacy
    wire = ticket(legacy)
    target, incarnation = tmp_path / 'candidate.db', str(uuid4())
    def fault(phase):
        if phase == 'cutover_candidate_committed':
            raise RuntimeError('stopped before manifest publication')
    with pytest.raises(RuntimeError):
        prepare_candidate(baseline, target, wire, key=c.db.copy_key(), identity=identity,
                          incarnation=incarnation, owner_key=owner.public_key, fault=fault)
    before = target.read_bytes()
    result = prepare_candidate(baseline, target, wire, key=c.db.copy_key(), identity=identity,
                                incarnation=incarnation, owner_key=owner.public_key)
    assert target.read_bytes() == before
    assert unpack(result)['body']['incarnation'] == incarnation
    with pytest.raises(JournalError, match='another identity'):
        prepare_candidate(baseline, target, wire, key=c.db.copy_key(), identity=identity,
                          incarnation=str(uuid4()), owner_key=owner.public_key)


def test_precommit_candidate_failure_retains_evidence_and_keeps_legacy_authority(legacy, tmp_path):
    c, node, identity, owner, baseline = legacy
    wire = ticket(legacy)
    target = tmp_path / 'candidate.db'
    def fault(phase):
        if phase == 'cutover_candidate_prepared':
            raise RuntimeError('stopped before commit')
    with pytest.raises(RuntimeError):
        prepare_candidate(baseline, target, wire, key=c.db.copy_key(), identity=identity,
                          incarnation=str(uuid4()), owner_key=owner.public_key, fault=fault)
    assert node.model.state is HomeState.AT_HOME
    assert retirement(node.store) is None
    assert target.exists() and baseline.exists()
    with pytest.raises(JournalError, match='incomplete'):
        prepare_candidate(baseline, target, wire, key=c.db.copy_key(), identity=identity,
                          incarnation=str(uuid4()), owner_key=owner.public_key)
