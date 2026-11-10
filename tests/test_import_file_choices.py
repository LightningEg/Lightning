"""BT-7AD/7AE/7AH: file choices remain read-only, preserve text and active duplicate evidence."""
import base64
import html
import json
import re
from datetime import date
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from lightning.bank_import_rows import decode_csv
from lightning.core.errors import ConflictError, ValidationError
from lightning.core.limits import MAX_STATEMENT_DOCUMENT_BYTES, MAX_WORKSHEET_REQUEST_BYTES
from lightning.import_profile import profile_dates, read_date
from lightning.runtime.app import _form_field_limit, _form_part_limit, _form_file_limit
from lightning.runtime.http import request_body_limit
from lightning.statement_files import read_excel, read_statement, WorksheetSelectionRequired
from lightning.ui.routes.bank_imports import _read_sheet_bundle
from lightning.ui.web import create_app


def two_sheets(*, custom=False, formula=False):
    workbook = Workbook()
    first = workbook.active
    first.title = 'Ignore this'
    first.append(['Date', 'Amount'])
    first.append(['2026-09-20', '=1+1' if formula else '-99'])
    second = workbook.create_sheet('September')
    second.append(['D', 'A', 'Payee'] if custom else ['Date', 'Amount', 'Counterparty'])
    second.append(['2026-09-21', -12, 'Café'])
    out = BytesIO()
    workbook.save(out)
    workbook.close()
    return out.getvalue()


def hidden(page, name):
    match = re.search(r'name="' + re.escape(name) + r'" value=([\'"])(.*?)\1', page)
    return html.unescape(match.group(2))


def test_only_selected_literal_worksheet_is_read():
    data = two_sheets(formula=True)
    with pytest.raises(WorksheetSelectionRequired) as error:
        read_excel(data)
    assert error.value.sheets == ['Ignore this', 'September']
    _, rows = decode_csv(read_excel(data, sheet_name='September'))
    assert len(rows) == 1 and rows[0]['Amount'] == '-12' and rows[0]['Counterparty'] == 'Café'
    with pytest.raises(ValidationError, match='formulas'):
        read_excel(data, sheet_name='Ignore this')
    with pytest.raises(ValidationError, match='from this workbook'):
        read_excel(data, sheet_name='Missing')


def test_multisheet_upload_then_second_sheet_stages_without_money(c, setup):
    bank = setup[0]['cib']
    before = c.reporting.account_balance(bank.id)
    client = TestClient(create_app(c))
    page = client.post(f'/accounts/{bank.id}/import', files={'file': ('book.xlsx', two_sheets())})
    assert page.status_code == 200 and 'Choose worksheets' in page.text and 'September' in page.text
    assert c.db.scalar('SELECT COUNT(*) FROM bank_import_batches') == 0
    chosen = client.post(f'/accounts/{bank.id}/import/sheets', data={
        'bundle': hidden(page.text, 'bundle'), 'sheet_0': 'September', 'encoding': 'auto'}, follow_redirects=False)
    assert chosen.status_code == 303
    batch = int(chosen.headers['location'].split('/')[-1])
    info, rows = c.bank_imports.preview(batch)
    assert info['file_name'] == 'book.xlsx [September]'
    assert len(rows) == 1 and rows[0]['Amount'] == '-12'
    assert c.reporting.account_balance(bank.id) == before


def test_mixed_bundle_survives_sheet_and_column_choices(c, setup):
    bank = setup[0]['cib']
    client = TestClient(create_app(c))
    page = client.post(f'/accounts/{bank.id}/import', files=[
        ('file', ('book.xlsx', two_sheets(custom=True))),
        ('file', ('other.csv', b'D,A,Payee\n2026-09-22,-13,Other shop\n'))])
    assert page.status_code == 200 and c.db.scalar('SELECT COUNT(*) FROM bank_import_batches') == 0
    mapped = client.post(f'/accounts/{bank.id}/import/sheets', data={
        'bundle': hidden(page.text, 'bundle'), 'sheet_0': 'September'})
    assert mapped.status_code == 200 and 'map_Date' in mapped.text
    bundle = json.loads(hidden(mapped.text, 'bundle'))
    assert len(bundle) == 2 and bundle[0]['filename'].endswith('[September]')
    assert c.db.scalar('SELECT COUNT(*) FROM bank_import_batches') == 0
    done = client.post(f'/accounts/{bank.id}/import/map', data={
        'payload': hidden(mapped.text, 'payload'), 'filename': hidden(mapped.text, 'filename'),
        'bundle': json.dumps(bundle), 'amount_model': 'SINGLE', 'map_Date': 'D',
        'map_Amount': 'A', 'map_Counterparty': 'Payee'}, follow_redirects=False)
    assert done.status_code == 303 and c.db.scalar('SELECT COUNT(*) FROM bank_import_batches') == 2
    assert c.db.scalar("SELECT COUNT(*) FROM bank_import_rows WHERE status='REVIEW'") == 2


