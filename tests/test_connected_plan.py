"""The parts of the plan talk to each other (owner request 2026-10-05): the savings target set in
Financial health limits the budget, dated goals count in what a month must leave, and the budget,
Needs you, Financial health and Reserves read one check (HealthService.plan_check)."""
import shutil
from decimal import Decimal

from lightning.core.dates import today
from lightning.database import migrator
from lightning.database.connection import Database
from lightning.ui.web import create_app
from lightning.workflows.review import ReviewInbox
from tests.screens import _ScreenClient, visible_text

MONTH = "2026-12"  # conftest pins today to 2026-12-31


def _plan(c, spend: str, fund: str = "60000"):
    """Income 10,000 a month; the emergency fund full (six months) unless the test says otherwise."""
    c.budgets.set_emergency_basis("income")  # this scenario explicitly uses six months of salary
    c.settings.set("budget_manual_monthly_income", "10000")
    if fund:
        c.reserves.set_emergency_fund(fund)
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    c.budgets.set_budget(food, MONTH, spend)


def test_a_plan_that_leaves_the_savings_target_passes(c):
    _plan(c, "8000")
    check = c.health.plan_check(MONTH)
    assert (check.income, check.planned, check.target_percent) == (Decimal("10000"), Decimal("8000"), Decimal("20"))
    assert check.savings_target == Decimal("2000.00") and check.spending_room == Decimal("8000.00")
    assert check.plan_saves == Decimal("2000") and check.planned_savings_rate == Decimal("20")
    assert check.over_by == 0


def test_a_plan_that_spends_into_the_savings_target_says_how_much_to_cut(c):
    _plan(c, "9000")
    check = c.health.plan_check(MONTH)
    assert check.planned_savings_rate == Decimal("10") and check.over_by == Decimal("1000.00")
    assert check.short_for == "target"
    c.health.set_limit("savings_rate", "5")  # a lower target makes the same plan fine
    assert c.health.plan_check(MONTH).over_by == 0


def test_dated_goals_raise_what_the_month_must_leave(c):
    _plan(c, "8000")
    c.reserves.create("New laptop", "3000", due_date="2026-12-31")  # 3,000 still needed this month
    check = c.health.plan_check(MONTH)
    assert check.goals == Decimal("3000.00") and check.short_for == "goals"
    assert check.to_save == Decimal("3000.00") and check.over_by == Decimal("1000.00")


def test_no_income_or_no_plan_means_no_check(c):
    check = c.health.plan_check(MONTH)
    assert check.planned is None and check.over_by == 0
    assert c.health.plan_check(MONTH).planned_savings_rate is None


def test_screens_share_the_one_check(c):
    _plan(c, "9000")
    c.reserves.create("New laptop", "1200", due_date="2027-11-30")  # 100 a month over 12 months
    browser = _ScreenClient(create_app(c), "http://testserver")
    budget = visible_text(browser.get(f"/budget?period=month&month={MONTH}").text)
    # The Plan leaves to save card (guideline 3.32 A08): the figure, its comparison with the target, Watch, the way out.
    assert "Plan leaves to save Watch 1,000 EGP 10% of income, target 20%" in budget
    assert "Plan 1,000 less to keep 2,000 a month" in budget
    inbox = {item["label"]: item for item in ReviewInbox(c).items(today())}
    item = inbox["This month's plan is below your savings target"]
    assert item["href"] == f"/budget?month={MONTH}" and "Plan 1,000 EGP less" in item["detail"]
    health = visible_text(browser.get("/financial-health").text)
    assert "Planned savings rate" in health and "10.0%" in health
    reserves = visible_text(browser.get("/reserves").text)
    assert "About 100 EGP a month" in reserves


def test_budget_settings_point_to_the_savings_target_instead_of_a_ceiling(c):
    browser = _ScreenClient(create_app(c), "http://testserver")
    page = browser.get("/settings?section=budget").text
    assert "ceiling_percent" not in page  # the savings target, behind Health's gear, sets Most you can plan
    assert "suggestion_percent" not in page and "carryover_month" not in page  # defaults now (owner, 2026-10-06)


