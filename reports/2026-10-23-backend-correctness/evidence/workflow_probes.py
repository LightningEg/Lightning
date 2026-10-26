"""Audit 4 button/route probes. Dummy temporary ledgers only.

Run: pytest -q -rx -o addopts='' reports/2026-10-23-backend-correctness/evidence/workflow_probes.py
Known defects are strict xfails against the desired behavior; an XPASS needs review.
The ordinary app test suite does not discover this audit artifact automatically.
"""
from __future__ import annotations

import asyncio
import shutil
from decimal import Decimal as D
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import httpx
import pytest
from lightning.bootstrap import build
from lightning.ui.web import create_app


@pytest.fixture
def w(tmp_path, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-10-23')
    monkeypatch.setenv('LIGHTNING_PRICES_OFFLINE', '1')
    c = build(tmp_path / 'dummy.db')
    bank = c.account_flows.open_account('Audit bank', 'BANK', '2026-09-01', '1000')
    wallet = c.account_flows.open_account('Audit wallet', 'CASH', '2026-09-01', '0')
    state = SimpleNamespace(c=c, bank=bank, wallet=wallet,
        alice=c.counterparties.ensure_person('Alice'), bob=c.counterparties.ensure_person('Bob'),
        food=c.categories.get_by_code('EXP.PERSONAL.FOOD').id,
        software=c.categories.get_by_code('EXP.WORK.SOFTWARE').id,
        salary=c.categories.get_by_code('EXP.WORK.SALARY').id,
        custody=c.categories.get_by_code('EXP.SYSTEM.CUSTODY').id,
        app=create_app(c))
    yield state
    c.db.close()


def request(w, path, data=None):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=w.app, raise_app_exceptions=False),
                                     base_url='http://testserver') as client:
            return await (client.get(path) if data is None else client.post(path, data=data))
    return asyncio.run(run())


def assign(w, **changes):
    return dict(mode='assign', date='2026-09-02', amount='100', from_owner_id='',
                to_owner_id=str(w.alice), category_id='', notes='ownership audit') | changes


def expense_form(w, **changes):
    return dict(kind='out', date='2026-09-05', amount='10', category_id=str(w.food),
                counterparty='', owner_id='', to_account_id='', notes='',
                account_id=str(w.bank.id), return_to=f'/accounts/{w.bank.id}') | changes


def financial_rows(w):
    return tuple(tuple(row) for table in ('transactions', 'ledger_entries')
                 for row in w.c.db.all(f'SELECT * FROM {table} ORDER BY id'))


def owner_cash(w, name):
    return w.c.money_from_others.cash_balance(name, w.bank.id, '2026-10-23')


def message(reply):
    return parse_qs(urlsplit(reply.headers['location']).query).get('msg', [''])[0]


def two_expenses(w):
    return [w.c.transactions.record_outflow(f'2026-09-0{i}', w.bank.id, '10', w.food,
                                           notes=f'old {i}') for i in (2, 3)]


def test_ownership_save_edit_undo_redo_delete_restore_conserve_gross(w):
    reply = request(w, f'/accounts/{w.bank.id}/ownership/new', assign(w))
    assert reply.status_code == 303
    ident = int(urlsplit(reply.headers['location']).path.split('/')[-1])
    assert owner_cash(w, 'Alice') == 100
    assert w.c.reporting.account_balance(w.bank.id) == 1000
    reply = request(w, f'/transactions/{ident}/ownership/edit', assign(w, amount='120'))
    assert reply.status_code == 303 and owner_cash(w, 'Alice') == 120
    group = w.c.undo.available()['undo']['id']
    assert request(w, '/history/undo', {'group_id': str(group)}).status_code == 303
    assert owner_cash(w, 'Alice') == 100
    assert request(w, '/history/redo', {'group_id': str(group)}).status_code == 303
    assert owner_cash(w, 'Alice') == 120
    assert request(w, f'/transactions/{ident}/delete', {'back': '/transactions'}).status_code == 303
    assert owner_cash(w, 'Alice') == 0
    assert request(w, f'/transactions/{ident}/restore', {'back': '/transactions'}).status_code == 303
    assert owner_cash(w, 'Alice') == 120
    assert w.c.reporting.account_balance(w.bank.id) == 1000