@pytest.mark.parametrize('encoding,text', [
    ('utf-8-sig', 'Café'), ('utf-16', 'متجر'), ('utf-16-le', 'متجر'),
    ('utf-16-be', 'متجر'), ('cp1256', 'متجر'), ('cp1252', 'Café €')])
def test_csv_encodings_preserve_names(encoding, text):
    raw = f'Date,Amount,Counterparty\n2026-09-20,-12,{text}\n'.encode(encoding)
    requested = 'cp1252' if encoding == 'cp1252' else 'auto'
    _, rows = decode_csv(read_statement('statement.csv', raw, 'EGP', encoding=requested))
    assert rows[0]['Counterparty'] == text


def test_explicit_csv_encoding_flows_through_http(c, setup):
    bank = setup[0]['cib']
    client = TestClient(create_app(c))
    response = client.post(f'/accounts/{bank.id}/import', data={'encoding': 'cp1252'},
                           files={'file': ('western.csv', 'Date,Amount,Counterparty\n2026-09-20,-12,Café €\n'.encode('cp1252'))},
                           follow_redirects=False)
    assert response.status_code == 303
    _, rows = c.bank_imports.preview(int(response.headers['location'].split('/')[-1]))
    assert rows[0]['Counterparty'] == 'Café €'


@pytest.mark.parametrize('bundle', ['{}', '[]', '[null]', '[1]', '[{}]', '[{"filename":1,"payload":""}]',
                                    '[{"filename":"x.xlsx","payload":"!"}]', json.dumps([{'filename': 'x', 'payload': ''}] * 21)])
def test_malformed_sheet_bundles_are_refused(bundle):
    with pytest.raises(ValidationError, match='Upload them again'):
        _read_sheet_bundle(bundle)