def test_migration_0042_keeps_a_custom_ceiling_as_the_savings_target(monkeypatch, tmp_path):
    before = tmp_path / "migrations"
    before.mkdir()
    for path in sorted(migrator._BUNDLED_MIGRATIONS_DIR.glob("*.sql")):
        if int(path.name[:4]) <= 41:
            shutil.copy(path, before / path.name)
    db = Database(":memory:")
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", before)
    migrator.migrate(db)
    db.execute("INSERT INTO settings(key,value,updated_at) VALUES ('budget_monthly_ceiling_percent','72.5','2026-10-01')")
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", migrator._BUNDLED_MIGRATIONS_DIR)
    assert migrator.migrate(db)[0] == "0042_savings_target_from_ceiling (APPLIED)"  # later migrations follow it
    assert db.scalar("SELECT value FROM settings WHERE key='financial_health_limit_savings_rate'") == "27.5"
    assert db.scalar("SELECT COUNT(*) FROM settings WHERE key='budget_monthly_ceiling_percent'") == 0


def test_bills_and_subscriptions_are_planned_like_loans_until_you_set_your_own(c):
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    c.planning.create(kind="SUBSCRIPTION", name="Gym", amount="120", frequency="MONTHLY",
                      start_date="2026-12-20", category_id=food)
    line = next(l for s in c.budgets.month_view(MONTH).sections for l in s.lines if l.category_id == food)
    assert line.budget == Decimal("120") and line.from_bills and not line.from_loans
    assert c.budgets.bill_lines(MONTH) == {food: Decimal("120")}
    c.budgets.set_budget(food, MONTH, "3000")  # your own amount replaces the automatic line
    assert c.budgets.bill_lines(MONTH) == {}


def test_an_emergency_fund_below_six_months_adds_its_top_up(c):
    _plan(c, "8000", fund="12000")  # 12,000 of a 60,000 target: 48,000 over 24 months
    check = c.health.plan_check(MONTH)
    assert check.emergency == Decimal("2000.00") and check.needs == Decimal("2000.00")
    assert check.over_by == 0  # the 20% target already leaves 2,000
    c.reserves.create("New laptop", "500", due_date="2026-12-31")
    check = c.health.plan_check(MONTH)
    assert check.short_for == "goals" and check.over_by == Decimal("500.00")
    assert check.needs_label == "your goals and emergency fund need"


def test_fill_this_month_stops_at_most_you_can_plan(c):
    c.settings.set("budget_manual_monthly_income", "10000")
    c.reserves.set_emergency_fund("60000")
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    transport = c.categories.get_by_code("EXP.PERSONAL.TRANSPORT").id
    c.budgets.set_budget(food, "2026-11", "9000", only_this_month=True)
    c.budgets.set_budget(transport, "2026-11", "1000", only_this_month=True)
    proposal, left = c.health.fit_fill(c.budgets.fill_proposal(MONTH, "last_month"))
    rows = {row.category_id: row for row in proposal.rows}
    assert not rows[food].selected and "Past Most you can plan: 8,000 of room left." in rows[food].conflict
    assert rows[transport].selected and left == Decimal("7000.00")
    page = visible_text(_ScreenClient(create_app(c), "http://testserver").get(f"/budget/fill?month={MONTH}").text)
    assert "Most you can plan 8,000 EGP, to leave 2,000 to save." in page


def test_saving_a_bill_or_loan_says_where_your_limits_stand(c):
    c.settings.set("budget_manual_monthly_income", "10000")
    c.planning.create(kind="BILL", name="Rent", amount="4500", frequency="MONTHLY", start_date="2027-01-01")
    assert c.health.commitments_note("BILL") == "Fixed costs to income is now 45%, within your 50% limit."
    c.planning.create(kind="LOAN", name="Car loan", amount="2500", frequency="MONTHLY",
                      start_date="2027-01-01", payment_count="12")
    assert c.health.commitments_note("LOAN") == ("Fixed costs to income is now 70%, above your 50% limit; "
                                                 "Loan payments to income is now 25%, above your 20% limit.")
    assert c.health.commitments_note("INCOME") == ""
    browser = _ScreenClient(create_app(c), "http://testserver")
    form = browser.get("/plan/items/new?kind=SUBSCRIPTION")
    assert form.status_code == 200


# ---- More of the plan connected (owner request 2026-10-05: "make things smart")

