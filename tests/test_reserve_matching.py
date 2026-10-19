def test_matching_expense_waits_for_confirmation_and_completion_frees_cash(c):
    account = c.account_flows.open_account("CIB", "BANK", "2026-09-01", "1000")
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    reserve = c.reserves.create("Groceries", "100", "PROJECT", "2026-10-01",
                                account_id=account.id)
    c.reserves.allocate(reserve["id"], "100")
    expense = c.transactions.record_outflow("2026-09-10", account.id, "100", food.id)

    assert c.reserves.auto_link_transaction(expense.id) == 0
    assert c.reserves.links_for_transaction(expense.id) == []
    assert [row["id"] for row in c.reserves.suggested_reserves(expense.id)] == [reserve["id"]]

    c.reserves.set_expense_link(reserve["id"], expense.id, "100")
    c.reserves.complete(reserve["id"])
    assert c.reserves.get(reserve["id"])["status"] == "COMPLETE"
    assert c.reserves.cash_summary(c.reporting.owned_liquid_cash("2026-09-10"))["allocated"] == 0


def test_the_reserves_page_lists_a_goal_with_a_linked_payment(c):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    account = c.account_flows.open_account("CIB", "BANK", "2026-09-01", "10000")
    reserve = c.reserves.create("Car insurance", "9000")
    c.reserves.allocate(reserve["id"], "9000")
    paid = c.transactions.record_outflow("2026-09-10", account.id, "6000",
                                         c.categories.get_by_code("EXP.PERSONAL.TRANSPORT").id)
    c.reserves.set_expense_link(reserve["id"], paid.id, "6000")
    page = TestClient(create_app(c), base_url="http://127.0.0.1").get("/plan/reserves")
    assert page.status_code == 200
    assert "Car insurance" in page.text and "6,000" in page.text


def test_combined_criteria_require_every_match(c):
    account = c.account_flows.open_account('Daily', 'BANK', '2026-09-01', '10000')
    other = c.account_flows.open_account('Other', 'BANK', '2026-09-01', '1000')
    food = c.categories.get_by_code('EXP.PERSONAL.FOOD')
    transport = c.categories.get_by_code('EXP.PERSONAL.TRANSPORT')
    match = c.transactions.record_outflow('2026-09-10', account.id, '10', food.id, counterparty='Grocery')
    party = c.counterparties.resolve('Grocery')['id']
    reserve = c.reserves.create('Combined', '100', account_id=account.id, category_id=food.id, counterparty_id=party)
    c.reserves.allocate(reserve['id'], '100')
    mismatches = [c.transactions.record_outflow('2026-09-10', acct.id, '10', cat.id, counterparty=name)
                  for acct, cat, name in [(other, food, 'Grocery'), (account, transport, 'Grocery'), (account, food, 'Other shop')]]
    no_rule = c.reserves.create('Ask only', '100')
    c.reserves.allocate(no_rule['id'], '100')
    ids = [match.id] + [t.id for t in mismatches]
    batch = c.reserves.suggested_reserves_for_transactions(ids)
    assert [r['id'] for r in batch[match.id]] == [reserve['id']]
    assert all(batch[t.id] == [] for t in mismatches)
    assert batch == {i: c.reserves.suggested_reserves(i) for i in ids}


def test_repeated_matching_criteria_create_edit_and_clear(c):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    account = c.account_flows.open_account('Daily', 'BANK', '2026-09-01', '1000')
    food = c.categories.get_by_code('EXP.PERSONAL.FOOD')
    party = c.counterparties.create('Grocer')
    client = TestClient(create_app(c))
    data = {'name':'Combined', 'target':'100', 'match_by':['account','category'], 'account_id':str(account.id), 'category_id':str(food.id)}
    assert client.post('/reserves', data=data, follow_redirects=False).status_code == 303
    reserve = next(r for r in c.reserves.list_active() if r['name'] == 'Combined')
    assert (reserve['account_id'], reserve['category_id']) == (account.id, food.id)
    data.update(match_by=['account','category','counterparty'], counterparty_id=str(party))
    url = f"/reserves/{reserve['id']}/edit"
    assert client.post(url, data=data, follow_redirects=False).status_code == 303
    assert c.reserves.get(reserve['id'])['counterparty_id'] == party
    data.update(match_by=['category'])
    client.post(url, data=data)
    saved = c.reserves.get(reserve['id'])
    assert saved['account_id'] is None and saved['counterparty_id'] is None and saved['category_id'] == food.id
    data.update(match_by=['category','account'], account_id='')
    assert client.post(url, data=data, headers={'X-Requested-With':'fetch'}).status_code == 400
    assert c.reserves.get(reserve['id'])['category_id'] == food.id
    data.update(match_by='none')
    client.post(url, data=data)
    assert all(c.reserves.get(reserve['id'])[key] is None for key in ['account_id','category_id','counterparty_id'])
