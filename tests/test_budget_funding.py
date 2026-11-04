from datetime import date
from decimal import Decimal as D

from lightning.planning.loan_actions import record_early_payment


def test_reserve_funding_preserves_gross_and_free_cash(c, setup):
    bank, food = setup[0]['cib'].id, setup[1]['EXP.PERSONAL.FOOD'].id
    c.budgets.set_budget(food, '2026-12', '1000', schedule=c.schedules.view())
    reserve = c.reserves.create('Repairs', '600')
    c.reserves.allocate(reserve['id'], '600')
    before = c.position.at('2026-12-31').free_cash
    expense = c.transactions.record_outflow('2026-12-20', bank, '700', food)
    c.reserves.set_expense_link(reserve['id'], expense.id, '600')
    assert c.position.at('2026-12-31').free_cash == before - D('100')
    assert c.reporting.cash_flow('2026-12-01', '2026-12-31').outflows == D('700')
    assert c.budgets.owned_spending('2026-12-01', '2026-12-31')[food] == D('700')
    assert c.budgets.plan_funded_spending('2026-12-01', '2026-12-31')[food] == D('100')
    line = next(line for section in c.budgets.month_view('2026-12', schedule=c.schedules.view()).sections for line in section.lines
                if line.category_id == food)
    assert line.actual == D('700') and line.planned_actual == D('100') and line.remaining == D('900')
    c.transactions.void(expense.id)
    assert c.budgets.funding.by_category('2026-12-01', '2026-12-31') == {}
    c.transactions.restore(expense.id)
    assert c.budgets.funding.by_category('2026-12-01', '2026-12-31')[food]['reserve'] == D('600')
    c.transactions.update_money(expense.id, '2026-12-20', bank, '650', food)
    assert c.budgets.funding.by_category('2026-12-01', '2026-12-31') == {}
    assert c.budgets.plan_funded_spending('2026-12-01', '2026-12-31')[food] == D('650')


def test_early_principal_does_not_enlarge_automatic_plan_or_hide_fee(c, setup):
    bank = setup[0]['cib'].id
    category = c.categories.get_by_code('EXP.SYSTEM.LOANS').id
    loan = c.planning.create(kind='LOAN', name='Loan', amount='1000', frequency='MONTHLY',
                             start_date='2026-12-20', payment_count='10', account_id=str(bank),
                             category_id=str(category))
    txn = record_early_payment(c.planning, loan, '5000', '100', '2026-12-05', bank, '10000')
    assert c.reporting.cash_flow('2026-12-01', '2026-12-31').outflows == D('5100')
    assert c.budgets.plan_funded_spending('2026-12-01', '2026-12-31')[category] == D('100')
    assert c.budgets.scheduled_payments('2026-12', schedule=c.schedules.view())[category] == D('1000')
    assert c.budgets.plan_summary('2026-12', schedule=c.schedules.view())['left'] == D('900')
    c.transactions.void(txn)
    assert c.budgets.funding.by_category('2026-12-01', '2026-12-31') == {}


def test_partial_reserve_on_split_is_allocated_once_and_undoable(c, setup):
    bank = setup[0]['cib'].id
    food = setup[1]['EXP.PERSONAL.FOOD'].id
    other = setup[1]['EXP.WORK.SOFTWARE'].id
    expense = c.transactions.record_outflow('2026-12-20', bank, '100', food)
    c.transactions.update_expense_split(expense.id, [(food, '60'), (other, '40')])
    a, b = c.reserves.create('A', '40'), c.reserves.create('B', '30')
    c.reserves.allocate(a['id'], '40')
    c.reserves.allocate(b['id'], '30')
    c.reserves.set_expense_link(a['id'], expense.id, '40')
    c.reserves.set_expense_link(b['id'], expense.id, '30')
    totals = c.budgets.funding.by_category('2026-12-01', '2026-12-31')
    assert (totals[food]['reserve'], totals[other]['reserve']) == (D('42'), D('28'))
    assert c.budgets.plan_funded_spending('2026-12-01', '2026-12-31')[food] == D('18')
    assert c.budgets.plan_funded_spending('2026-12-01', '2026-12-31')[other] == D('12')
    c.reserves.unlink_expense(a['id'], expense.id)
    assert sum(x['reserve'] for x in c.budgets.funding.by_category('2026-12-01', '2026-12-31').values()) == D('30')


def test_early_payment_and_reserve_overlap_never_adjusts_more_than_payment(c, setup):
    bank = setup[0]['cib'].id
    category = c.categories.get_by_code('EXP.SYSTEM.LOANS').id
    loan = c.planning.create(kind='LOAN', name='Loan', amount='1000', frequency='MONTHLY',
                             start_date='2026-12-20', payment_count='10', account_id=str(bank), category_id=str(category))
    txn = record_early_payment(c.planning, loan, '5000', '100', '2026-12-05', bank, '10000')
    reserve = c.reserves.create('Debt', '5100')
    c.reserves.allocate(reserve['id'], '5100')
    c.reserves.set_expense_link(reserve['id'], txn, '5100')
    amounts = c.budgets.funding.by_category('2026-12-01', '2026-12-31')[category]
    assert amounts == {'principal': D('5000'), 'reserve': D('100')}
    assert c.budgets.plan_funded_spending('2026-12-01', '2026-12-31')[category] == 0