def test_safe_to_spend_and_the_forecast_keep_the_emergency_top_up(c):
    # The budget asks each month to leave the fund's top-up; the forecast and Safe to spend hold it back too.
    _plan(c, "8000", fund="12000")  # 48,000 short of 60,000: 2,000 a month
    f = c.forecaster.forecast(today())
    assert [m.emergency_saving for m in f.months] == [Decimal("2000.00")] * 3
    assert all(m.money_out == m.commitments + m.budget_spending + m.goal_saving + m.emergency_saving for m in f.months)
    parts = dict(f.safe_to_spend_parts)
    assert parts["Emergency fund top-up"] == Decimal("-2000.00")
    assert f.safe_to_spend == f.free_cash + sum(v for k, v in parts.items() if k != "Free cash")
    c.reserves.set_emergency_fund("60000")  # a full fund needs nothing
    assert "Emergency fund top-up" not in dict(c.forecaster.forecast(today()).safe_to_spend_parts)


def test_recurring_income_stands_in_until_a_month_has_income(c):
    # A new profile with its salary set up in Recurring gets a checked plan from the first day.
    c.budgets.set_emergency_basis("income")  # the optional salary-based cushion works before spending history
    assert c.budgets.income_average(MONTH).amount is None
    c.planning.create(kind="INCOME", name="Salary", amount="12000", frequency="MONTHLY", start_date="2027-01-01")
    average = c.budgets.income_average(MONTH)
    assert (average.amount, average.scheduled, average.window) == (Decimal("12000.00"), True, "from your recurring income")
    c.reserves.set_emergency_fund("72000")
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    c.budgets.set_budget(food, MONTH, "11000")
    assert c.health.plan_check(MONTH).over_by == Decimal("1400.00")  # 20% of 12,000 is 2,400; the plan leaves 1,000
    page = visible_text(_ScreenClient(create_app(c), "http://testserver").get("/plan/reserves").text)
    assert "From your recurring income" in page


def test_saving_the_target_or_a_goal_says_what_it_does_to_the_plan(c):
    _plan(c, "8000")
    assert c.health.plan_note() == "Most you can plan this month is now 8,000; this month's plan fits."
    c.health.set_limit("savings_rate", "30")
    assert c.health.plan_note() == "Most you can plan this month is now 7,000; this month's plan is 1,000 over it."
    c.planning.create(kind="BILL", name="Rent", amount="7500", frequency="MONTHLY", start_date="2027-01-01")
    assert c.health.plan_note().endswith("Bills and loan payments alone come to 7,500 a month, more than that.")
    c.reserves.create("Wedding", "20000", due_date="2026-12-31")
    assert c.health.plan_note() == ("Saving needed is now 20,000 a month, all of your income: "
                                    "give a goal a later date or a smaller target.")
    browser = _ScreenClient(create_app(c), "http://testserver")
    page = visible_text(browser.post("/settings/financial-health-limit",
                                     data={"key": "savings_rate", "value": "25", "action": "save"}).text)
    assert "Financial health limit saved. Saving needed is now 20,000 a month" in page
    page = visible_text(browser.post("/reserves", data={"name": "Phone", "target": "600",
                                                        "due_date": "2027-05-31"}).text)
    assert "Created Phone. Saving needed is now" in page


def test_needs_you_names_a_category_planned_below_its_bills(c):
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    c.planning.create(kind="BILL", name="Groceries box", amount="900", frequency="MONTHLY",
                      start_date="2026-12-20", category_id=food)
    assert c.budgets.below_scheduled(MONTH) == []  # no rule of its own: the bill plans the category
    c.budgets.set_budget(food, MONTH, "500")
    assert c.budgets.below_scheduled(MONTH) == [{"category_id": food, "name": "Food & Groceries", "planned": Decimal("500"),
                                                 "scheduled": Decimal("900")}]
    inbox = {item["label"]: item for item in ReviewInbox(c).items(today())}
    item = inbox["Food & Groceries is planned below its bills"]
    assert item["detail"] == "Planned 500 EGP; bills and loan payments scheduled this month come to 900."
    assert item["href"] == f"/budget?month={MONTH}"
    c.budgets.set_budget(food, MONTH, "900")
    assert c.budgets.below_scheduled(MONTH) == []


# ---- The smarter plan, all of it (owner, 2026-10-05: "do them all")

