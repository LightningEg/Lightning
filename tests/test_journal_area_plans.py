"""Plans and budgets travel as command proposals with exact row effects."""
from decimal import Decimal
from uuid import uuid4

import pytest

from test_journal_finance import devices, groups  # noqa: F401
from lightning.sync.journal.codec import origin_id, unpack


def status(home, wire):
    return home.home.status(origin_id(unpack(wire)["body"]["origin"]))


def same(hd, pc):
    assert hd.store.fingerprint() == pc.store.fingerprint() == pc.adapter.fingerprint(full=True)


def uid(device, table, name_or_id):
    return device.adapter.uid(table, name_or_id)


def account(device, name):
    return next(item for item in device.c.accounts.list() if item.name == name)


def plan(device, name):
    return next(item for item in device.c.planning.items(active_only=False) if item.name == name)


def category(device, code="EXP.PERSONAL.FOOD"):
    return device.c.categories.get_by_code(code)


def add_rent(pc, **changes):
    values = dict(kind="BILL", name="Rent", amount="300.00", frequency="MONTHLY", interval_count=1, start_date="2026-09-05",
                  end_date=None, payment_count=None, account_id=uid(pc, "accounts", account(pc, "Bank").id),
                  category_id=uid(pc, "categories", category(pc).id), counterparty_id=None, principal=None, notes="",
                  weekend_move="none", month_day=None, match_window_days=None, match_tolerance_pct=None)
    return pc.command("plans.add", **(values | changes))


def edit_values(item, pc, **changes):
    values = dict(kind=item.kind.value, name=item.name, amount=f"{item.amount:.2f}", frequency=item.frequency.value,
                  interval_count=item.interval_count, start_date=item.start_date, end_date=item.end_date, payment_count=None,
                  account_id=uid(pc, "accounts", item.account_id), category_id=uid(pc, "categories", item.category_id),
                  counterparty_id=None, principal=None, notes=item.notes, weekend_move=item.weekend_move.value,
                  match_window_days=item.match_window_days, match_tolerance_pct=item.match_tolerance_pct)
    return values | changes


def test_create_and_pay_a_bill_links_a_transaction_exactly(devices):
    hd, pc = devices
    wire = add_rent(pc)
    assert not pc.c.planning.items()  # Pending until the home confirms.
    pc.sync_with(hd.home)
    assert status(hd, wire)["status"] == "accepted"
    item = plan(pc, "Rent")
    record = unpack(wire)["body"]["record"]
    assert uid(pc, "planned_items", item.id) == record == uid(hd, "planned_items", plan(hd, "Rent").id)
    assert item.amount == Decimal("300") and item.account_id == account(pc, "Bank").id
    paid = pc.command("plans.pay", item_id=record, due_date="2026-09-05", date_paid="2026-09-05", amount="300.00",
                      account_id=None)
    pc.sync_with(hd.home)
    assert status(hd, paid)["status"] == "accepted"
    assert next(row for row in pc.balances() if row["name"] == "Bank")["balance"] == 700  # 1000 - 300
    payment = next(p for p in pc.c.planning.payments(plan(pc, "Rent"), "2026-09-30", None) if p.due_date == "2026-09-05")
    assert payment.status.value == "PAID"
    assert pc.c.planning.linked_transaction_ids() == hd.c.planning.linked_transaction_ids() and pc.c.planning.linked_transaction_ids()
    same(hd, pc)
    # The home issues commands too, and a later skip of the next date also replays on the replica.
    skip = hd.command("plans.skip", item_id=record, due_date="2026-10-05")
    assert status(hd, skip)["status"] == "accepted"
    pc.sync_with(hd.home)
    same(hd, pc)
    reopen = pc.command("plans.reopen", item_id=record, due_date="2026-10-05")
    pc.sync_with(hd.home)
    assert status(hd, reopen)["status"] == "accepted" and not hd.c.planning.is_installment_purchase(item.id)
    same(hd, pc)


def test_payee_plan_and_payment_chain_in_one_sync_without_conflict(devices):
    hd, pc = devices
    payee = pc.command("plans.add_payee", name="Landlord", default_category_id=None, alias=None, kind=None)
    party = unpack(payee)["body"]["record"]
    created = add_rent(pc, counterparty_id=party)
    record = unpack(created)["body"]["record"]
    renamed = pc.command("plans.set_amount", item_id=record, amount="350.00")
    pc.sync_with(hd.home)
    assert [status(hd, wire)["status"] for wire in (payee, created, renamed)] == ["accepted"] * 3
    item = plan(pc, "Rent")
    assert item.amount == Decimal("350") and pc.c.counterparties.get(item.counterparty_id)["name"] == "Landlord"
    same(hd, pc)


