"""Journal area: currencies, rates, foreign accounts, conversions and reserves travel as commands."""
from decimal import Decimal
from uuid import uuid4

import pytest

from test_journal_finance import devices, groups  # noqa: F401
from lightning.sync.journal.codec import origin_id, unpack


def status(home, wire):
    return home.home.status(origin_id(unpack(wire)["body"]["origin"]))


def settle(hd, pc, *wires):
    pc.sync_with(hd.home)
    assert [status(hd, wire)["status"] for wire in wires] == ["accepted"] * len(wires)
    assert hd.store.fingerprint() == pc.store.fingerprint() == pc.adapter.fingerprint(full=True)


def account(device, name):
    return next(item for item in device.c.accounts.list() if item.name == name)


def uid(device, table, local_id):
    return device.adapter.uid(table, local_id)


def usd_setup(hd, pc):
    """USD registered, a rate saved and a USD account opened by the replica."""
    register = pc.command("currencies.register", code="USD", name=None)
    rate = pc.command("currencies.save_rate", currency="USD", day="2026-09-01", rate="48.5")
    opened = pc.command("accounts.open", opening_balance_date=None, owner_id=None, name="Dollars", account_type="BANK", opening_date="2026-09-01",
                        opening_balance="200", institution="", currency="USD", last4=None, notes="")
    settle(hd, pc, register, rate, opened)
    return unpack(opened)["body"]["record"]


def test_register_a_currency_save_a_rate_and_open_a_foreign_account(devices):
    hd, pc = devices
    assert not any(row["code"] == "USD" for row in pc.c.currencies.list())
    dollars = usd_setup(hd, pc)
    assert [row["code"] for row in pc.c.currencies.list()] == [row["code"] for row in hd.c.currencies.list()] == ["EGP", "USD"]
    assert [(row["date"], row["rate"]) for row in pc.c.fx.list()] == [("2026-09-01", Decimal("48.5"))]
    usd = account(pc, "Dollars")
    assert usd.currency == "USD" and pc.adapter.uid("accounts", usd.id) == dollars
    assert pc.c.reporting.account_balance(usd.id) == hd.c.reporting.account_balance(account(hd, "Dollars").id) == 200
    # A newer rate for the same day is an exact replacement, from either device.
    again = hd.command("currencies.save_rate", currency="USD", day="2026-09-01", rate="49.25")
    assert status(hd, again)["status"] == "accepted"
    pc.sync_with(hd.home)
    assert [row["rate"] for row in pc.c.fx.list()] == [Decimal("49.25")]
    assert hd.store.fingerprint() == pc.store.fingerprint() == pc.adapter.fingerprint(full=True)


def test_convert_with_a_fee_then_edit_the_conversion(devices):
    hd, pc = devices
    # Fund the conversion and its fee without borrowing from the bank.
    funding = hd.command("transactions.record_inflow", date="2026-09-01",
                         account_id=uid(hd, "accounts", account(hd, "Bank").id), amount="5000",
                         category_id=uid(hd, "categories", hd.c.categories.get_by_code("EXP.WORK.SALARY").id),
                         counterparty="", notes="Conversion funding", owner_id=None)
    settle(hd, pc, funding)
    dollars = usd_setup(hd, pc)
    bank = uid(pc, "accounts", account(pc, "Bank").id)
    convert = pc.command("transactions.record_conversion", date="2026-09-02", from_account_id=bank, to_account_id=dollars,
                         sent="4850", received="100", fee="10", description="", notes="airport")
    assert pc.c.reporting.account_balance(account(pc, "Dollars").id) == 200  # Pending until the home confirms.
    settle(hd, pc, convert)
    record = unpack(convert)["body"]["record"]
    txn = pc.c.transactions.get(pc.adapter.local("transactions", record))
    described = pc.c.transactions.conversion_of(txn)
    assert (described.sent, described.received, described.fee) == (4850, 100, 10)
    assert pc.c.reporting.account_balance(account(pc, "Dollars").id) == 300
    assert pc.c.reporting.account_balance(account(pc, "Bank").id) == hd.c.reporting.account_balance(account(hd, "Bank").id)
    trade = [row for row in pc.c.db.all("SELECT * FROM fx_rates WHERE source='TRADE'")]
    assert len(trade) == 1 and trade == [row for row in hd.c.db.all("SELECT * FROM fx_rates WHERE source='TRADE'")]
    edit = hd.command("transactions.update_conversion", txn_id=record, date="2026-09-02", from_account_id=bank,
                      to_account_id=dollars, sent="4900", received="100", fee="5", description="", notes="airport")
    assert status(hd, edit)["status"] == "accepted"
    pc.sync_with(hd.home)
    assert pc.c.transactions.conversion_of(pc.c.transactions.get(pc.adapter.local("transactions", record))).sent == 4900
    assert hd.store.fingerprint() == pc.store.fingerprint() == pc.adapter.fingerprint(full=True)
    assert str(pc.c.db.one("SELECT rate_e6 FROM fx_rates WHERE source='TRADE'")["rate_e6"]) == \
        str(hd.c.db.one("SELECT rate_e6 FROM fx_rates WHERE source='TRADE'")["rate_e6"])