def test_reserve_funding_does_not_change_forecast_twice_and_is_visible(c, setup):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    bank, food = setup[0]['cib'].id, setup[1]['EXP.PERSONAL.FOOD'].id
    c.budgets.set_budget(food, '2026-12', '1000', schedule=c.schedules.view())
    reserve = c.reserves.create('Repairs', '600')
    c.reserves.allocate(reserve['id'], '600')
    before = c.forecaster.forecast(date(2026, 12, 31))
    expense = c.transactions.record_outflow('2026-12-20', bank, '600', food)
    c.reserves.set_expense_link(reserve['id'], expense.id, '600')
    after = c.forecaster.forecast(date(2026, 12, 31))
    assert after.free_cash == before.free_cash
    assert after.safe_to_spend == before.safe_to_spend
    page = TestClient(create_app(c)).get('/budget?period=month&month=2026-12').text
    assert 'Funded outside the plan' in page
    assert '600' in page
    assert c.budgets.funding.by_category('2026-12-01', '2026-12-19') == {}
    assert c.budgets.funding.by_category('2026-12-20', '2026-12-20')[food]['reserve'] == D('600')


def test_funding_replays_with_undo_and_redo(c, setup):
    from lightning.undo import user_action
    bank, food = setup[0]['cib'].id, setup[1]['EXP.PERSONAL.FOOD'].id
    expense = c.transactions.record_outflow('2026-12-20', bank, '100', food)
    reserve = c.reserves.create('Trip', '100')
    c.reserves.allocate(reserve['id'], '100')
    with user_action('Link payment'):
        c.reserves.set_expense_link(reserve['id'], expense.id, '100')
    assert c.budgets.plan_funded_spending('2026-12-01', '2026-12-31')[food] == 0
    c.undo.replay()
    assert c.budgets.plan_funded_spending('2026-12-01', '2026-12-31')[food] == D('100')
    c.undo.replay(redo=True)
    assert c.budgets.plan_funded_spending('2026-12-01', '2026-12-31')[food] == 0


def test_loan_installment_topup_remains_monthly_spending(c, setup):
    bank, food = setup[0]['cib'].id, setup[1]['EXP.PERSONAL.FOOD'].id
    item = c.planning.create(kind='LOAN', name='Loan', amount='100', payment_count='3',
                             start_date='2026-12-02', account_id=bank, category_id=food)
    c.planning.record_payment(item, '2026-12-02', '2026-12-02', '50', bank)
    topup = c.transactions.record_outflow('2026-12-03', bank, '50', food)
    c.planning.mark_paid(item, '2026-12-02', topup.id)
    assert c.budgets.funding.by_category('2026-12-01', '2026-12-31') == {}
    assert c.budgets.plan_funded_spending('2026-12-01', '2026-12-31')[food] == D('100')


def test_carryover_uses_plan_funded_not_gross_spending(c, setup):
    bank, food = setup[0]['cib'].id, setup[1]['EXP.PERSONAL.FOOD'].id
    c.budgets.set_budget(food, '2026-11', '100', schedule=c.schedules.view())
    c.budgets.set_carryover('2026-12', {food: True}, schedule=c.schedules.view())
    expense = c.transactions.record_outflow('2026-11-20', bank, '80', food)
    reserve = c.reserves.create('Travel', '60')
    c.reserves.allocate(reserve['id'], '60')
    c.reserves.set_expense_link(reserve['id'], expense.id, '60')
    line = next(line for section in c.budgets.month_view('2026-12', schedule=c.schedules.view()).sections for line in section.lines
                if line.category_id == food)
    assert line.opening_carryover == D('80')


def test_budget_average_and_spending_average_keep_their_distinct_meanings(c, setup):
    bank, food = setup[0]['cib'].id, setup[1]['EXP.PERSONAL.FOOD'].id
    expense = c.transactions.record_outflow('2026-11-20', bank, '100', food)
    reserve = c.reserves.create('Travel', '60')
    c.reserves.allocate(reserve['id'], '60')
    c.reserves.set_expense_link(reserve['id'], expense.id, '60')
    assert c.budgets.category_averages('2026-12', schedule=c.schedules.view())[food]['average3'] == D('40')
    assert c.budgets.spending_average('2026-12').amount == D('100')


def test_one_cent_reserve_split_preserves_exact_funding_total(c, setup):
    bank = setup[0]['cib'].id
    food, other = setup[1]['EXP.PERSONAL.FOOD'].id, setup[1]['EXP.WORK.SOFTWARE'].id
    expense = c.transactions.record_outflow('2026-12-20', bank, '100', food)
    c.transactions.update_expense_split(expense.id, [(food, '60'), (other, '40')])
    reserve = c.reserves.create('Fund', '1')
    c.reserves.allocate(reserve['id'], '1')
    c.reserves.set_expense_link(reserve['id'], expense.id, '0.01')
    amounts = c.budgets.funding.by_category('2026-12-01', '2026-12-31')
    assert (amounts[food]['reserve'], amounts[other]['reserve']) == (D('0.006'), D('0.004'))
    assert sum(value['reserve'] for value in amounts.values()) == D('0.01')
