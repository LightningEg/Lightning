from __future__ import annotations

import os
from uuid import uuid4

import pytest

from lightning.bootstrap import build
from lightning.sync.identity import load_or_create
from lightning.sync.journal.automation import JournalAutomation
from lightning.sync.journal.codec import JournalError
from lightning.sync.journal.device import JournalDevice
from lightning.sync.journal.finance import attach, initialize
from lightning.sync.journal.home import JournalHome
from lightning.sync.journal.snapshots import checkpoint_replica
from lightning.workflows.live_prices import Plan


@pytest.fixture
def devices(tmp_path):
    profile, generation = str(uuid4()), str(uuid4())
    identities = [load_or_create(tmp_path / f"identity-{i}", f"Device {i}") for i in range(2)]
    home_container = build(tmp_path / "home.db", key=os.urandom(32))
    home_container.account_flows.open_account("Bank", "BANK", "2026-01-01", "1000")
    home_store = initialize(
        home_container, profile=profile, generation=generation,
        device=identities[0].device_id, incarnation=str(uuid4()),
        home_key=identities[0].public_key, origin_key=identities[0].public_key,
        role="home", dummy_profile=True,
    )
    checkpoint_replica(home_store, tmp_path / "replica.db", identities[0].sign,
                       device=identities[1].device_id, incarnation=str(uuid4()),
                       origin_key=identities[1].public_key)
    replica_container = build(tmp_path / "replica.db", key=home_container.db.copy_key(),
                              experimental_journal=True)
    replica_store = attach(replica_container)
    home = JournalHome(home_store, identities[0].sign)
    for store, identity in zip((home_store, replica_store), identities):
        home.approve_origin(identity.device_id, store.config["incarnation"], identity.public_key)
    home_device = JournalDevice(home_store, identities[0], home)
    replica_device = JournalDevice(replica_store, identities[1])
    yield home_device, replica_device
    home_container.db.close()
    replica_container.db.close()


def test_daily_automation_job_is_idempotent_and_publishes_one_receipt(devices):
    home, replica = devices
    automation = JournalAutomation(home)
    first = automation.dispatch_once("revaluation:2026-10-22", "automation.process_due")
    commits = home.store.db.scalar("SELECT COUNT(*) FROM journal_commits")
    again = automation.dispatch_once("revaluation:2026-10-22", "automation.process_due")

    assert first["state"] == "accepted"
    assert again == first
    assert home.store.db.scalar("SELECT COUNT(*) FROM journal_commits") == commits
    assert home.store.db.scalar("SELECT COUNT(*) FROM journal_automation_jobs") == 1


def test_automation_job_key_cannot_be_reused_for_different_work(devices):
    automation = JournalAutomation(devices[0])
    automation.dispatch_once("bill-match:2026-10-22", "automation.match_bills", as_of="2026-10-22")

    with pytest.raises(JournalError, match="reused"):
        automation.dispatch_once("bill-match:2026-10-22", "automation.process_due")


def test_replica_cannot_issue_home_automation(devices):
    home, replica = devices

    with pytest.raises(JournalError, match="only on the home"):
        replica.command("automation.process_due")

    assert home.store.db.scalar("SELECT COUNT(*) FROM journal_commits") == 0


def test_live_price_result_is_saved_on_home_and_replayed_as_exact_rows(devices):
    home, replica = devices
    automation = JournalAutomation(home)
    before = replica.store.fingerprint()
    result = automation.accept_prices((Plan("2026-10-22"), {}, []))

    assert result["state"] == "accepted"
    assert home.store.db.scalar(
        "SELECT state FROM journal_automation_results WHERE job_key='live-prices:2026-10-22'") == "applied"
    replica.sync_with(home.home)
    assert home.store.fingerprint() == replica.store.fingerprint()
    assert replica.store.fingerprint() != before