def test_safe_to_spend_keeps_the_rest_of_the_savings_target(c):
    _plan(c, "8000")  # the fund is full and no goal is dated: the 20% target (2,000) is what is kept back
    f = c.forecaster.forecast(today())
    assert [m.target_saving for m in f.months] == [Decimal("2000.00")] * 3
    parts = dict(f.safe_to_spend_parts)
    assert parts["Rest of savings target"] == Decimal("-2000.00")
    assert f.safe_to_spend == f.free_cash + sum(v for k, v in parts.items() if k != "Free cash")
    c.reserves.create("New laptop", "3000", due_date="2026-12-31")  # a goal larger than the target replaces it
    december = c.forecaster.forecast(today()).months[0]
    assert (december.goal_saving, december.target_saving) == (Decimal("3000.00"), 0)


def test_a_goal_the_plan_cannot_reach_says_when_it_can(c):
    _plan(c, "9000")  # the plan leaves 1,000 a month
    c.reserves.create("Car deposit", "6000", due_date="2027-02-28")  # 2,000 a month for three months
    [late] = c.health.goal_reach()
    assert (late["need"], late["can"], late["reached"]) == (Decimal("2000.00"), Decimal("1000"), "2027-05")
    inbox = {item["label"]: item for item in ReviewInbox(c).items(today())}
    item = inbox["Car deposit will not be ready by its date"]
    assert "leaves 1,000 for it. Setting aside 1,000 a month, it is ready in May 2027." in item["detail"]
    page = visible_text(_ScreenClient(create_app(c), "http://testserver").get("/plan/reserves").text)
    assert "Your plan leaves 1,000 a month for it: set that aside each month and it is ready in 2027-05" in page
    c.budgets.set_budget(c.categories.get_by_code("EXP.PERSONAL.FOOD").id, MONTH, "7000")
    assert c.health.goal_reach() == []


def _salaried(c, setup):
    """Salary 30,000 for September to November; Food planned 5,000 but 6,000 spent in October and November;
    Transport planned 3,000 with 500 spent; the emergency fund full."""
    accounts, cats = setup
    cib = accounts["cib"].id
    food, transport = cats["EXP.PERSONAL.FOOD"].id, c.categories.get_by_code("EXP.PERSONAL.TRANSPORT").id
    for month in ("09", "10", "11"):
        c.transactions.record_inflow(f"2026-{month}-01", cib, "30,000", cats["EXP.WORK.SALARY"].id)
    for month in ("10", "11"):
        c.transactions.record_outflow(f"2026-{month}-15", cib, "6,000", food)
        c.transactions.record_outflow(f"2026-{month}-16", cib, "500", transport)
    c.budgets.set_budget(food, "2026-10", "5000")
    c.budgets.set_budget(transport, "2026-10", "3000")
    c.reserves.set_emergency_fund("180000")
    return food, transport


def test_a_raise_in_recurring_is_offered_to_the_plan(c, setup):
    _salaried(c, setup)
    assert c.health.raise_offer() is None  # no recurring income yet
    c.planning.create(kind="INCOME", name="Salary", amount="36000", frequency="MONTHLY", start_date="2027-01-01",
                      category_id=setup[1]["EXP.WORK.SALARY"].id)
    offer = c.health.raise_offer()
    assert (offer["average"], offer["raise"], offer["room"], offer["keep_rate"]) == (
        Decimal("30000.00"), Decimal("6000.00"), Decimal("28800.00"), Decimal("33.3"))
    inbox = {item["label"]: item for item in ReviewInbox(c).items(today())}
    assert inbox["Your income went up"]["popup"] and inbox["Your income went up"]["href"] == f"/budget/raise?month={MONTH}"
    browser = _ScreenClient(create_app(c), "http://testserver")
    assert "Save the difference" in visible_text(browser.get(f"/budget/raise?month={MONTH}").text)
    budget = visible_text(browser.get(f"/budget?month={MONTH}").text)
    # On the Plan leaves to save card (guideline 3.32 A08.5: no key note in a row of its own); its popup offers both choices.
    assert "Income up 6,000 Raise the plan" in budget
    page = visible_text(browser.post("/budget/raise", data={"month": MONTH, "choice": "save"}).text)
    assert "Savings target raised to 33.3%" in page and c.health.limit_values()["savings_rate"] == Decimal("33.3")
    assert c.health.take_raise("plan").startswith("The plan now counts your recurring income, 36,000")
    average = c.budgets.income_average(MONTH)
    assert (average.amount, average.scheduled) == (Decimal("36000.00"), True) and c.health.raise_offer() is None
    assert "income_from_recurring\" value=\"1\" checked" in browser.get("/settings?section=budget").text


