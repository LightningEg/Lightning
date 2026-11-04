"""NF-7D: retrieval cannot change identities, money or the scope of a financial picker."""
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.core.matching import fold_search_text, match_score, rank_choices
from lightning.transactions.domain import TxnFilter
from lightning.ui.routes.search import matches
from lightning.ui.web import create_app


@pytest.mark.parametrize(('typed', 'saved', 'kind'), [
    ('Talbt', 'Talabat', 'Counterparty'), ('مدرسه', 'مَدْرَسة', 'Category'),
    ('cafe', 'Café', 'Account'), ('Groceres', 'Food and Groceries', 'Category'),
    ('Commercial Internatinal Bank', 'Commercial International Bank', 'Investment'),
])
def test_spelling_and_script_variants_are_retrieval_only(typed, saved, kind):
    assert match_score(typed, saved, kind=kind) > 0
    assert saved != typed
    assert fold_search_text('Ahmed') != fold_search_text('أحمد')


@pytest.mark.parametrize(('needle', 'text'), [('12', '13'), ('CIB', 'CB'), ('45.60', '45.66'), ('1', '2'), ('aa', 'ab')])
def test_short_codes_dates_and_amounts_do_not_get_typo_matches(needle, text):
    assert match_score(needle, text) == 0


def test_exact_precedes_near_ties_and_ranking_is_stable():
    rows = [{'id': '1', 'label': 'Talabat'}, {'id': '2', 'label': 'Talabat shop'}, {'id': '3', 'label': 'Talabat shops'}]
    assert rank_choices('Talabat', rows, 'Counterparty')[0] == '1'
    assert rank_choices('Talabt', rows, 'Counterparty') == rank_choices('Talabt', rows, 'Counterparty')
    assert rank_choices('zzzz', rows) == []


def test_aliases_and_duplicate_names_keep_entity_types_and_ids(c, setup):
    accounts, _ = setup
    party = c.counterparties.create(accounts['cib'].name, alias='My bank shop')
    c.counterparties.create('أحمد', kind='PERSON')
    results = matches(c, accounts['cib'].name)
    assert {'Account', 'Counterparty'} <= {row['kind'] for row in results}
    assert next(row for row in matches(c, 'My bank shop') if row['kind'] == 'Counterparty')['entity_id'] == party
    assert any(row['kind'] == 'Person' for row in matches(c, 'احمد'))
    c.counterparties.set_active(party, False)
    assert not any(row.get('entity_id') == party for row in matches(c, 'My bank shop'))


@pytest.mark.parametrize('kind', ['Account', 'Counterparty', 'Person', 'Category', 'Investment'])
def test_each_scoped_picker_ranks_only_current_choices_and_writes_nothing(c, kind):
    with TestClient(create_app(c)) as client:
        before = list(c.db.conn.iterdump())
        response = client.post('/search/picker', data={'q': 'احمد', 'kind': kind, 'choices': json.dumps([
            {'id': 'allowed', 'label': 'أحمد'}, {'id': 'other', 'label': 'محمود'}])})
        assert response.status_code == 200 and response.json()['ids'] == ['allowed']
        assert list(c.db.conn.iterdump()) == before


def test_history_uses_alias_account_and_category_ids_but_keeps_exact_filters(c, setup):
    accounts, cats = setup
    food = cats['EXP.PERSONAL.FOOD'].id
    first = c.transactions.record_outflow('2026-09-20', accounts['cib'].id, '123', food, counterparty='Talabat')
    second = c.transactions.record_outflow('2026-09-21', accounts['wallet'].id, '456', food, counterparty='Talabat')
    party = c.counterparties.resolve('Talabat')
    c.counterparties.add_alias(party['id'], 'طلبات')
    for query in ('طلبات', 'Talbt', 'Groceres'):
        assert {first.id, second.id} <= c.transactions.search_ids(query)
    assert first.id in c.transactions.search_ids('CIB Current')
    for query in ('طلبات 123', 'Talbt 2026-09-20', first.ref):
        found, total = c.transactions.find(TxnFilter(search=query, account_id=accounts['cib'].id,
                                                    date_from='2026-09-20', date_to='2026-09-20', category_ids=[food]))
        assert total == 1 and found[0].id == first.id
    assert second.id not in c.transactions.search_ids('طلبات 123')
    c.counterparties.set_active(party['id'], False)
    assert first.id in c.transactions.search_ids('طلبات')   # history retains archived identities
    c.transactions.void(first.id)
    assert first.id not in c.transactions.search_ids('طلبات')
    assert c.reporting.account_balance(accounts['wallet'].id) == Decimal('744')


def test_the_full_bundled_instrument_catalogue_fits_the_guard_and_ranks_typos(c):
    import json
    from urllib.parse import urlencode
    from lightning.assets.catalog import instruments
    from lightning.market.iso import venue_name
    from lightning.runtime.http import MAX_BODY
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    catalogue=instruments()
    choices=[{'id':str(i),'label':r['name'],'code':r['ticker'],'context':venue_name(r.get('mic'))} for i,r in enumerate(catalogue)]
    form={'q':'Glencroe','kind':'Investment','choices':json.dumps(choices,ensure_ascii=False,separators=(',',':'))}
    assert 2000 < len(choices) <= 4000
    assert len(urlencode(form).encode()) < MAX_BODY
    expected=next(str(i) for i,r in enumerate(catalogue) if r['ticker']=='GLEN' and r['mic']=='XLON')
    with TestClient(create_app(c)) as client:
        response=client.post('/search/picker',data=form)
        assert response.status_code==200 and expected in response.json()['ids']