def test_worksheet_continuation_has_bounded_bytes_and_runtime_form_budget():
    path = '/accounts/17/import/sheets'
    assert request_body_limit(path) == MAX_WORKSHEET_REQUEST_BYTES
    assert _form_part_limit(path) == MAX_WORKSHEET_REQUEST_BYTES
    assert _form_field_limit(path) == 100 and _form_file_limit(path) == 0
    assert _form_file_limit('/accounts/17/import') == 20
    chunk = base64.b64encode(b'x' * (MAX_STATEMENT_DOCUMENT_BYTES // 2 + 1)).decode()
    with pytest.raises(ValidationError):
        _read_sheet_bundle(json.dumps([{'filename': 'a.xlsx', 'payload': chunk}, {'filename': 'b.xlsx', 'payload': chunk}]))


@pytest.mark.parametrize('value,expected', [('46631', '2027-09-01'), ('46631.5', '2027-09-01'),
    ('٤٦٦٣١', '2027-09-01'), ('1', '1900-01-01'), ('59', '1900-02-28'), ('61', '1900-03-01')])
def test_excel_serial_dates(value, expected):
    assert read_date(value).isoformat() == expected


@pytest.mark.parametrize('value', ['0', '-1', '60', '60.5', 'NaN', 'Infinity', '2958466', '999999999999999999999999'])
def test_invalid_excel_serial_dates(value):
    with pytest.raises(ValidationError):
        read_date(value)


def test_serial_dates_do_not_bias_text_date_order_and_amount_stays_numeric(c, setup):
    assert profile_dates(['46631', '10/13/2026', '10/02/2026']).order == 'mdy'
    serial = (date(2026, 9, 20) - date(1899, 12, 30)).days
    batch, _ = c.bank_imports.stage(setup[0]['cib'].id, 'serial.csv',
        f'Date,Amount,Counterparty,Category\n{serial},-100,Shop,Food & Groceries\n46631,-20,Future,Food & Groceries\n'.encode())
    _, rows = c.bank_imports.preview(batch)
    assert rows[0]['Date'] == '2026-09-20' and rows[0]['Amount'] == '-100'
    assert rows[1]['Date'] == '2027-09-01'
    assert rows[1]['_skip_reason'] and 'future' in rows[1]['_skip_reason']
    before = c.reporting.account_balance(setup[0]['cib'].id)
    result = c.bank_imports.confirm(batch, {rows[0]['_import_row_id']: {}})
    assert result['posted'] == 1 and c.reporting.account_balance(setup[0]['cib'].id) == before - 100


@pytest.mark.parametrize('reference', [True, False])
def test_reupload_matches_only_active_rows_and_explicit_override_posts_once(c, setup, reference):
    bank = setup[0]['cib']
    suffix = ',Reference' if reference else ''
    refs = [',A', ',B'] if reference else ['', '']
    data = (f'Date,Amount,Counterparty,Category{suffix}\n'
            f'2026-09-20,-10,Shop,Food & Groceries{refs[0]}\n'
            f'2026-09-21,-20,Other shop,Food & Groceries{refs[1]}\n').encode()
    first, _ = c.bank_imports.stage(bank.id, 'same.csv', data)
    _, rows = c.bank_imports.preview(first)
    assert c.bank_imports.confirm(first, {r['_import_row_id']: {} for r in rows})['posted'] == 2
    removed = c.db.scalar('SELECT transaction_id FROM bank_import_rows WHERE batch_id=? ORDER BY row_number LIMIT 1', (first,))
    c.transactions.void(removed, 'test deletion')
    second, _ = c.bank_imports.stage(bank.id, 'same.csv', data)
    _, rows = c.bank_imports.preview(second)
    assert not rows[0]['_possible_duplicate'] and rows[0]['_default_match'] == 'new'
    assert rows[1]['_possible_duplicate'] and rows[1]['_repeat_import']
    before = c.reporting.account_balance(bank.id)
    client = TestClient(create_app(c))
    page = client.get(f'/accounts/{bank.id}/import/{second}?rows=all')
    assert 'Not a duplicate' in page.text
    decisions = {rows[0]['_import_row_id']: {'skip': True}, rows[1]['_import_row_id']: {'match': 'new'}}
    assert c.bank_imports.confirm(second, decisions)['posted'] == 1
    assert c.reporting.account_balance(bank.id) == before - 20
    with pytest.raises(ConflictError):
        c.bank_imports.confirm(second, decisions)


def test_historical_skips_do_not_mark_new_upload_duplicate(c, setup):
    bank = setup[0]['cib']
    data = b'Date,Amount,Counterparty\n2026-09-20,-10,Shop\n'
    first, _ = c.bank_imports.stage(bank.id, 'skipped.csv', data)
    _, rows = c.bank_imports.preview(first)
    c.bank_imports.confirm(first, {rows[0]['_import_row_id']: {'skip': True}})
    second, _ = c.bank_imports.stage(bank.id, 'skipped.csv', data)
    _, rows = c.bank_imports.preview(second)
    assert not rows[0]['_possible_duplicate'] and rows[0]['_default_match'] == 'new'


def test_utf8_normalization_preserves_historical_hash_bytes():
    for data in (b'Date,Amount\n2026-09-20,-1\n', b'\xef\xbb\xbfDate,Amount\n2026-09-20,-1\n'):
        assert read_statement('old.csv', data, 'EGP') == data


def test_duplicate_override_survives_http_validation_and_posts_once(c, setup):
    bank, category = setup[0]['cib'], setup[1]['EXP.PERSONAL.FOOD']
    data = b'Date,Amount,Counterparty,Category\n2026-09-20,-10,Carrefour,Food & Groceries\n'
    first, _ = c.bank_imports.stage(bank.id, 'same.csv', data)
    _, rows = c.bank_imports.preview(first)
    c.bank_imports.confirm(first, {rows[0]['_import_row_id']: {}})
    second, _ = c.bank_imports.stage(bank.id, 'same.csv', data)
    _, rows = c.bank_imports.preview(second)
    row = rows[0]['_import_row_id']
    before = c.reporting.account_balance(bank.id)
    client = TestClient(create_app(c))
    form = {f'match_{row}': 'new', f'category_{row}': str(category.id), f'amount_{row}': 'bad'}
    page = client.post(f'/accounts/{bank.id}/import/{second}/confirm', data=form)
    assert page.status_code == 200 and f'<option value="new" selected>' in page.text
    assert c.reporting.account_balance(bank.id) == before
    form[f'amount_{row}'] = '-10'
    response = client.post(f'/accounts/{bank.id}/import/{second}/confirm', data=form)
    assert response.status_code == 200
    assert c.reporting.account_balance(bank.id) == before - 10
    assert c.bank_imports.summary(second)['posted'] == 1
    client.post(f'/accounts/{bank.id}/import/{second}/confirm', data=form)
    assert c.reporting.account_balance(bank.id) == before - 10
