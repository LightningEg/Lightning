from decimal import Decimal

import pytest

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app
from screens import _ScreenClient


def _food(c):
    return c.categories.get_by_code("EXP.PERSONAL.FOOD")


def _proposal(c, source, month="2026-12"):
    return c.budgets.fill_proposal(month, source, schedule=c.schedules.view())


def test_last_month_copies_base_limit_without_spending_or_carryover(c, setup):
    accounts, _ = setup
    food = _food(c)
    c.budgets.set_budget(food.id, "2026-11", "4000", schedule=c.schedules.view())
    c.transactions.record_outflow("2026-11-12", accounts["cib"].id, "6500", food.id)
    c.budgets.set_carryover("2026-12", {food.id: True}, schedule=c.schedules.view())
    c.budgets.set_budget(food.id, "2026-12", "7000", only_this_month=True, schedule=c.schedules.view())

    row = next(row for row in _proposal(c, "last_month").rows if row.category_id == food.id)

    assert row.amount == Decimal("4000")
    assert row.current_amount == Decimal("7000")
    assert "Current limit" in row.conflict
    assert not row.selected
    assert "From 2026-11" in row.note


def test_last_month_identifies_repeated_amounts_already_in_use(c, setup):
    food = _food(c)
    c.budgets.set_budget(food.id, "2026-10", "4000", schedule=c.schedules.view())

    row = next(row for row in _proposal(c, "last_month", "2026-11").rows if row.category_id == food.id)

    assert row.amount == row.current_amount == Decimal("4000")
    assert row.already_using_last_month
    assert row.conflict == "Already using last month's plan"
    assert not row.selected


def test_average_source_uses_three_full_months_and_one_month_of_history(c, setup):
    accounts, _ = setup
    food = _food(c)
    for month, amount in (("2026-09", "3000"), ("2026-10", "4000"), ("2026-11", "5200")):
        c.transactions.record_outflow(f"{month}-12", accounts["cib"].id, amount, food.id)
    c.budgets.set_budget(food.id, "2026-12", "1000", only_this_month=True, schedule=c.schedules.view())

    row = next(row for row in _proposal(c, "average").rows if row.category_id == food.id)

    assert row.amount == Decimal("4100")  # 4,066.67 shown as a tidy figure
    assert row.source == "Your average" and row.current_amount == Decimal("1000")
    assert row.selected and "3 months" in row.note

    # Only one month of history: that month is the figure.
    other = c.categories.get_by_code("EXP.PERSONAL.TRANSPORT")
    c.transactions.record_outflow("2026-11-03", accounts["cib"].id, "900", other.id)
    row = next(row for row in _proposal(c, "average").rows if row.category_id == other.id)
    assert row.amount == Decimal("900")


def test_average_source_skips_one_off_categories(c, setup):
    accounts, _ = setup
    food = _food(c)
    c.transactions.record_outflow("2026-11-12", accounts["cib"].id, "5000", food.id)
    c.budgets.set_one_off(food.id, True)
    assert all(row.category_id != food.id for row in _proposal(c, "average").rows)


def test_schedule_sums_bills_and_subscriptions_but_excludes_skips_and_loans(c, setup):
    accounts, _ = setup
    food = _food(c)
    bill = c.planning.create(kind="BILL", name="Electricity", amount="650", frequency="ONCE",
                             start_date="2026-12-20", category_id=food.id)
    c.planning.create(kind="SUBSCRIPTION", name="Gym", amount="120", frequency="MONTHLY",
                      start_date="2026-12-20", category_id=food.id)
    c.planning.create(kind="LOAN", name="Car loan", amount="2500", frequency="MONTHLY",
                      start_date="2026-12-20", category_id=food.id, payment_count="4")
    c.planning.skip(bill, "2026-12-20")

    row = next(row for row in _proposal(c, "schedule").rows if row.category_id == food.id)

    assert row.amount == Decimal("120")
    assert "Car loan" not in row.note and "Electricity" not in row.note
    assert "2,620" in row.conflict  # the loan and the gym are both planned automatically (2026-10-05)
    assert not row.selected