def test_someone_paid_button_creates_one_expense_without_changing_gross(w):
    reply = request(w, f'/accounts/{w.bank.id}/ownership/new',
                    assign(w, mode='expense', category_id=str(w.food), amount='70'))
    assert reply.status_code == 303
    assert w.c.reporting.account_balance(w.bank.id) == 1000
    assert owner_cash(w, 'Alice') == 70
    assert w.c.reporting.cash_flow('2026-09-01', '2026-09-30').outflows == 70


@pytest.mark.parametrize('changes', [dict(amount='0'), dict(amount='-1'), dict(amount='1.001'),
    dict(amount='1001'), dict(amount='NaN'), dict(amount='letters'), dict(date='2026-11-01'),
    dict(date='not a date'), dict(to_owner_id='999'), dict(to_owner_id=''),
    dict(from_owner_id='1', to_owner_id='1'), dict(mode='unknown')])
def test_invalid_ownership_save_changes_nothing(w, changes):
    before = financial_rows(w)
    reply = request(w, f'/accounts/{w.bank.id}/ownership/new', assign(w, **changes))
    assert reply.status_code == 400
    assert financial_rows(w) == before


def test_ownership_edit_cannot_strand_the_previous_owners_spending(w):
    reply = request(w, f'/accounts/{w.bank.id}/ownership/new', assign(w))
    ident = int(urlsplit(reply.headers['location']).path.split('/')[-1])
    w.c.transactions.record_outflow('2026-09-03', w.bank.id, '90', w.food, owner_id=w.alice)
    request(w, f'/transactions/{ident}/ownership/edit', assign(w, to_owner_id=str(w.bob)))
    assert owner_cash(w, 'Alice') >= 0, f"Alice now owns {owner_cash(w, 'Alice')}"


def test_bulk_held_for_cannot_remove_the_old_owners_funding(w):
    txn = w.c.transactions.record_inflow('2026-09-02', w.bank.id, '100', w.custody,
                                        owner_id=w.alice, allow_system_category=True)
    w.c.transactions.record_outflow('2026-09-03', w.bank.id, '50', w.custody,
                                    owner_id=w.alice, allow_system_category=True)
    reply = request(w, '/transactions/bulk-edit', dict(txn_ids=[str(txn.id)], whom='Bob', back='/transactions'))
    assert reply.status_code == 303
    assert owner_cash(w, 'Alice') >= 0, f"Alice now owns {owner_cash(w, 'Alice')}"


def test_bulk_notes_skips_transfer_and_keeps_amounts_dates_categories(w):
    made = two_expenses(w)
    transfer = w.c.transactions.record_transfer('2026-09-04', w.bank.id, w.wallet.id, '50')
    before = [w.c.transactions.get(tx.id) for tx in made]
    reply = request(w, '/transactions/bulk-edit', dict(txn_ids=[str(t.id) for t in made + [transfer]],
                                                    notes='bulk note', back='/transactions'))
    assert 'Changed 2 rows.' in message(reply) and '1 left' in message(reply)
    for old in before:
        now = w.c.transactions.get(old.id)
        assert now.notes == 'bulk note' and now.date == old.date
        assert [(x.quantity, x.category_id) for x in now.lines] == [(x.quantity, x.category_id) for x in old.lines]
    assert w.c.transactions.get(transfer.id).notes == ''


