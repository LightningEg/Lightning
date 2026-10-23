"""2X: a stale or concurrent confirmation cannot replace a settled occurrence."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.core.errors import ValidationError
from lightning.ui.web import create_app


def bill(c, setup, kind='BILL'):
    bank, food=setup[0]['cib'].id, setup[1]['EXP.PERSONAL.FOOD'].id
    values={'payment_count':'3'} if kind=='LOAN' else {}
    item=c.planning.create(kind=kind, name='Bill', amount='100', start_date='2026-09-02',
                           account_id=bank, category_id=food, **values)
    a=c.transactions.record_outflow('2026-09-02',bank,'100',food)
    b=c.transactions.record_outflow('2026-09-02',bank,'100',food)
    return item,a.id,b.id


def test_stale_http_link_preserves_the_first_confirmation_and_retry_is_harmless(c, setup):
    item,first,second=bill(c,setup)
    with TestClient(create_app(c)) as client:
        form={'due':'2026-09-02','outcome':'link','transaction_id':first}
        assert client.post(f'/plan/items/{item}/pay',data=form,follow_redirects=False).status_code==303
        assert client.post(f'/plan/items/{item}/pay',data=form,follow_redirects=False).status_code==303
        rejected=client.post(f'/plan/items/{item}/pay',data=form|{'transaction_id':second},follow_redirects=False)
        assert 'msg=' in rejected.headers['location']
    assert c.db.scalar('SELECT transaction_id FROM planned_payments WHERE planned_item_id=?',(item,))==first
    assert c.db.scalar('SELECT COUNT(*) FROM planned_payments WHERE planned_item_id=?',(item,))==1
    c.planning.reopen(item,'2026-09-02')
    c.planning.mark_paid(item,'2026-09-02',second)
    assert c.db.scalar('SELECT transaction_id FROM planned_payments WHERE planned_item_id=?',(item,))==second


def test_two_connections_cannot_both_confirm_different_transactions(c, setup):
    item,first,second=bill(c,setup)
    barrier=Barrier(2)
    def confirm(tid):
        other=build(c.db.path)
        try:
            barrier.wait(timeout=10)
            try:
                other.planning.mark_paid(item,'2026-09-02',tid)
                return 'linked',tid
            except ValidationError:
                return 'refused',tid
        finally:
            other.db.close()
    with ThreadPoolExecutor(2) as workers:
        results=list(workers.map(confirm,[first,second]))
    assert sorted(outcome for outcome,_ in results)==['linked','refused']
    winner=next(tid for outcome,tid in results if outcome=='linked')
    assert c.db.scalar('SELECT transaction_id FROM planned_payments WHERE planned_item_id=?',(item,))==winner


def test_partial_loan_topup_is_not_duplicated_by_retry(c,setup):
    bank,food=setup[0]['cib'].id,setup[1]['EXP.PERSONAL.FOOD'].id
    item=c.planning.create(kind='LOAN',name='Loan',amount='100',payment_count='3',start_date='2026-09-02',account_id=bank,category_id=food)
    c.planning.record_payment(item,'2026-09-02','2026-09-02','50',bank)
    topup=c.transactions.record_outflow('2026-09-03',bank,'50',food)
    for _ in range(2):
        c.planning.mark_paid(item,'2026-09-02',topup.id)
    assert c.db.scalar('SELECT COUNT(*) FROM loan_extra_payments WHERE planned_item_id=?',(item,))==1
    assert c.planning.loan_progress(c.planning.get(item))['still_to_pay']==Decimal('200')