def test_goal_source_is_informational_and_never_a_spending_category(c, setup):
    c.reserves.create("School fees", "12000", "PROJECT", due_date="2027-12-31")

    proposal = _proposal(c, "goal")

    assert len(proposal.rows) == 1
    row = proposal.rows[0]
    assert row.category_id is None
    # October 2026 through the December 2027 deadline is 13 monthly set-asides.
    assert row.amount == Decimal("923.08")
    assert not row.selectable and not row.selected
    assert "Reserves" in row.conflict

    with pytest.raises(ValidationError, match="at least one category"):
        c.budgets.apply_fill("2026-12", {}, schedule=c.schedules.view())


def test_parent_ceiling_conflict_is_shown_without_changing_the_ceiling(c, setup):
    food = _food(c)
    transport = c.categories.get_by_code("EXP.PERSONAL.TRANSPORT")
    personal = c.categories.get_by_code("EXP.PERSONAL")
    c.budgets.set_budget(personal.id, "2026-12", "500", schedule=c.schedules.view())
    c.planning.create(kind="BILL", name="Food box", amount="400", frequency="ONCE",
                      start_date="2026-12-20", category_id=food.id)
    c.planning.create(kind="BILL", name="Taxi pass", amount="200", frequency="ONCE",
                      start_date="2026-12-20", category_id=transport.id)

    rows = _proposal(c, "schedule").rows
    food_row = next(row for row in rows if row.category_id == food.id)
    transport_row = next(row for row in rows if row.category_id == transport.id)

    assert "above the Personal ceiling of 500" in food_row.conflict
    assert "above the Personal ceiling of 500" in transport_row.conflict
    assert not food_row.selected and not transport_row.selected
    assert c.budgets.amounts_for("2026-12", loans=False, schedule=c.schedules.view())[personal.id][0] == Decimal("500")


def test_apply_fill_changes_selected_month_only(c, setup):
    food = _food(c)
    c.budgets.set_budget(food.id, "2026-11", "4000", schedule=c.schedules.view())

    assert c.budgets.apply_fill("2026-12", {food.id: "5200"}, schedule=c.schedules.view()) == 1

    dec = c.budgets.amounts_for("2026-12", loans=False, schedule=c.schedules.view())[food.id]
    jan = c.budgets.amounts_for("2027-01", loans=False, schedule=c.schedules.view())[food.id]
    assert dec[0] == Decimal("5200") and dec[1] is True
    assert jan[0] == Decimal("4000") and jan[1] is False


def test_apply_fill_rolls_back_every_category_on_error(c, setup, monkeypatch):
    food = _food(c)
    transport = c.categories.get_by_code("EXP.PERSONAL.TRANSPORT")
    original = c.budgets.repo.upsert
    calls = 0

    def fail_on_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated write failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(c.budgets.repo, "upsert", fail_on_second)
    with pytest.raises(RuntimeError, match="simulated write failure"):
        c.budgets.apply_fill("2026-12", {food.id: "1000", transport.id: "500"}, schedule=c.schedules.view())

    assert all(c.budgets.amounts_for("2026-12", loans=False, schedule=c.schedules.view()).get(cid) is None
               for cid in (food.id, transport.id))


def test_budget_fill_screen_reviews_and_posts_month_only_edits(c, setup):
    food = _food(c)
    c.budgets.set_budget(food.id, "2026-11", "4000", schedule=c.schedules.view())
    c.budgets.set_budget(food.id, "2026-12", "7000", only_this_month=True, schedule=c.schedules.view())
    client = _ScreenClient(create_app(c), base_url="http://testserver")

    preview = client.get("/budget/fill?month=2026-12&source=last_month")
    assert preview.status_code == 200
    assert "Already using last month's plan" not in preview.text
    assert 'value="4000.00"' in preview.text
    assert "Current limit: 7,000.00 fixed" in preview.text

    response = client.post("/budget/fill?month=2026-12", data={
        "source": "last_month", "selected": str(food.id), f"amount_{food.id}": "5200",
    })

    assert "Applied 1 budget for 2026-12 only" in response.text
    assert c.budgets.amounts_for("2026-12", loans=False, schedule=c.schedules.view())[food.id][0] == Decimal("5200")
    assert c.budgets.amounts_for("2027-01", loans=False, schedule=c.schedules.view())[food.id][0] == Decimal("4000")