def test_bulk_category_skips_income_transfer_and_split(w):
    made = two_expenses(w)
    income = w.c.transactions.record_inflow('2026-09-02', w.bank.id, '100', w.salary)
    transfer = w.c.transactions.record_transfer('2026-09-04', w.bank.id, w.wallet.id, '50')
    split = w.c.transactions.record_outflow('2026-09-05', w.bank.id, '20', w.food)
    w.c.transactions.update_expense_split(split.id, [(w.food, '10'), (w.software, '10')])
    reply = request(w, '/transactions/bulk-category', dict(txn_ids=[str(t.id) for t in made+[income, transfer, split]],
        category_id=str(w.software), back='/transactions'))
    assert 'category of 2 rows.' in message(reply) and '3 left' in message(reply)
    assert all(w.c.transactions.get(t.id).lines[0].category_id == w.software for t in made)
    assert w.c.transactions.get(income.id).lines[0].category_id == w.salary
    assert len(w.c.transactions.get(split.id).lines) == 2


def test_bulk_invalid_later_row_rolls_back_earlier_row(w):
    made = two_expenses(w)
    before = financial_rows(w)
    reply = request(w, '/transactions/bulk-edit', dict(txn_ids=[str(made[0].id), '999'], notes='never saved'))
    assert reply.status_code == 303 and financial_rows(w) == before


def test_bulk_checked_later_row_rolls_back_earlier_row(w):
    made = two_expenses(w)
    w.c.reconciliation.close(w.bank.id, '2026-09-02', D('990'))
    before = financial_rows(w)
    reply = request(w, '/transactions/bulk-edit', dict(txn_ids=[str(made[1].id), str(made[0].id)], notes='never saved'))
    assert 'Unlock it first' in message(reply) and financial_rows(w) == before


def test_bulk_repeated_ids_apply_once_and_undo_redo_is_one_action(w):
    made = two_expenses(w)
    reply = request(w, '/transactions/bulk-edit', dict(txn_ids=[str(t.id) for t in made]*2, notes='bulk note'))
    assert 'Changed 2 rows.' in message(reply)
    group = w.c.undo.available()['undo']['id']
    request(w, '/history/undo', {'group_id': str(group)})
    assert [w.c.transactions.get(t.id).notes for t in made] == ['old 2', 'old 3']
    request(w, '/history/redo', {'group_id': str(group)})
    assert all(w.c.transactions.get(t.id).notes == 'bulk note' for t in made)
    # Reusing the stale Undo ID after a later action must leave everything alone.
    request(w, '/transactions/bulk-edit', dict(txn_ids=[str(made[0].id)], notes='new action'))
    before = financial_rows(w)
    reply = request(w, '/history/undo', {'group_id': str(group)})
    assert 'History changed' in message(reply) and financial_rows(w) == before


@pytest.mark.parametrize('action', ['bulk-edit', 'bulk-category', 'bulk-delete'])
def test_empty_bulk_selection_changes_nothing(w, action):
    before = financial_rows(w)
    reply = request(w, f'/transactions/{action}', {'notes':'unused', 'category_id':str(w.food)})
    assert 'Choose at least one' in message(reply) and financial_rows(w) == before


def test_bulk_delete_retry_is_harmless_and_restore_is_harmless(w):
    made = two_expenses(w)
    data = dict(txn_ids=[str(t.id) for t in made], back='/transactions')
    request(w, '/transactions/bulk-delete', data)
    before = financial_rows(w)
    reply = request(w, '/transactions/bulk-delete', data)
    assert 'Deleted 0' in message(reply) and financial_rows(w) == before
    request(w, f'/transactions/{made[0].id}/restore', {'back':'/transactions'})
    before = financial_rows(w)
    request(w, f'/transactions/{made[0].id}/restore', {'back':'/transactions'})
    assert financial_rows(w) == before


