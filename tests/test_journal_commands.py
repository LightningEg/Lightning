"""J6c: covered service actions travel as command proposals with exact row effects."""
from uuid import uuid4

import pytest

from test_journal_finance import devices, groups
from lightning.sync.journal.codec import origin_id, unpack


def status(home, wire):
    return home.home.status(origin_id(unpack(wire)["body"]["origin"]))


def account(device, name):
    return next(item for item in device.c.accounts.list() if item.name == name)


def test_open_and_rename_an_account_from_a_replica_replays_exactly(devices):
    hd, pc = devices
    wire = pc.command("accounts.open", currency=None, opening_balance_date=None, owner_id=None, name="Savings", account_type="BANK", opening_date="2026-02-01",
                      opening_balance="500", institution="", last4=None, notes="")
    assert not any(item.name == "Savings" for item in pc.c.accounts.list())  # Pending until the home confirms.
    pc.sync_with(hd.home)
    assert status(hd, wire)["status"] == "accepted"
    savings = account(pc, "Savings")
    assert pc.c.reporting.account_balance(savings.id) == 500
    uid = unpack(wire)["body"]["record"]
    assert pc.adapter.uid("accounts", savings.id) == uid == hd.adapter.uid("accounts", account(hd, "Savings").id)
    rename = hd.command("accounts.update", account_id=uid, name="Rainy day", institution="", account_type="BANK",
                        opening_date="2026-02-01", last4=None, notes="")
    assert status(hd, rename)["status"] == "accepted"
    pc.sync_with(hd.home)
    assert account(pc, "Rainy day").id == savings.id
    assert hd.store.fingerprint() == pc.store.fingerprint() == pc.adapter.fingerprint(full=True)
    # A cash transaction can use the account another device created.
    money = groups(pc, "-20.00")
    money["money"]["account"] = uid
    pc.save(money)
    pc.sync_with(hd.home)
    assert pc.c.reporting.account_balance(savings.id) == 480


def test_concurrent_change_to_the_same_record_waits_for_review(devices):
    hd, pc = devices
    bank = pc.adapter.uid("accounts", account(pc, "Bank").id)
    fields = dict(institution="", account_type="BANK", opening_date="2026-01-01", last4=None, notes="")
    first = hd.command("accounts.update", account_id=bank, name="Main bank", **fields)
    late = pc.command("accounts.update", account_id=bank, name="Salary bank", **fields)  # Saw the old name.
    pc.sync_with(hd.home)
    assert status(hd, first)["status"] == "accepted"
    assert status(hd, late) == dict(status="review", reason="conflict")
    assert [item["state"] for item in pc.pending_commands()] == ["Needs review"]
    state = hd.home.review_state(origin_id(unpack(late)["body"]["origin"]))
    hd.home.review(command_id=str(uuid4()), proposal_id=state["proposal_id"], token=state["token"], choice="apply")
    pc.sync_with(hd.home)
    assert account(pc, "Salary bank") and not pc.pending_commands()


def test_two_changes_from_one_device_chain_without_conflict(devices):
    hd, pc = devices
    food = pc.c.categories.get_by_code("EXP.PERSONAL.FOOD")
    created = pc.command("categories.create", parent_id=pc.adapter.uid("categories", food.parent_id), name="Coffee",
                         default_reimbursable=None)
    record = unpack(created)["body"]["record"]
    renamed = pc.command("categories.update", category_id=record, name="Coffee out", active=True, default_reimbursable=None)
    pc.sync_with(hd.home)
    assert status(hd, created)["status"] == status(hd, renamed)["status"] == "accepted"
    assert pc.c.categories.get(pc.adapter.local("categories", record)).name == "Coffee out"
    assert hd.store.fingerprint() == pc.store.fingerprint()


def test_service_refusal_and_uncovered_areas_are_refused_not_written(devices):
    hd, pc = devices
    duplicate = pc.command("accounts.open", currency=None, opening_balance_date=None, owner_id=None, name="Bank", account_type="BANK", opening_date="2026-02-01",
                           opening_balance="0", institution="", last4=None, notes="")
    pc.sync_with(hd.home)
    assert status(hd, duplicate) == dict(status="rejected", reason="financial-validation")
    with pytest.raises(Exception, match="not covered"):
        pc.command("rules.create", name="x")
    assert hd.store.fingerprint() == pc.store.fingerprint()


def test_original_inflow_wire_without_description_remains_accepted(devices):
    home, replica = devices
    bank = account(replica, "Bank")
    category = replica.c.categories.get_by_code("EXP.WORK.SALARY")
    wire = replica.command("transactions.record_inflow",
        date="2026-09-02", account_id=replica.adapter.uid("accounts", bank.id),
        amount="125", notes="queued before the update", owner_id=None,
        category_id=replica.adapter.uid("categories", category.id), counterparty="Employer")
    replica.sync_with(home.home)
    assert status(home, wire)["status"] == "accepted"
    assert home.store.fingerprint() == replica.store.fingerprint()