def test_create_a_reserve_set_money_aside_link_a_payment_and_complete_it(devices):
    hd, pc = devices
    created = pc.command("reserves.create", name="Holiday", target="500", due_date=None, recurrence="NONE",
                         counterparty_id=None, category_id=None, account_id=None, kind="PROJECT")
    reserve = unpack(created)["body"]["record"]
    aside = pc.command("reserves.allocate", reserve_id=reserve, amount="300")
    settle(hd, pc, created, aside)
    for device in (hd, pc):
        row = device.c.reserves.get(device.adapter.local("cash_reserves", reserve))
        assert (row["name"], row["allocated"], row["target"]) == ("Holiday", 300, 500)
    # The history the service wrote travels too, naming the reserve through its UUID.
    assert pc.c.reserves.allocation_at("2026-12-31") == hd.c.reserves.allocation_at("2026-12-31") == 300
    release = pc.command("reserves.allocate", reserve_id=reserve, amount="250")
    rename = hd.command("reserves.update", reserve_id=reserve, name="Summer holiday", target="600", due_date="2027-06-01",
                        recurrence="NONE", counterparty_id=None, category_id=None, account_id=None)
    assert status(hd, rename)["status"] == "accepted"
    pc.sync_with(hd.home)
    assert status(hd, release)["status"] == "review"  # It saw the reserve before the rename.
    state = hd.home.review_state(origin_id(unpack(release)["body"]["origin"]))
    hd.home.review(command_id=str(uuid4()), proposal_id=state["proposal_id"], token=state["token"], choice="apply")
    pc.sync_with(hd.home)
    # Link a posted payment, then close the reserve.
    pc.save(groups(pc, "-100.00"))
    pc.sync_with(hd.home)
    txn = pc.c.db.one("SELECT id FROM transactions WHERE type='OUT' ORDER BY id DESC")["id"]
    link = pc.command("reserves.link_payment", reserve_id=reserve, transaction_id=uid(pc, "transactions", txn), amount="100")
    settle(hd, pc, link)
    for device in (hd, pc):
        row = device.c.reserves.get(device.adapter.local("cash_reserves", reserve))
        assert (row["name"], row["allocated"], row["spent"]) == ("Summer holiday", 250, 100)
        assert len(device.c.reserves.links_for_reserve(row["id"])) == 1
    unlink = pc.command("reserves.unlink_payment", reserve_id=reserve, transaction_id=uid(pc, "transactions", txn))
    settle(hd, pc, unlink)
    assert pc.c.reserves.links_for_reserve(pc.adapter.local("cash_reserves", reserve)) == []
    complete = pc.command("reserves.complete", reserve_id=reserve)
    settle(hd, pc, complete)
    assert hd.c.reserves.get(hd.adapter.local("cash_reserves", reserve))["status"] == "COMPLETE"
    assert hd.c.reserves.list_active() == pc.c.reserves.list_active() == []


def test_a_deleted_reserve_left_in_history_does_not_stop_the_journal(devices):
    hd, pc = devices
    with hd.adapter.writing():
        gone = hd.c.reserves.create("Old", "100")
        hd.c.reserves.delete(gone["id"])  # Legacy data: history keeps naming a reserve that no longer exists.
    assert hd.c.db.scalar("SELECT COUNT(*) FROM reserve_allocation_history WHERE status='DELETED'") == 1
    assert hd.adapter.fingerprint(full=True) == hd.adapter.fingerprint(full=True)
    assert all(row["values"] is None or row["values"]["reserve_id"] for row in hd.adapter.rows.all_rows()
               if row["table"] == "reserve_allocation_history")


def test_concurrent_rate_for_a_reserve_conflicts_and_refusals_write_nothing(devices):
    hd, pc = devices
    created = pc.command("reserves.create", name="Car", target="900", due_date=None, recurrence="NONE",
                         counterparty_id=None, category_id=None, account_id=None, kind="PROJECT")
    reserve = unpack(created)["body"]["record"]
    settle(hd, pc, created)
    first = hd.command("reserves.allocate", reserve_id=reserve, amount="100")
    late = pc.command("reserves.allocate", reserve_id=reserve, amount="200")  # Saw the old amount.
    pc.sync_with(hd.home)
    assert status(hd, first)["status"] == "accepted"
    assert status(hd, late) == dict(status="review", reason="conflict")
    assert [item["state"] for item in pc.pending_commands()] == ["Needs review"]
    state = hd.home.review_state(origin_id(unpack(late)["body"]["origin"]))
    hd.home.review(command_id=str(uuid4()), proposal_id=state["proposal_id"], token=state["token"], choice="apply")
    pc.sync_with(hd.home)
    assert pc.c.reserves.get(pc.adapter.local("cash_reserves", reserve))["allocated"] == 200
    assert hd.store.fingerprint() == pc.store.fingerprint() == pc.adapter.fingerprint(full=True)


def test_service_refusals_are_rejected_without_writing(devices):
    hd, pc = devices
    unregistered = pc.command("currencies.save_rate", currency="GBP", day="2026-09-01", rate="60")
    too_much = pc.command("reserves.create", name="Nothing", target="0", due_date=None, recurrence="NONE",
                          counterparty_id=None, category_id=None, account_id=None, kind="PROJECT")
    pc.sync_with(hd.home)
    assert status(hd, unregistered) == dict(status="rejected", reason="financial-validation")
    assert status(hd, too_much) == dict(status="rejected", reason="financial-validation")
    assert hd.c.fx.list() == [] and hd.c.reserves.list_active() == []
    assert hd.store.fingerprint() == pc.store.fingerprint() == pc.adapter.fingerprint(full=True)
    with pytest.raises(Exception, match="at most two decimal"):
        pc.command("currencies.save_rate", currency="USD", day="2026-09-01", rate="1.1234567")