def test_edit_and_remove_a_plan(devices):
    hd, pc = devices
    created = add_rent(pc)
    record = unpack(created)["body"]["record"]
    pc.sync_with(hd.home)
    item = plan(pc, "Rent")
    edit = pc.command("plans.update", item_id=record, **edit_values(item, pc, name="Flat rent", amount="320.00", notes="Cairo"))
    pc.sync_with(hd.home)
    assert status(hd, edit)["status"] == "accepted"
    assert plan(hd, "Flat rent").amount == Decimal("320") and plan(pc, "Flat rent").notes == "Cairo"
    same(hd, pc)
    pc.command("plans.pay", item_id=record, due_date="2026-09-05", date_paid="2026-09-05", amount="320.00", account_id=None)
    pc.sync_with(hd.home)
    stop = pc.command("plans.remove", item_id=record)  # Paid history exists, so it stops instead of vanishing.
    pc.sync_with(hd.home)
    assert status(hd, stop)["status"] == "accepted"
    assert not plan(pc, "Flat rent").active and not pc.c.planning.items()
    same(hd, pc)
    other = add_rent(hd, name="Gym", kind="SUBSCRIPTION", amount="50.00")
    gym = unpack(other)["body"]["record"]
    pc.sync_with(hd.home)
    delete = pc.command("plans.remove", item_id=gym)
    pc.sync_with(hd.home)
    assert status(hd, delete)["status"] == "accepted"
    assert not any(item.name == "Gym" for item in pc.c.planning.items(active_only=False))
    assert not any(item.name == "Gym" for item in hd.c.planning.items(active_only=False))
    same(hd, pc)


def test_set_a_budget_and_carry_it_over(devices):
    hd, pc = devices
    food = category(pc)
    key = uid(pc, "categories", food.id)
    wire = pc.command("budgets.set", category_id=key, month="2026-09", amount="1200.00", only_this_month=False,
                      average_months=None)
    pc.sync_with(hd.home)
    assert status(hd, wire)["status"] == "accepted"
    assert hd.c.budgets.amounts_for("2026-09")[food.id][0] == Decimal("1200") == pc.c.budgets.amounts_for("2026-09")[food.id][0]
    carry = pc.command("budgets.set_carryover", month="2026-09", lines=[dict(category=key, enabled=True)])
    pc.sync_with(hd.home)
    assert status(hd, carry) == dict(status="accepted", reason="accepted")
    assert pc.c.budgets.repo.carryover_settings("2026-09") == hd.c.budgets.repo.carryover_settings("2026-09") == {food.id: True}
    same(hd, pc)
    reset = hd.command("budgets.reset_carryover", category_id=key, month="2026-10")
    assert status(hd, reset)["status"] == "accepted"
    page = pc.command("budgets.save_month", month="2026-10", only_this_month=True,
                      lines=[dict(category=key, amount="900.00", average_months=None)])
    pc.sync_with(hd.home)
    assert status(hd, page)["status"] == "accepted"
    assert pc.c.budgets.amounts_for("2026-10")[pc.c.categories.get(food.id).id][0] == Decimal("900")
    clear = pc.command("budgets.set", category_id=key, month="2026-09", amount=None, only_this_month=False, average_months=None)
    pc.sync_with(hd.home)
    assert status(hd, clear)["status"] == "accepted"
    assert food.id not in pc.c.budgets.amounts_for("2026-09")
    same(hd, pc)


def test_instalment_purchase_and_early_loan_payment(devices):
    hd, pc = devices
    bank = uid(pc, "accounts", account(pc, "Bank").id)
    buy = pc.command("plans.buy_in_instalments", name="Laptop", price="1200.00", fee="0.00", months=12, first_date="2026-10-01",
                     account_id=bank, counterparty_id=None)
    pc.sync_with(hd.home)
    assert status(hd, buy)["status"] == "accepted"
    laptop = plan(pc, "Laptop")
    assert pc.c.planning.is_installment_purchase(laptop.id) and hd.c.planning.is_installment_purchase(plan(hd, "Laptop").id)
    same(hd, pc)
    record = unpack(buy)["body"]["record"]
    early = pc.command("plans.pay_loan_early", item_id=record, principal="200.00", fee="0.00", date_paid="2026-09-20",
                       account_id=bank, expected_remaining=f"{pc.c.planning.loan_progress(laptop)['still_to_pay']:.2f}")
    pc.sync_with(hd.home)
    assert status(hd, early)["status"] == "accepted"
    assert next(row for row in pc.balances() if row["name"] == "Bank")["balance"] == 800
    assert pc.c.planning.has_history(laptop.id) and hd.c.planning.has_history(plan(hd, "Laptop").id)
    same(hd, pc)


