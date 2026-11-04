"""NF-7F: labels do not change filing, and one-category edits leave the rest of the plan alone."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app
from lightning.sync.journal.proxy import JournalServices
from test_journal_finance import devices  # noqa: F401


def test_rename_clear_and_old_forms_preserve_rule_behavior_and_identity(c, setup):
    _, cats = setup
    values = c.rules.form_values() | {'counterparty':'Talabat', 'category_id':str(cats['EXP.PERSONAL.FOOD'].id), 'tag':'food'}
    rule_id = c.rules.save(values)
    original = c.rules.get(rule_id)
    ledger = c.db.all('SELECT * FROM ledger_entries')
    outcome = c.rules.outcome('Talabat')
    values['name'] = '  Food   delivery  '
    c.rules.save(values, rule_id)
    assert c.rules.get(rule_id) == replace(original, name='Food delivery')
    assert c.rules.outcome('Talabat') == outcome
    old_form = dict(values);old_form.pop('name')
    c.rules.save(old_form, rule_id)
    assert c.rules.get(rule_id).name == 'Food delivery'
    with pytest.raises(ValidationError):
        c.rules.save(values | {'name':'a'*121}, rule_id)
    assert c.rules.get(rule_id).name == 'Food delivery'
    c.rules.save(values | {'name':''}, rule_id)
    assert c.rules.get(rule_id) == original
    assert [tuple(x) for x in c.db.all('SELECT * FROM ledger_entries')] == [tuple(x) for x in ledger]


def test_rule_name_is_editable_and_shown_in_both_languages(c, setup):
    _, cats = setup
    values = c.rules.form_values() | {'name':'طلبات الأكل', 'counterparty':'Talabat', 'category_id':str(cats['EXP.PERSONAL.FOOD'].id)}
    with TestClient(create_app(c)) as client:
        client.post('/rules', data=values)
        rule = c.rules.list()[0]
        assert rule.name == 'طلبات الأكل'
        assert 'طلبات الأكل' in client.get('/rules').text
        assert 'name="name"' in client.get(f'/rules/{rule.id}/edit').text
        c.settings.set('locale','ar')
        assert 'اسم القاعدة' in client.get(f'/rules/{rule.id}/edit').text


def test_renaming_on_replica_waits_for_confirmation_and_uses_the_rule_uuid(devices):
    home, replica = devices
    services = JournalServices(home)
    category = home.c.categories.get_by_code('EXP.PERSONAL.FOOD')
    values = home.c.rules.form_values() | {'counterparty':'Talabat','category_id':str(category.id),'name':'Delivery'}
    rule_id = services.rules.save(values)
    replica.sync_with(home.home)
    uid = home.adapter.uid('rules', rule_id)
    form = replica.c.rules.form_values(replica.c.rules.list()[0]) | {'name':'Weekend delivery'}
    # The command carries portable references, while the local form carries local ids.
    from lightning.sync.journal.proxy import PendingOnHome
    with pytest.raises(PendingOnHome):
        JournalServices(replica).rules.save(form, replica.adapter.local('rules', uid))
    assert home.c.rules.get(rule_id).name == 'Delivery'
    replica.sync_with(home.home)
    assert home.c.rules.get(rule_id).name == 'Weekend delivery'
    assert replica.c.rules.list()[0].name == 'Weekend delivery'


@pytest.mark.parametrize('phone',[False,True])
def test_one_budget_category_changes_without_resubmitting_the_grid(c, setup, phone):
    _, cats = setup
    food = cats['EXP.PERSONAL.FOOD'].id
    software = cats['EXP.WORK.SOFTWARE'].id
    c.budgets.set_budget(food,'2026-12','1000',schedule=c.schedules.view())
    c.budgets.set_budget(software,'2026-12','2000',schedule=c.schedules.view())
    app = create_app(c)
    @app.middleware('http')
    async def frame(request, call_next):
        request.state.phone = phone
        return await call_next(request)
    with TestClient(app) as client:
        page = client.get('/budget?month=2026-12').text
        if phone:
            assert f'action="/budget/rule/{food}"' in page
        else:
            assert f'/budget/category/{food}/edit?month=2026-12' in page
            edit = client.get(f'/budget/category/{food}/edit?month=2026-12')
            assert edit.status_code == 200 and f'action="/budget/rule/{food}"' in edit.text
        untouched = c.db.all('SELECT * FROM budgets WHERE category_id=?',(software,))
        response = client.post(f'/budget/rule/{food}',data={'month':'2026-12','rule':'1200'},follow_redirects=False)
        assert response.status_code == 303
        assert [tuple(x) for x in c.db.all('SELECT * FROM budgets WHERE category_id=?',(software,))] == [tuple(x) for x in untouched]
        assert c.budgets.plan_left(food,'2026-12',schedule=c.schedules.view()) is not None
