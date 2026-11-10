"""Real guarded uploads: Excel from the drop area survives sheet/column choices and multiple files."""
import pytest

pytest.importorskip('playwright.sync_api')

from test_import_account_defaults_browser import account_page  # noqa: F401
from test_import_file_choices import two_sheets


def test_drop_excel_and_csv_for_one_account_preserves_both_through_choices(c, setup, account_page):
    page, origin = account_page
    bank = setup[0]['cib']
    before = c.reporting.account_balance(bank.id)
    page.goto(origin + '/import')
    page.locator('#import-files').set_input_files([
        {'name': 'cib.xlsx', 'mimeType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
         'buffer': two_sheets(custom=True)},
        {'name': 'cib.csv', 'mimeType': 'text/csv', 'buffer': b'D,A,Payee\n2026-09-22,-13,Shop\n'}])
    for selector in page.locator('[data-import-list] select').all():
        selector.select_option(str(bank.id), force=True)
    page.get_by_role('button', name='Review statements', exact=True).click()
    page.wait_for_selector('input[name=sheet_0]')
    assert c.db.scalar('SELECT COUNT(*) FROM bank_import_batches') == 0
    page.locator('input[name=sheet_0]').fill('September')
    page.get_by_role('option', name='September', exact=True).click()
    page.get_by_role('button', name='Review statement', exact=True).click()
    page.wait_for_selector('select[name=map_Date]')
    page.locator('select[name=map_Date]').select_option('D', force=True)
    page.locator('select[name=map_Amount]').select_option('A', force=True)
    page.locator('select[name=map_Counterparty]').select_option('Payee', force=True)
    page.get_by_role('button', name='Preview rows', exact=True).click()
    page.wait_for_url('**/import/*')
    page.wait_for_selector('.import-summary')  # the review opens on its questions (NF-7AB1)
    assert c.db.scalar('SELECT COUNT(*) FROM bank_import_batches') == 2
    assert c.db.scalar("SELECT COUNT(*) FROM bank_import_rows WHERE status='REVIEW'") == 2
    assert c.reporting.account_balance(bank.id) == before