def test_concurrent_edit_of_one_plan_waits_for_review(devices):
    hd, pc = devices
    created = add_rent(hd)
    record = unpack(created)["body"]["record"]
    pc.sync_with(hd.home)
    item = plan(pc, "Rent")
    first = hd.command("plans.set_amount", item_id=record, amount="310.00")
    late = pc.command("plans.update", item_id=record, **edit_values(item, pc, name="Home rent"))  # Saw 300.
    pc.sync_with(hd.home)
    assert status(hd, first)["status"] == "accepted"
    assert status(hd, late) == dict(status="review", reason="conflict")
    assert [entry["state"] for entry in pc.pending_commands()] == ["Needs review"]
    state = hd.home.review_state(origin_id(unpack(late)["body"]["origin"]))
    hd.home.review(command_id=str(uuid4()), proposal_id=state["proposal_id"], token=state["token"], choice="apply")
    pc.sync_with(hd.home)
    assert plan(pc, "Home rent") and not pc.pending_commands()
    same(hd, pc)


def test_service_refusal_is_rejected_without_writing(devices):
    hd, pc = devices
    bad = add_rent(pc, amount="0.00")  # The planning service decides: an amount above zero is required.
    root = next(item for item in pc.c.categories.tree() if item.is_root)  # A budget needs a money-out category below it.
    refused_budget = pc.command("budgets.set", category_id=uid(pc, "categories", root.id), month="2026-09", amount="10.00",
                                only_this_month=False, average_months=None)
    pc.sync_with(hd.home)
    assert status(hd, bad) == dict(status="rejected", reason="financial-validation")
    assert status(hd, refused_budget) == dict(status="rejected", reason="financial-validation")
    assert not hd.c.planning.items(active_only=False) and not pc.c.planning.items(active_only=False)
    assert hd.c.db.scalar("SELECT COUNT(*) FROM budgets") == 0
    same(hd, pc)
    with pytest.raises(Exception, match="not covered"):
        pc.command("sms_imports.unknown_action", ending="1234", account_id=uid(pc, "accounts", account(pc, "Bank").id))


def test_delete_an_unpaid_instalment_plan_and_link_an_existing_payment(devices):
    hd, pc = devices
    buy = pc.command("plans.buy_in_instalments", name="Phone", price="600.00", fee="0.00", months=6, first_date="2026-10-01",
                     account_id=None, counterparty_id=None)
    record = unpack(buy)["body"]["record"]
    remove = pc.command("plans.remove", item_id=record)  # The terms row goes with the plan, on both devices.
    rent = add_rent(pc)
    pc.sync_with(hd.home)
    assert [status(hd, wire)["status"] for wire in (buy, remove, rent)] == ["accepted"] * 3
    assert not any(item.name == "Phone" for item in hd.c.planning.items(active_only=False))
    assert not hd.c.db.scalar("SELECT COUNT(*) FROM installment_purchases") and not pc.c.db.scalar("SELECT COUNT(*) FROM installment_purchases")
    same(hd, pc)
    # The amount needs a person’s review: outside automatic tolerance, within manual linking policy.
    spent = groups(pc, "-250.00")
    spent["money"]["date"] = "2026-09-05"
    pc.save(spent)
    pc.sync_with(hd.home)
    txn = pc.c.db.scalar("SELECT id FROM transactions ORDER BY id DESC LIMIT 1")
    link = pc.command("plans.link_payment", item_id=unpack(rent)["body"]["record"], due_date="2026-09-05",
                      transaction_id=uid(pc, "transactions", txn))
    pc.sync_with(hd.home)
    assert status(hd, link)["status"] == "accepted"
    assert pc.c.planning.linked_transaction_ids() == {txn} and len(hd.c.planning.linked_transaction_ids()) == 1
    same(hd, pc)


def test_move_room_and_fill_between_budgets(devices):
    hd, pc = devices
    food, other = category(pc), category(pc, "EXP.PERSONAL.TRANSPORT") if pc.c.categories.get_by_code("EXP.PERSONAL.TRANSPORT") else None
    keys = [uid(pc, "categories", item.id) for item in (food, other)]
    fill = pc.command("budgets.apply_fill", month="2026-09", lines=[
        dict(category=keys[0], amount="1000.00", average_months=None), dict(category=keys[1], amount="400.00", average_months=None)])
    move = pc.command("budgets.move_room", month="2026-09", to_id=keys[1], from_id=keys[0], amount="150.00")
    pc.sync_with(hd.home)
    assert status(hd, fill)["status"] == status(hd, move)["status"] == "accepted"
    amounts = hd.c.budgets.amounts_for("2026-09")
    assert (amounts[food.id][0], amounts[other.id][0]) == (Decimal("850"), Decimal("550")) == tuple(
        pc.c.budgets.amounts_for("2026-09")[item.id][0] for item in (food, other))
    percent = pc.command("budgets.set_income_percent", category_id=keys[0], month="2026-10", percent="12.50", only_this_month=False)
    pc.sync_with(hd.home)
    assert status(hd, percent)["status"] == "accepted"
    assert pc.c.budgets.amounts_for("2026-10")[food.id][3] == Decimal("12.5")
    same(hd, pc)
