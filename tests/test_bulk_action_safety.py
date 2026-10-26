"""2O/3AE: confirmations and failed batches preserve their intended scope."""
import shutil

import pytest
from fastapi.testclient import TestClient

from lightning.runtime.http import Host
from lightning.ui.web import create_app


def expect(locator):
    from playwright.sync_api import expect as check
    return check(locator)


@pytest.fixture
def rows(c, setup):
    bank, food = setup[0]['cib'], setup[1]['EXP.PERSONAL.FOOD']
    made = [c.transactions.record_outflow(f'2026-09-0{i}', bank.id, '10', food.id,
                                         notes=f'old {i}') for i in (2, 3)]
    return bank, made


@pytest.fixture
def ui(c):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    hosts = []
    if not shutil.which('chromium'):
        pytest.skip('Chromium is unavailable')
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
        def open_page(phone=False):
            app = create_app(c)
            async def view(scope, receive, send):
                if scope['type'] == 'http':
                    scope.setdefault('state', {})['phone'] = phone
                await app(scope, receive, send)
            host = Host(lambda _: view).start()
            hosts.append(host)
            page = browser.new_page(viewport={'width':390 if phone else 1280, 'height':900})
            page.goto(host.launch_url)
            return page, host.origin
        yield open_page
        browser.close()
    for host in hosts:
        host.stop()


def test_phone_delete_cancel_confirm_and_undo_use_the_selected_ids(c, rows, ui):
    bank, made = rows
    page, origin = ui(phone=True)
    page.goto(f'{origin}/accounts/{bank.id}?select=1')
    page.locator('#phone-select-visible').check()
    expect(page.locator('.phone-select-count')).to_have_text('2 selected')
    delete = page.locator('#phone-bulk').get_by_role('button', name='Delete', exact=True)
    delete.click()
    dialog = page.locator('dialog.ask-dialog[open]')
    expect(dialog).to_contain_text('Delete 2 transactions?')
    assert all(not c.transactions.get(t.id).is_void for t in made)
    dialog.get_by_role('button', name='Cancel', exact=True).click()
    assert page.locator('.transaction-select:checked').count() == 2
    delete.click()
    dialog.get_by_role('button', name='Delete', exact=True).click()
    page.wait_for_url('**/*msg=*')
    assert all(c.transactions.get(t.id).is_void for t in made)
    page.locator('form[action="/history/undo"] button').click()
    page.wait_for_url('**/?msg=*')
    assert all(not c.transactions.get(t.id).is_void for t in made)


def test_phone_category_still_submits_without_a_delete_question(c, setup, rows, ui):
    bank, made = rows
    page, origin = ui(phone=True)
    page.goto(f'{origin}/accounts/{bank.id}?select=1')
    page.locator('#phone-select-visible').check()
    software = setup[1]['EXP.WORK.SOFTWARE']
    # Exercise the existing picker value without coupling this safety check to its search UI.
    page.locator('#phone-bulk select[name="category_id"]').evaluate('(el, value) => el.value = value', str(software.id))
    page.locator('#phone-bulk').get_by_role('button', name='Change category', exact=True).click()
    page.wait_for_url('**/*msg=*')
    assert all(c.transactions.get(t.id).lines[0].category_id == software.id for t in made)
    assert page.locator('dialog.ask-dialog[open]').count() == 0


def test_failed_mass_edit_keeps_scope_and_draft_then_can_succeed_after_unlock(c, rows, ui):
    bank, made = rows
    c.reconciliation.close(bank.id, '2026-09-02', '49990')
    page, origin = ui()
    page.goto(f'{origin}/accounts/{bank.id}')
    page.locator('#select-visible').check()
    page.locator('#edit-selected').click()
    note = page.locator('[form="f-edit"][name="notes"]')
    note.fill('keep this unsaved correction')
    page.locator('#f-edit').evaluate('(f) => f.requestSubmit()')
    page.get_by_role('button', name='All 2 rows', exact=True).click()
    expect(page.locator('#bulk-edit-error')).to_be_visible()
    assert [c.transactions.get(t.id).notes for t in made] == ['old 2', 'old 3']
    assert page.locator('.transaction-select:checked').count() == 2
    expect(note).to_have_value('keep this unsaved correction')
    c.reconciliation.unlock(bank.id)
    page.locator('#f-edit').evaluate('(f) => f.requestSubmit()')
    page.get_by_role('button', name='All 2 rows', exact=True).click()
    page.wait_for_url('**/*msg=*')
    assert all(c.transactions.get(t.id).notes == 'keep this unsaved correction' for t in made)
    assert page.locator('.transaction-select:checked').count() == 0
    assert c.reporting.account_balance(bank.id) == 49980


def test_json_batch_failure_rolls_back_earlier_rows(c, rows):
    bank, made = rows
    c.reconciliation.close(bank.id, '2026-09-02', '49990')
    with TestClient(create_app(c)) as client:
        response = client.post('/transactions/bulk-edit', data={
            'txn_ids':[str(made[1].id),str(made[0].id)], 'notes':'do not partly apply',
            'back':f'/accounts/{bank.id}'}, headers={'X-Requested-With':'fetch'})
    assert response.status_code == 400
    assert made[0].ref in response.json()['error']
    assert [c.transactions.get(t.id).notes for t in made] == ['old 2','old 3']


def test_legacy_batch_post_keeps_the_redirect_contract(c, rows):
    bank, made = rows
    with TestClient(create_app(c)) as client:
        response = client.post('/transactions/bulk-edit', data={
            'txn_ids':[str(t.id) for t in made], 'notes':'updated',
            'back':f'/accounts/{bank.id}'}, follow_redirects=False)
    assert response.status_code == 303
    assert all(c.transactions.get(t.id).notes == 'updated' for t in made)


def test_arabic_phone_confirmation_uses_arabic_words_and_digits(c, rows, ui):
    bank, made = rows
    c.settings.set("locale", "ar")
    page, origin = ui(phone=True)
    page.goto(f'{origin}/accounts/{bank.id}?select=1')
    page.locator('#phone-select-visible').check()
    expect(page.locator('.phone-select-count')).to_have_text('٢ محدد')
    page.locator('#phone-bulk button[formaction="/transactions/bulk-delete"]').click()
    expect(page.locator('dialog.ask-dialog[open]')).to_contain_text('تحذف ٢ معاملات؟')
    assert all(not c.transactions.get(t.id).is_void for t in made)


def test_arabic_batch_refusal_translates_the_reason_and_names_the_row(c, rows):
    bank, made = rows
    c.settings.set("locale", "ar")
    c.reconciliation.close(bank.id, '2026-09-02', '49990')
    with TestClient(create_app(c)) as client:
        response = client.post('/transactions/bulk-edit', data={
            'txn_ids':[str(t.id) for t in made], 'notes':'do not apply'}, headers={'X-Requested-With':'fetch'})
    assert response.status_code == 400
    assert made[0].ref in response.json()['error']
    assert 'This month' not in response.json()['error']
    assert 'البنك' in response.json()['error']