def test_stale_popup_notes_save_must_not_undo_a_newer_amount(w):
    reply = request(w, f'/accounts/{w.bank.id}/transaction/new', expense_form(w))
    txn = w.c.db.scalar("SELECT MAX(id) FROM transactions WHERE type='OUT'")
    assert reply.status_code == 303
    old_form = request(w, f'/transactions/{txn}/edit-popup')
    import re
    revision = re.search(r'name="revision" value="([a-f0-9]{64})"', old_form.text).group(1)
    request(w, f'/transactions/{txn}/edit-popup', expense_form(w, amount='20', notes='newer amount'))
    reply = request(w, f'/transactions/{txn}/edit-popup', expense_form(w, notes='note from older form', revision=revision))
    assert reply.status_code in (400, 409, 412) or w.c.transactions.get(txn).lines[0].quantity == -20


def foreign_bill_without_fx(w):
    w.c.currencies.register('USD')
    usd = w.c.account_flows.open_account('USD bank', 'BANK', '2026-09-01', '0', currency='USD')
    w.c.planning.create(kind='BILL', name='Foreign bill', amount='10', frequency='MONTHLY',
                       start_date='2026-09-05', account_id=str(usd.id), category_id=str(w.food))


def test_failed_popup_save_must_not_commit_and_invite_duplicate_retry(w):
    foreign_bill_without_fx(w)
    before = financial_rows(w)
    reply = request(w, f'/accounts/{w.bank.id}/transaction/new', expense_form(w))
    if reply.status_code >= 400:
        retry = request(w, f'/accounts/{w.bank.id}/transaction/new', expense_form(w))
        assert retry.status_code == 400
    count = w.c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='OUT'")
    assert reply.status_code < 400 or financial_rows(w) == before, (
        f"HTTP {reply.status_code}; posted expenses {count}; balance {w.c.reporting.account_balance(w.bank.id)}")


@pytest.fixture
def browser(w):
    from playwright.sync_api import sync_playwright
    from lightning.runtime.http import Host
    if not shutil.which('chromium'):
        pytest.skip('Chromium is unavailable')
    host = Host(lambda _: w.app).start()
    try:
        with sync_playwright() as playwright:
            process = playwright.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
            try:
                page = process.new_page(viewport={'width':1280,'height':900})
                errors = []
                page.on('pageerror', lambda err: errors.append(str(err)))
                page.goto(host.launch_url)
                page.goto(f'{host.origin}/accounts/{w.bank.id}')
                yield page, host, errors
            finally:
                process.close()
    finally:
        host.stop()


def test_browser_ownership_cancel_and_discard_post_nothing(w, browser):
    page, host, errors = browser
    # Use the same popup link as the account's ownership action.
    page.locator('details.money-actions summary').click()
    page.locator(f'a[data-popup-open][href="/accounts/{w.bank.id}/ownership/new"]').click()
    page.locator('#app-popup[open]').wait_for()
    page.locator('#ownership-amount').fill('100')
    page.keyboard.press('Escape')
    page.get_by_role('button', name='Keep editing', exact=True).click()
    assert page.locator('#ownership-amount').input_value() == '100'
    assert w.c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='ADJ'") == 0
    page.keyboard.press('Escape')
    page.get_by_role('button', name='Discard', exact=True).click()
    page.locator('#app-popup').wait_for(state='hidden')
    assert w.c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='ADJ'") == 0
    assert not errors


def test_browser_failed_bulk_save_keeps_scope_and_typed_changes(w, browser):
    made = two_expenses(w)
    w.c.reconciliation.close(w.bank.id, '2026-09-02', D('990'))
    page, host, errors = browser
    # Both rows are selectable; the closed history refusal happens during the write.
    page.goto(f'{host.origin}/accounts/{w.bank.id}')
    boxes = page.locator('.transaction-select:not(:disabled)')
    boxes.first.check()
    boxes.nth(1).check()
    page.locator('#edit-selected').click()
    page.locator('tr.editing').wait_for()
    page.locator('[form="f-edit"][name="notes"]').fill('keep this unsaved correction')
    page.locator('#f-edit').evaluate('(f) => f.requestSubmit()')
    page.get_by_role('button', name='All 2 rows', exact=True).click()
    page.locator('#bulk-edit-error').wait_for()
    assert all(w.c.transactions.get(t.id).notes == f'old {i}' for t,i in zip(made,(2,3)))
    assert page.locator('.transaction-select:checked').count() == 2
    assert page.locator('[form="f-edit"][name="notes"]').input_value() == 'keep this unsaved correction'


