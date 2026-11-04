"""Mohab's statement step: select a document, review its rows, then confirm real money once."""
from decimal import Decimal

import pytest

from lightning.ui.web import create_app
from screens import Browser, Choose
from test_statement_files import workbook, pdf, cib_lines


@pytest.mark.parametrize('document',['excel','pdf'])
def test_mohab_brings_a_statement_through_the_existing_review(c,setup,document):
    bank=setup[0]['cib']
    if document=='excel':
        filename='fictional-mohab.xlsx'
        data=workbook([['Date','Amount','Counterparty'],['2026-09-20',-125,'Example shop']])
        expected=Decimal('-125')
    else:
        filename='fictional-cib.pdf';data=pdf(cib_lines());expected=Decimal('875')
    b=Browser(create_app(c))
    b.go('Transactions','Accounts',bank.name,'Import statement')
    before=c.reporting.account_balance(bank.id)
    b.submit(button='Review statement',files={'file':(filename,data)})
    assert c.reporting.account_balance(bank.id)==before
    form=b.page.form('Post ready rows')
    answers={}
    for key,value in form.fields.items():
        if not key.startswith('amount_'):continue
        rid=key.split('_',1)[1]
        answers[f'category_{rid}']=Choose('Food & Groceries' if Decimal(value)<0 else 'Salary')
        party=form.fields.get('counterparty_'+rid,'')
        if party:answers['counterparty_pick_'+rid]='new:'+party
    assert answers
    b.submit(answers,button='Post ready rows')
    assert c.reporting.account_balance(bank.id)==before+expected
    assert 'Posted' in b.page.text or 'posted' in b.page.text
