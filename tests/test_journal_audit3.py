"""Audit 3 (4C): the edit-journal gaps it found stay fixed."""
import asyncio
from uuid import uuid4

import pytest

from test_journal_finance import devices, groups  # noqa: F401  (fixture)
from test_journal_cloud import Carrier, peers
from lightning.core.errors import ValidationError
from lightning.sync.journal.cloud import CloudUnavailable, MailboxExchange
from lightning.sync.journal.codec import JournalError, origin_id, unpack


def status(hd, wire):
    return hd.home.status(origin_id(unpack(wire)["body"]["origin"]))


def account(device, name):
    return next(item for item in device.c.accounts.list() if item.name == name)


def spend(hd, pc, amount="-20"):
    """A confirmed cash payment made through the screens' command path."""
    bank = pc.adapter.uid("accounts", account(pc, "Bank").id)
    food = pc.adapter.uid("categories", pc.c.categories.get_by_code("EXP.PERSONAL.FOOD").id)
    args = dict(account_id=bank, date="2026-09-01", amount=amount, category_id=food, other_account_id=None,
                counterparty="", notes="", owner_id=None)
    wire = pc.command("transactions.record_in_account", description="", **args)
    pc.sync_with(hd.home)
    assert status(hd, wire)["status"] == "accepted"
    return unpack(wire)["body"]["record"], args


def bank_line(device, record):
    return device.c.db.scalar("SELECT amount_e6 FROM ledger_entries WHERE transaction_id=? ORDER BY line_no LIMIT 1",
                              (device.adapter.local("transactions", record),))



def test_4c1_stale_amount_edit_waits_for_review(devices):
    hd, pc = devices
    record, args = spend(hd, pc)
    hd.command("transactions.update_in_account", txn_id=record, **(args | dict(amount="-30")))
    late = pc.command("transactions.update_in_account", txn_id=record, **(args | dict(amount="-40")))  # Saw -20.
    pc.sync_with(hd.home)
    assert status(hd, late) == dict(status="review", reason="conflict")
    assert bank_line(hd, record) == -30_000_000



def test_4c2_replay_detects_a_diverged_replica(devices):
    hd, pc = devices
    spend(hd, pc)
    pc.adapter.allowed = True  # Stands in for any replay bug or stray local write.
    with pc.c.db.transaction():
        pc.c.db.execute("UPDATE ledger_entries SET memo='diverged' WHERE id=(SELECT MAX(id) FROM ledger_entries)")
    pc.adapter.allowed = False
    with pytest.raises(JournalError, match="fingerprint"):
        spend(hd, pc, "-5")


def test_4c3_register_edit_keeps_a_command_change(devices):
    hd, pc = devices
    payment = groups(pc, "-10.00")
    record = str(uuid4())
    pc.save(payment, record=record)
    pc.sync_with(hd.home)
    bank = pc.adapter.uid("accounts", account(pc, "Bank").id)
    hd.command("transactions.update_in_account", txn_id=record, account_id=bank, date="2026-09-01", amount="-99",
               category_id=payment["category"]["category"], other_account_id=None, counterparty="", notes="",
               owner_id=None)
    pc.sync_with(hd.home)
    with pytest.raises(ValidationError, match="another screen"):
        pc.save(dict(details=dict(counterparty="", notes="lunch", description="")), record=record)
    assert bank_line(hd, record) == bank_line(pc, record) == -99_000_000


def test_4c4_mailbox_recovers_after_one_transient_home_refusal(devices, monkeypatch):
    home, pc = devices
    hp, pp = peers(devices, Carrier())
    pc.save(groups(pc))
    real, calls = type(home.home).process, []
    def once_frozen(self, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise JournalError("Confirmation is frozen or authority repair is required")
        return real(self, **kwargs)
    monkeypatch.setattr(type(home.home), "process", once_frozen)
    async def run():
        for _ in range(30):
            await hp.pump()
            try:
                await pp.channel.synchronize(MailboxExchange(pp), home_id=home.identity.device_id)
                return True
            except CloudUnavailable:
                continue
        return False
    assert asyncio.run(run()) and not pc.store.pending()


def test_4c5_stale_bulk_action_waits_for_review(devices):
    hd, pc = devices
    record, args = spend(hd, pc)
    other = pc.adapter.uid("categories", pc.c.categories.get_by_code("EXP.PERSONAL.FOOD").parent_id)
    hd.command("transactions.update_in_account", txn_id=record, **(args | dict(amount="-30")))
    late = pc.command("transactions.set_category", txn_ids=[record], category_id=other)  # Saw -20.
    pc.sync_with(hd.home)
    assert status(hd, late) == dict(status="review", reason="conflict")
    fresh = pc.command("transactions.set_category", txn_ids=[record], category_id=args["category_id"])
    pc.sync_with(hd.home)  # Strict order: it waits behind the review, then is checked against what it saw.
    assert status(hd, fresh)["status"] == "staged"
