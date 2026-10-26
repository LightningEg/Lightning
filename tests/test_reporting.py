"""Reporting and the core invariants: the net-worth equation must always reconcile."""

import random
from datetime import date, timedelta
from decimal import Decimal

from lightning.core.money import ZERO
from lightning.core.errors import ValidationError


def test_net_worth_by_account_and_class(setup, c):
    accounts, cats = setup
    c.transactions.record_transfer("2026-09-05", accounts["cib"].id, accounts["thndr"].id, "10000")
    nw = c.reporting.net_worth("2026-09-30")
    assert nw.total == Decimal("56200")  # 50,000 + 1,200 + 5,000
    groups = {g.code: g for g in nw.by_class}
    assert groups["CASH"].value == Decimal("51200")
    children = {ch.code: ch.value for ch in groups["CASH"].children}
    assert children == {"CASH.PHYSICAL": Decimal("1200"), "CASH.BANK": Decimal("40000"),
                        "CASH.BROKERAGE": Decimal("10000")}
    assert groups["DEPOSIT"].value == Decimal("5000")
    assert groups["CASH"].label == "Liquid Cash"
    assert "LIABILITY" not in groups


def test_transfers_do_not_change_net_worth_or_cash_flow(setup, c):
    accounts, _ = setup
    before = c.reporting.net_worth("2026-09-30").total
    c.transactions.record_transfer("2026-09-05", accounts["cib"].id, accounts["wallet"].id, "2000")
    c.transactions.record_transfer("2026-09-06", accounts["cib"].id, accounts["wallet"].id, "1000")
    assert c.reporting.net_worth("2026-09-30").total == before
    flow = c.reporting.cash_flow("2026-09-01", "2026-09-30")
    assert flow.inflows == ZERO and flow.outflows == ZERO


def test_dated_reserve_assignments_allow_negative_spendable_cash_and_reject_unknown_past(setup, c):
    accounts, _ = setup
    c.money_from_others.record("2026-09-10", "Dad", accounts["cib"].id, "10000")
    reserve = c.reserves.create("Travel", "50000")
    c.reserves.allocate(reserve["id"], "42000")

    assert c.reporting.owned_liquid_cash("2026-12-31") == Decimal("41200")
    assert c.reserves.allocation_at("2026-09-30") is None
    assigned = c.reserves.allocation_at("2026-12-31")
    assert assigned == Decimal("42000")
    assert c.reporting.owned_liquid_cash("2026-12-31") - assigned == Decimal("-800")


def test_money_from_others_is_deducted_and_reconciles_bridge(setup, c):
    accounts, cats = setup
    before = c.reporting.net_worth("2026-09-19").total
    c.transactions.record_inflow("2026-09-20", accounts["cib"].id, "1000", cats["EXP.WORK.SALARY"].id)
    c.money_from_others.record("2026-09-20", "Dad", accounts["cib"].id, Decimal("1000"))
    nw = c.reporting.net_worth("2026-09-30")
    assert nw.total == before
    assert sum((group.value for group in nw.by_class), Decimal("0")) == nw.total
    bridge = c.reporting.bridge("2026-09-20", "2026-09-30")
    # Owner-tagged ledger activity must be included before the separate custody
    # adjustment removes the portion that is not household-owned.
    assert bridge.inflows == Decimal("1000")
    assert bridge.custody_change == Decimal("-1000")
    assert bridge.difference == 0


def test_sidebar_separates_gross_account_balances_from_what_you_own(setup, c):
    accounts, cats = setup
    c.transactions.record_inflow("2026-09-20", accounts["cib"].id, "1000", cats["EXP.WORK.SALARY"].id)
    c.money_from_others.record("2026-09-20", "Dad", accounts["cib"].id, Decimal("1000"))

    all_accounts, owned, groups = c.reporting.sidebar("2026-09-30")

    assert all_accounts == Decimal("57200")
    assert owned == Decimal("56200")
    assert all_accounts - owned == Decimal("1000")
    assert sum((group.value for group in groups), ZERO) == all_accounts
    assert all(group.code != "CUSTODY" for group in groups)


def test_bridge_example(setup, c):
    accounts, cats = setup
    c.transactions.record_inflow("2026-10-01", accounts["cib"].id, "20000", cats["EXP.WORK.SALARY"].id)
    c.transactions.record_outflow("2026-10-03", accounts["cib"].id, "12000", cats["EXP.PERSONAL.FOOD"].id)
    c.transactions.record_transfer("2026-10-04", accounts["cib"].id, accounts["thndr"].id, "5000")
    b = c.reporting.bridge_for_month("2026-10")
    assert b.opening == Decimal("56200")
    assert b.inflows == Decimal("20000") and b.outflows == Decimal("12000")
    assert b.revaluation == ZERO and b.new_balances == ZERO
    assert b.closing == Decimal("64200") and b.difference == ZERO


def test_new_account_mid_month_is_its_own_bridge_line(setup, c):
    c.account_flows.open_account("NBE", "BANK", "2026-09-15", "7000")
    b = c.reporting.bridge_for_month("2026-09")
    assert b.new_balances == Decimal("63200") and b.inflows == ZERO and b.difference == ZERO