def test_a_yearly_bonus_is_not_read_as_a_raise(c, setup):
    """7L1: 30,000 a month plus a yearly 30,000 bonus spreads to 35,500 over twelve months, with a 9,000 quarterly share: not a raise."""
    _salaried(c, setup)
    cats = setup[1]
    c.planning.create(kind="INCOME", name="Salary", amount="30000", frequency="MONTHLY", start_date="2027-01-01",
                      category_id=cats["EXP.WORK.SALARY"].id)
    c.planning.create(kind="INCOME", name="Annual bonus", amount="30000", frequency="YEARLY", start_date="2027-03-01",
                      category_id=c.categories.get_by_code("EXP.WORK.BONUS").id)
    c.planning.create(kind="INCOME", name="Profit share", amount="9000", frequency="QUARTERLY",
                      start_date="2027-03-01")
    assert c.planning.income_a_month() == Decimal("35500.00")  # the plan's own total still spreads the lumps
    assert c.health.raise_offer() is None
    assert "Your income went up" not in {item["label"] for item in ReviewInbox(c).items(today())}
    # A real raise in the monthly pay is still offered, at the monthly figure only.
    c.planning.create(kind="INCOME", name="Second job", amount="6000", frequency="MONTHLY", start_date="2027-01-01")
    assert c.health.raise_offer()["recurring"] == Decimal("36000.00")


def test_a_declined_raise_is_not_offered_again_until_the_amount_changes(c, setup):
    _salaried(c, setup)
    c.planning.create(kind="INCOME", name="Salary", amount="36000", frequency="MONTHLY", start_date="2027-01-01")
    assert c.health.take_raise("keep") == "The plan keeps counting your average income."
    assert c.health.raise_offer() is None
    c.planning.create(kind="INCOME", name="Bonus", amount="3000", frequency="MONTHLY", start_date="2027-01-01")
    assert c.health.raise_offer()["recurring"] == Decimal("39000.00")


def test_a_month_that_saved_less_than_the_target_is_in_needs_you(c, setup):
    _salaried(c, setup)  # November: 30,000 in, 6,500 out, 78% saved
    assert c.health.short_month() is None
    c.health.set_limit("savings_rate", "80")
    short = c.health.short_month()
    assert (short["month"], short["short"]) == ("2026-11", Decimal("500.00"))
    item = {i["label"]: i for i in ReviewInbox(c).items(today())}["November 2026 saved less than your target"]
    assert item["detail"].startswith("It saved 78% of money in; your target is 80%, 500 EGP more.")


def test_over_plan_two_months_running_offers_to_move_room(c, setup):
    food, transport = _salaried(c, setup)
    [row] = c.budgets.over_twice(MONTH)
    assert (row["category_id"], row["amount"], row["from_id"]) == (food, Decimal("1000"), transport)
    item = {i["label"]: i for i in ReviewInbox(c).items(today())}["Food & Groceries over plan two months running"]
    assert "Over its plan in October and November, by up to 1,000 EGP. Move 1,000 from Transportation" in item["detail"]
    browser = _ScreenClient(create_app(c), "http://testserver")
    assert "Food & Groceries 5,000 → 6,000" in visible_text(browser.get(item["href"]).text)
    browser.post("/budget/move", data={"month": MONTH, "to": food, "from": transport, "amount": "1000"})
    plans = c.budgets.amounts_for(MONTH, loans=False)
    assert (plans[food][0], plans[transport][0]) == (Decimal("6000"), Decimal("2000"))
    assert c.budgets.amounts_for("2026-11", loans=False)[food][0] == Decimal("5000")  # history unchanged


def test_editing_a_goal_saves_and_returns_it(c):
    # Edit used to fail after saving (it looked up the goal on the returned row); Mohab found it moving a date.
    goal = c.reserves.create("Phone", "6000", due_date="2027-03-31")
    saved = c.reserves.update(goal["id"], "Phone", "6000", "2027-06-30")
    assert (saved["name"], saved["due_date"]) == ("Phone", "2027-06-30")