def test_browser_phone_delete_waits_for_confirmation(w):
    from playwright.sync_api import sync_playwright
    from lightning.runtime.http import Host
    made = two_expenses(w)
    async def phone(scope, receive, send):
        if scope['type'] == 'http':
            scope.setdefault('state', {})['phone'] = True
        await w.app(scope, receive, send)
    host = Host(lambda _: phone).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
            page = browser.new_page(viewport={'width':390, 'height':844})
            page.goto(host.launch_url)
            page.goto(f'{host.origin}/accounts/{w.bank.id}?select=1')
            page.locator('#phone-select-visible').check()
            page.locator('#phone-bulk').get_by_role('button', name='Delete', exact=True).click()
            state = [w.c.transactions.get(t.id).is_void for t in made]
            assert not any(state), f'Before any confirmation answer, selected rows are void: {state}'
            assert page.locator('dialog.ask-dialog[open]').count() == 1
            browser.close()
    finally:
        host.stop()


def test_browser_ownership_save_uses_the_picker_and_posts_once(w, browser):
    page, host, errors = browser
    page.locator('details.money-actions summary').click()
    page.locator(f'a[data-popup-open][href="/accounts/{w.bank.id}/ownership/new"]').click()
    page.locator('#app-popup[open]').wait_for()
    page.locator('#ownership-amount').fill('100')
    page.get_by_role('combobox', name='To / person who paid').fill('Alice')
    page.locator('#ownership-to-options [role=option]').filter(has_text='Alice').click()
    page.locator('#app-popup-content').get_by_role('button', name='Save', exact=True).click()
    page.wait_for_url(f'**/accounts/{w.bank.id}')
    assert w.c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='ADJ'") == 1
    assert owner_cash(w, 'Alice') == 100
    assert w.c.reporting.account_balance(w.bank.id) == 1000
    assert not errors


def test_browser_pc_delete_cancel_then_confirm_then_undo(w, browser):
    made = two_expenses(w)
    page, host, errors = browser
    page.goto(f'{host.origin}/accounts/{w.bank.id}')
    page.locator('#select-visible').check()
    page.locator('#delete-selected').click()
    page.locator('dialog.ask-dialog[open]').wait_for()
    page.get_by_role('button', name='Cancel', exact=True).click()
    assert all(not w.c.transactions.get(t.id).is_void for t in made)
    assert page.locator('.transaction-select:checked').count() == 2
    page.locator('#delete-selected').click()
    page.locator('dialog.ask-dialog[open]').get_by_role('button', name='Delete', exact=True).click()
    page.wait_for_url('**/*msg=*')
    assert all(w.c.transactions.get(t.id).is_void for t in made)
    page.locator('form[action="/history/undo"] button').click()
    page.wait_for_url('**/?msg=*')
    assert all(not w.c.transactions.get(t.id).is_void for t in made)
    assert not errors