def test_cash_flow_splits(setup, c):
    accounts, cats = setup
    c.transactions.record_inflow("2026-09-10", accounts["cib"].id, "30000", cats["EXP.WORK.SALARY"].id)
    c.transactions.record_inflow("2026-09-11", accounts["cib"].id, "500", cats["EXP.INVEST.INTEREST"].id)
    c.transactions.record_outflow("2026-09-12", accounts["cib"].id, "300", cats["EXP.WORK.SOFTWARE"].id)
    c.transactions.record_outflow("2026-09-12", accounts["cib"].id, "700", cats["EXP.PERSONAL.FOOD"].id)
    f = c.reporting.cash_flow("2026-09-01", "2026-09-30")
    assert (f.household_inflows, f.investment_inflows) == (Decimal("30000"), Decimal("500"))
    assert (f.personal_outflows, f.work_outflows) == (Decimal("700"), Decimal("300"))
    assert f.net == Decimal("29500")
    spending = {g.code: g.value for g in c.reporting.spending_by_category("2026-09-01", "2026-09-30")}
    assert spending == {"EXP.PERSONAL.FOOD": Decimal("700"), "EXP.WORK.SOFTWARE": Decimal("300")}
    by_scope = {g.code: g.value for g in c.reporting.spending_by_category("2026-09-01", "2026-09-30", depth=1)}
    assert by_scope == {"EXP.PERSONAL": Decimal("700"), "EXP.WORK": Decimal("300")}


def test_statement_running_balance(setup, c):
    accounts, cats = setup
    c.transactions.record_outflow("2026-09-10", accounts["cib"].id, "100", cats["EXP.PERSONAL.FOOD"].id)
    c.transactions.record_inflow("2026-09-11", accounts["cib"].id, "40", cats["EXP.WORK.SALARY"].id)
    s = c.reporting.statement(accounts["cib"].id, "2026-09-05", "2026-09-30")
    assert s.opening == Decimal("50000")
    assert [r.balance for r in s.rows] == [Decimal("49900"), Decimal("49940")]
    assert s.closing == Decimal("49940")


def test_monthly_trend(setup, c):
    accounts, cats = setup
    c.transactions.record_inflow("2026-09-20", accounts["cib"].id, "100", cats["EXP.WORK.SALARY"].id)
    trend = c.reporting.monthly_trend("2026-10", 3)
    assert [m["month"] for m in trend] == ["2026-08", "2026-09", "2026-10"]
    assert trend[1]["inflows"] == Decimal("100")


def test_randomized_ledger_always_reconciles(c):
    """Random mix of accounts, money in/out, transfers, edits and voids.

    After every step: internal lines net to zero, balances rebuild from the ledger,
    and the net-worth equation closes to exactly 0.00 for every month.
    """
    rng = random.Random(20260925)
    flows = c.account_flows
    accs = [flows.open_account(f"Acc {i}", t, "2026-01-01",
                               "0" if t == "DEPOSIT" else str(rng.randint(0, 50000)))
            for i, t in enumerate(["BANK", "CASH", "DEPOSIT", "BROKERAGE", "OTHER_ASSET"])]
    from lightning.categories.domain import Movement
    ins = c.categories.pickable(Movement.INFLOW)
    outs = c.categories.pickable(Movement.OUTFLOW)
    made = []
    expected = {a.id: c.reporting.account_balance(a.id) for a in accs}
    for step in range(300):
        day = (date(2026, 1, 1) + timedelta(days=step * 181 // 300)).isoformat()
        amount = Decimal(rng.randint(1, 500000)) / 100
        a, b = rng.sample(accs, 2)
        roll = rng.random()
        if roll < 0.35:
            if c.reporting.account_balance(a.id, day) < amount:
                continue
            try:
                t = c.transactions.record_outflow(day, a.id, amount, rng.choice(outs).id)
            except ValidationError:
                continue
            expected[a.id] -= amount
        elif roll < 0.6:
            try:
                t = c.transactions.record_inflow(day, a.id, amount, rng.choice(ins).id)
            except ValidationError:
                continue
            expected[a.id] += amount
        elif roll < 0.85:
            if c.reporting.account_balance(a.id, day) < amount:
                continue
            try:
                t = c.transactions.record_transfer(day, a.id, b.id, amount)
            except ValidationError:
                continue
            expected[a.id] -= amount
            expected[b.id] += amount
        elif made and roll < 0.93:
            victim = c.transactions.get(rng.choice(made))
            if not victim.is_void:
                for line in victim.lines:
                    expected[line.account_id] -= line.quantity
                c.transactions.void(victim.id)
            continue
        elif made:
            victim = c.transactions.get(rng.choice(made))
            if victim.is_void or victim.type.value == "TRF":
                continue
            after_removing = c.reporting.account_balance(a.id, day) - sum(
                (line.quantity for line in victim.lines if line.account_id == a.id and line.date <= day), ZERO)
            if victim.type.value == "OUT" and after_removing < amount:
                continue
            for line in victim.lines:
                expected[line.account_id] -= line.quantity
            try:
                edited = c.transactions.update_money(victim.id, day, a.id, amount, rng.choice(
                    ins if victim.type.value == "IN" else outs).id)
            except ValidationError:
                for line in victim.lines:
                    expected[line.account_id] += line.quantity
                continue
            expected[a.id] += edited.lines[0].quantity
            continue
        else:
            continue
        made.append(t.id)

    for a in accs:
        assert c.reporting.account_balance(a.id) == expected[a.id], a.label
    internal = c.db.scalar(
        "SELECT SUM(le.amount_base_e6) FROM ledger_entries le JOIN transactions t ON t.id = le.transaction_id"
        " WHERE le.effect = 'INTERNAL' AND t.status = 'POSTED'")
    assert (internal or 0) == 0
    for month in ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]:
        b = c.reporting.bridge_for_month(month)
        assert b.difference == ZERO, month
        assert b.revaluation == ZERO
    total = c.reporting.bridge("2026-01-01", "2026-06-30")
    assert total.closing == sum(expected.values())
