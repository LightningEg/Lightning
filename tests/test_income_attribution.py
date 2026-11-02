from decimal import Decimal


def _planned_salary(c, account_id, salary_id, due_date="2026-11-15"):
    item_id = c.planning.create(
        kind="INCOME", name="Monthly salary", amount="20000", frequency="MONTHLY",
        start_date=due_date, account_id=str(account_id), category_id=str(salary_id),
    )
    return c.planning.record_payment(item_id, due_date, "2026-10-29", "20000", account_id)


def test_early_salary_is_averaged_in_scheduled_month_but_reported_on_bank_date(c, setup):
    accounts, cats = setup
    salary = cats["EXP.WORK.SALARY"]
    bonus = c.categories.get_by_code("EXP.WORK.BONUS")

    c.transactions.record_inflow("2026-09-20", accounts["cib"].id, "8000", salary.id)
    _planned_salary(c, accounts["cib"].id, salary.id)
    c.transactions.record_inflow("2026-10-20", accounts["cib"].id, "10000", salary.id)
    c.transactions.record_inflow("2026-10-21", accounts["cib"].id, "90000", bonus.id)
    owner_id = c.counterparties.create("Family member")
    c.transactions.record_inflow("2026-10-22", accounts["cib"].id, "50000", salary.id,
                                 owner_id=owner_id)

    average = c.budgets.income_average("2026-12", schedule=c.schedules.view())

    # September, October and November each contribute exactly one recurring salary payment.
    assert average.months_counted == 3
    assert average.amount == Decimal("12666.67")
    assert c.reporting.cash_flow("2026-10-01", "2026-10-31").inflows == Decimal("120000")
    assert c.reporting.cash_flow("2026-11-01", "2026-11-30").inflows == Decimal("0")


def test_unlinked_salary_stays_in_bank_month(c, setup):
    accounts, cats = setup
    salary = cats["EXP.WORK.SALARY"]
    _planned_salary(c, accounts["cib"].id, salary.id)
    c.transactions.record_inflow("2026-10-20", accounts["cib"].id, "7000", salary.id)

    # November's scheduled payment is outside this Sep–Oct lookback; the unlinked Oct
    # transaction remains in October and is included.
    average = c.budgets.income_average("2026-11", schedule=c.schedules.view())
    assert average.months_counted == 1
    assert average.amount == Decimal("7000.00")