def test_browser_phone_change_category_applies_to_selected_rows(w):
    from playwright.sync_api import sync_playwright
    from lightning.runtime.http import Host
    made = two_expenses(w)
    async def phone(scope, receive, send):
        if scope['type'] == 'http':
            scope.setdefault('state', {})['phone'] = True
        await w.app(scope, receive, send)
    host = Host(lambda _: phone).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
            page = browser.new_page(viewport={'width':390,'height':844})
            page.goto(host.launch_url)
            page.goto(f'{host.origin}/accounts/{w.bank.id}?select=1')
            page.locator('#phone-select-visible').check()
            page.get_by_role('combobox', name='Category for the selected rows').fill('Software')
            page.locator('#phone-bulk [role=option]').filter(has_text='Software').click()
            page.locator('#phone-bulk').get_by_role('button', name='Change category', exact=True).click()
            page.wait_for_url('**/*msg=*')
            assert all(w.c.transactions.get(t.id).lines[0].category_id==w.software for t in made)
            assert w.c.reporting.account_balance(w.bank.id)==980
            browser.close()
    finally:
        host.stop()


def test_merge_preview_is_read_only_stale_confirm_refuses_and_undo_restores(w):
    made = two_expenses(w)
    before = financial_rows(w)
    reply = request(w, f'/transactions/merge?keep={made[0].id}&drop={made[1].id}')
    assert reply.status_code == 200 and financial_rows(w) == before
    preview = w.c.transactions.merge_preview(made[0].id, made[1].id)
    w.c.transactions.update_metadata(made[1].id, made[1].date, notes='changed since preview')
    before = financial_rows(w)
    form = dict(keep_id=str(made[0].id),drop_id=str(made[1].id),fingerprint=preview.fingerprint)
    assert request(w, '/transactions/merge', form).status_code == 400
    assert financial_rows(w) == before
    form['fingerprint'] = w.c.transactions.merge_preview(made[0].id,made[1].id).fingerprint
    assert request(w, '/transactions/merge', form).status_code == 303
    assert w.c.transactions.get(made[1].id).is_void
    group = w.c.undo.available()['undo']['id']
    after = financial_rows(w)
    assert request(w, '/transactions/merge', form).status_code == 400
    assert financial_rows(w) == after
    request(w, '/history/undo', {'group_id':str(group)})
    assert not w.c.transactions.get(made[1].id).is_void
    assert w.c.reporting.account_balance(w.bank.id) == 980


def test_split_save_validates_sum_and_undo_preserves_original(w):
    txn = two_expenses(w)[0]
    before = financial_rows(w)
    path = f'/transactions/{txn.id}/split'
    invalid = dict(split_category_id=[str(w.food),str(w.software)],split_amount=['8','8'])
    assert request(w,path,invalid).status_code == 303
    assert financial_rows(w) == before
    valid = dict(split_category_id=[str(w.food),str(w.software)],split_amount=['4','6'])
    assert request(w,path,valid).status_code == 303
    assert len(w.c.transactions.get(txn.id).lines) == 2
    assert w.c.reporting.account_balance(w.bank.id) == 980
    group = w.c.undo.available()['undo']['id']
    request(w, '/history/undo', {'group_id':str(group)})
    assert len(w.c.transactions.get(txn.id).lines) == 1


def test_record_bill_payment_rejects_repeat_and_undo_removes_cash_and_link(w):
    ident = w.c.planning.create(kind='BILL',name='Internet bill',amount='25',frequency='MONTHLY',
        start_date='2026-09-05',account_id=str(w.bank.id),category_id=str(w.food))
    form = dict(due='2026-09-05',outcome='record',date_paid='2026-09-05',amount='25',account_id=str(w.bank.id))
    path = f'/plan/items/{ident}/pay'
    reply = request(w,path,form)
    assert reply.status_code == 303 and 'recorded and marked paid' in message(reply)
    assert w.c.reporting.account_balance(w.bank.id) == 975
    group = w.c.undo.available()['undo']['id']
    before = financial_rows(w)
    reply = request(w,path,form)
    assert 'already settled' in message(reply) and financial_rows(w) == before
    request(w, '/history/undo', {'group_id':str(group)})
    assert w.c.reporting.account_balance(w.bank.id) == 1000
    assert w.c.db.scalar('SELECT COUNT(*) FROM planned_payments WHERE planned_item_id=?',(ident,)) == 0
