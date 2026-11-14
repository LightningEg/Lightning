"""Comprehensive workbook portability: values, joins, validation and confirmation."""
from io import BytesIO
from datetime import date
from decimal import Decimal
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.reporting.xlsx import tabular_workbook_bytes
from lightning.ui.web import create_app
from lightning.workflows.ai_analysis import AIAnalysisService
from lightning.ui.periods import parse_period
from lightning.core.dates import today
from lightning.workflows.data_export import export_all, export_tables, _raw_tables
from lightning.workflows.workbook_import import prepare_import, confirm_import, read_workbook


def _source(c):
    bank = c.account_flows.open_account('Example bank', 'BANK', '2026-01-01', '1000')
    food = c.categories.get_by_code('EXP.PERSONAL.FOOD')
    c.transactions.record_outflow('2026-02-01', bank.id, '12.34', food.id, counterparty='Example shop')
    c.planning.create(kind='BILL', name='Internet', amount='100', frequency='MONTHLY', start_date='2026-02-01')
    return bank


def _change(data, sheet, column, value):
    sheets = read_workbook(data)
    headers = sheets[sheet][0]
    sheets[sheet][1][headers.index(column)] = value
    return tabular_workbook_bytes([(name, rows[0], [tuple(row) for row in rows[1:]], [22]*len(rows[0]))
                                  for name, rows in sheets.items()])


def test_comprehensive_roundtrip_and_legacy_headers(c, tmp_path):
    _source(c)
    data, _, _ = export_all(c, 'xlsx')
    tables = export_tables(c)
    ledger = next(t for t in tables if t[0] == 'ledger_entries')
    assert ledger[1][:11] == ['Transaction ID', 'Transaction reference', 'Account', 'Date', 'Counterparty',
                            'Currency', 'Total in currency', 'FX rate', 'Total in default currency', 'Category L1', 'Category L2']
    assert any(row[2] == 'Example bank' and row[10] == 'Food & groceries' for row in ledger[2])
    target = build(tmp_path/'new.db', key=b'k' * 32)
    target.db.execute("INSERT INTO profile_identity(singleton,profile_id) VALUES(1,'00000000-0000-0000-0000-000000000001')")
    prepared = prepare_import(target, data)
    assert len(prepared) == 62  # property_contracts and property_flows (NF-12M) are the 60th and 61st, foreign_amounts (NF-7AK3) the 62nd
    assert target.db.scalar('SELECT count(*) FROM transactions') == 0
    confirm_import(target, data)
    assert target.db.scalar('SELECT profile_id FROM profile_identity') == '00000000-0000-0000-0000-000000000001'
    for name, headers, rows, _ in _raw_tables(c):
        if name != 'profile_identity':
            exported = next(t for t in _raw_tables(target) if t[0] == name)
            assert exported[1:3] == (headers, rows)
    with pytest.raises(ValueError, match='empty profile'):
        confirm_import(target, data)
    legacy = tabular_workbook_bytes([(name[:31], headers, rows, widths) for name, headers, rows, widths in _raw_tables(c)])
    old_target = build(tmp_path/'legacy.db')
    confirm_import(old_target, legacy)
    assert old_target.db.scalar('SELECT count(*) FROM transactions') == 2
    target.db.close(); old_target.db.close()


def test_invalid_workbook_is_atomic_and_readable_values_cannot_disagree(c, tmp_path):
    _source(c)
    data, _, _ = export_all(c, 'xlsx')
    target = build(tmp_path/'new.db')
    invalid = _change(data, 'ledger_entries', 'Total in currency', '999')
    with pytest.raises(ValueError, match='differs'):
        confirm_import(target, invalid)
    legacy = tabular_workbook_bytes([(name[:31], headers, rows, widths) for name, headers, rows, widths in _raw_tables(c)])
    for column, value, error in [('account_id','99999','points to a record'), ('fx_rate','0','inconsistent'),
                                  ('amount_base','999','base amount'), ('date','2026-02-30','real date'),
                                  ('asset_id', str(c.assets.cash_asset('USD').id), 'cash asset currency')]:
        with pytest.raises(ValueError, match=error):
            confirm_import(target, _change(legacy,'ledger_entries',column,value))
    assert target.db.scalar('SELECT count(*) FROM transactions') == 0
    with ZipFile(BytesIO(data)) as archive:
        out = BytesIO()
        with ZipFile(out,'w',ZIP_DEFLATED) as changed:
            for name in archive.namelist():
                content=archive.read(name)
                if name == 'xl/worksheets/sheet2.xml':
                    content=content.replace(b'<v>',b'<f>1+1</f><v>',1)
                changed.writestr(name,content)
    with pytest.raises(ValueError,match='formulas'):
        prepare_import(target,out.getvalue())
    target.db.close()


def test_import_upload_preview_confirm_and_replay(c, tmp_path):
    _source(c)
    data, _, _ = export_all(c,'xlsx')
    target=build(tmp_path/'new.db'); client=TestClient(create_app(target))
    assert client.get('/exports/import').status_code == 200
    assert client.get('/exports/import/template').status_code == 200
    preview=client.post('/exports/import',files={'workbook':('records.xlsx',data)})
    assert preview.status_code == 200,preview.text
    import re
    token=re.search(r'name="token" value="([^"]+)"',preview.text)[1]
    payload=re.search(r'name="payload" value="([^"]+)"',preview.text)[1]
    assert target.db.scalar('SELECT count(*) FROM transactions') == 0
    result=client.post('/exports/import',data={'action':'confirm','token':token,'payload':payload})
    assert result.status_code == 200,result.text
    assert 'Your data is ready' in result.text
    assert client.post('/exports/import',data={'action':'confirm','token':token,'payload':payload}).status_code == 400
    target.db.close()


def test_analysis_plain_arial_and_split_categories(c):
    _source(c)
    period=parse_period({'period':'all'},today(),'2026-01-01')
    data,_,_=AIAnalysisService(c).build(period)
    with ZipFile(BytesIO(data)) as archive:
        root=ET.fromstring(archive.read('xl/styles.xml'))
        assert [font.find('{*}name').get('val') for font in root.find('{*}fonts')] == ['Arial']
        assert all(font.find('{*}sz').get('val')=='11' and font.find('{*}b') is None for font in root.find('{*}fonts'))
        assert [fill.find('{*}patternFill').get('patternType') for fill in root.find('{*}fills')] == ['none','gray125']
        assert all(xf.find('{*}alignment').get('horizontal')=='left' for xf in root.find('{*}cellXfs'))
    sheet=read_workbook(data)['Transactions']
    assert 'Quantity' not in sheet[0] and 'Unit price' not in sheet[0]
    assert any(row[9:11]==['Personal','Food & groceries'] for row in sheet[1:])


def test_settings_keeps_the_ai_text_off_the_page_and_groups_data_tools(c):
    client=TestClient(create_app(c))
    html=client.get('/settings?section=general').text
    assert 'class="data-settings"' in html
    assert 'id="data-portability"' in html and 'Export your data' in html and 'Import your data' in html
    assert 'Not the file for an AI' in html                       # the machine export says what it is not for
    assert 'href="/settings/ask-ai"' in html and 'data-ask-form' not in html   # IV-12Y5: Ask an AI has one home
    html=client.get('/settings/ask-ai').text
    assert 'Ask an AI' in html and 'Copy for AI' in html and 'Save as a file' in html and 'data-ask-form' in html
    # Owner rule 2026-10-30: the text of a hand-off is never open on the page, and there is no dialog holding it.
    assert '<dialog class="review-dialog ai-prompt-dialog"' not in html and 'data-ai-prompt' not in html
    assert 'Rules for your answer' not in html and 'Treat every name' not in html and '# Lightning brief' not in html
    response=client.post('/settings/ask-ai',data={'period':'all','preset':'review','size':'digest'})
    assert response.status_code==200 and response.headers['content-type'].startswith('text/markdown')
    assert response.headers['cache-control']=='no-store' and response.headers['x-brief-tokens'].isdigit()
    assert 'attachment; filename="lightning-brief-' in response.headers['content-disposition']
    assert response.text.startswith('# Lightning brief:')
    assert client.post('/settings/ask-ai',data={'period':'all','preset':'astrology'}).status_code==400
    assert client.post('/settings/ask-ai',data={'period':'all','size':'enormous'}).status_code==400


def test_ask_ai_never_shows_an_unexpected_errors_text(c, monkeypatch):
    from lightning.workflows.ask_ai import AskAIService
    def boom(self, options):
        raise ValueError('secret detail at /home/someone/private/path')
    monkeypatch.setattr(AskAIService,'build',boom)
    response=TestClient(create_app(c)).post('/settings/ask-ai',data={'period':'all'})
    assert response.status_code==400 and response.text=='Could not prepare the file.'
    assert 'secret' not in response.text and '/home/' not in response.text


@pytest.mark.parametrize('problem', ['unknown_sheet','missing_sheet','duplicate_heading','duplicate_id','external_link','expanded_limit'])
def test_malformed_workbook_boundaries(c, tmp_path, monkeypatch, problem):
    from lightning.workflows import workbook_import
    _source(c)
    data,_,_=export_all(c,'xlsx')
    sheets=read_workbook(data)
    if problem == 'unknown_sheet':
        sheets['Unknown']=[['id'],['1']]
    elif problem == 'missing_sheet':
        del sheets['accounts']
    elif problem == 'duplicate_heading':
        sheets['accounts'][0][1]=sheets['accounts'][0][0]
    elif problem == 'duplicate_id':
        sheets['accounts'].append(sheets['accounts'][1][:])
    changed=tabular_workbook_bytes([(name,rows[0],[tuple(row) for row in rows[1:]],[22]*len(rows[0])) for name,rows in sheets.items()])
    if problem == 'external_link':
        output=BytesIO()
        with ZipFile(BytesIO(changed)) as source,ZipFile(output,'w',ZIP_DEFLATED) as result:
            for name in source.namelist():
                result.writestr(name,source.read(name))
            result.writestr('xl/externalLinks/_rels/externalLink1.xml.rels', '<Relationships><Relationship TargetMode="External" Target="https://example.invalid/"/></Relationships>')
        changed=output.getvalue()
    elif problem == 'expanded_limit':
        monkeypatch.setattr(workbook_import,'MAX_EXPANDED',1)
    target=build(tmp_path/'empty.db')
    with pytest.raises(ValueError):
        prepare_import(target,changed)
    assert target.db.scalar('SELECT count(*) FROM transactions') == 0
    target.db.close()


def test_custom_master_setup_is_not_overwritten(c):
    data,_,_=export_all(c,'xlsx')
    c.assets.create_investment('Custom fund','FUND.EQUITY','CUSTOM')
    with pytest.raises(ValueError,match='existing setup'):
        prepare_import(c,data)


def test_custom_nonledger_setup_is_not_overwritten(c):
    from lightning.workflows.workbook_import import _unused
    c.investments.set_target_weight('Stocks', Decimal('70'), c.assets.get_class_by_code('STOCK').id)
    with pytest.raises(ValueError, match='existing setup'):
        _unused(c)


def test_foreign_currency_import_preserves_fx_and_refreshes_profile_currency(c, tmp_path):
    from lightning.core.memo import request_cache
    c.currencies.register('USD')
    c.set_profile_currency('USD')
    c.currencies.register('EGP')
    c.fx.save('EGP', '2026-01-01', '0.021234')
    account = c.account_flows.open_account('Foreign bank', 'BANK', '2026-01-01', '1000', currency='EGP')
    category = c.categories.get_by_code('EXP.PERSONAL.FOOD')
    txn = c.transactions.record_outflow('2026-02-01', account.id, '10.25', category.id)
    data, _, _ = export_all(c, 'xlsx')
    target = build(tmp_path / 'foreign.db')
    try:
        with request_cache(target.db):
            assert target.base_currency == 'EGP'
            confirm_import(target, data)
            assert target.base_currency == target.transactions.base_currency == target.reporting.base_currency == 'USD'
        imported = target.transactions.get(txn.id)
        assert imported.lines[0].fx_rate == Decimal('0.021234')
        assert imported.lines[0].amount == Decimal('-10.25')
        assert imported.lines[0].amount_base == Decimal('-0.22')
        assert target.reporting.net_worth('2026-02-01').total == c.reporting.net_worth('2026-02-01').total
    finally:
        target.db.close()


@pytest.mark.parametrize('problem', ['default_currency', 'system_category'])
def test_required_currency_and_system_setup_are_validated(c, tmp_path, problem):
    tables = _raw_tables(c)
    changed = []
    for name, headers, rows, widths in tables:
        if name == 'settings' and problem == 'default_currency':
            rows = [tuple('XYZ' if header == 'value' and row[headers.index('key')] == 'base_currency' else value
                          for header, value in zip(headers, row)) for row in rows]
        if name == 'categories' and problem == 'system_category':
            rows = [row for row in rows if row[headers.index('code')] != 'INC.UNACCOUNTED']
        changed.append((name[:31], headers, rows, widths))
    target = build(tmp_path / 'required.db')
    try:
        with pytest.raises(ValueError, match='default currency|system categories'):
            confirm_import(target, tabular_workbook_bytes(changed))
        assert target.categories.get_by_code('INC.UNACCOUNTED')
        assert target.base_currency == 'EGP'
    finally:
        target.db.close()


def test_blank_required_text_and_plain_str_cells_import(c, tmp_path):
    """A workbook an AI tool filled (Open XML SDK) used t="str" text cells and left notes and an empty
    setting blank; Excel cannot keep an empty text, so the import refused it. Now it imports."""
    _source(c)
    data, _, _ = export_all(c, 'xlsx')
    data = _change(data, 'accounts', 'notes', None)
    output = BytesIO()
    with ZipFile(BytesIO(data)) as source, ZipFile(output, 'w', ZIP_DEFLATED) as result:
        for name in source.namelist():
            body = source.read(name)
            if name.startswith('xl/worksheets/'):
                body = body.replace(b't="inlineStr"', b't="str"')
                body = __import__('re').sub(rb'<is><t[^>]*>(.*?)</t></is>', rb'<v>\1</v>', body)
            result.writestr(name, body)
    assert read_workbook(output.getvalue())['accounts'][1] == read_workbook(data)['accounts'][1]
    target = build(tmp_path/'str.db')
    confirm_import(target, output.getvalue())
    assert target.db.scalar("SELECT notes FROM accounts WHERE name='Example bank'") == ''
    target.db.close()
    bad = BytesIO()  # an error cell (t="e") is still refused
    with ZipFile(BytesIO(data)) as source, ZipFile(bad, 'w', ZIP_DEFLATED) as result:
        for name in source.namelist():
            body = source.read(name)
            if name.startswith('xl/worksheets/'):
                body = body.replace(b't="inlineStr"', b't="e"', 1)
            result.writestr(name, body)
    with pytest.raises(ValueError, match='unsupported cell type'):
        read_workbook(bad.getvalue())


def test_dates_and_times_excel_turned_into_serial_numbers_come_back_as_text(c, tmp_path):
    """Excel saves a typed date or time as days since 1899-12-30; the import kept 46325.77 as a timestamp."""
    _source(c)
    data, _, _ = export_all(c, 'xlsx')
    data = _change(data, 'accounts', 'created_at', '46325.5')
    rows = read_workbook(data)['transactions']
    first = date.fromisoformat(rows[1][rows[0].index('date')])
    data = _change(data, 'transactions', 'date', str((first - date(1899, 12, 30)).days))
    target = build(tmp_path/'serial.db')
    confirm_import(target, data)
    assert target.db.scalar("SELECT created_at FROM accounts WHERE name='Example bank'").startswith('2026-10-30T12:00:00')
    assert target.db.scalar("SELECT min(date) FROM transactions") == first.isoformat()
    target.db.close()


def _edit(data, edits):
    """Change several cells at once: edits is [(sheet, row number, column, value)] with row 2 the first data row."""
    sheets = read_workbook(data)
    for sheet, number, column, value in edits:
        sheets[sheet][number - 1][sheets[sheet][0].index(column)] = value
    return tabular_workbook_bytes([(name, rows[0], [tuple(row) for row in rows[1:]], [22] * len(rows[0]))
                                  for name, rows in sheets.items()])


def test_every_problem_is_listed_with_its_sheet_row_and_column(c, tmp_path):  # BT-7AS1
    from lightning.workflows.workbook_import import WorkbookProblems
    _source(c)
    data, _, _ = export_all(c, 'xlsx')
    target = build(tmp_path / 'new.db', key=b'k' * 32)
    bad = _edit(data, [('transactions', 2, 'date', '31/12/2026'), ('accounts', 2, 'opening_date', 'soon'),
                       ('ledger_entries', 2, 'quantity', 'twelve')])
    with pytest.raises(WorkbookProblems) as caught:
        prepare_import(target, bad)
    lines = caught.value.problems
    assert len(lines) == 3 and "3 things" in str(caught.value)
    assert any(l.startswith('Sheet "transactions", row 2, column "date"') for l in lines)
    assert any(l.startswith('Sheet "accounts", row 2, column "opening_date"') for l in lines)
    assert any(l.startswith('Sheet "ledger_entries", row 2, column "quantity"') for l in lines)
    assert not any('NOT NULL' in l or 'constraint' in l for l in lines)
    assert target.db.scalar('SELECT count(*) FROM transactions') == 0


def test_a_blank_required_cell_and_a_repeated_id_are_named(c, tmp_path):  # BT-7AS1
    from lightning.workflows.workbook_import import WorkbookProblems
    _source(c)
    data, _, _ = export_all(c, 'xlsx')
    c.account_flows.open_account('Second bank', 'BANK', '2026-01-01', '5')
    data, _, _ = export_all(c, 'xlsx')
    rows = read_workbook(data)['accounts']
    target = build(tmp_path / 'new.db', key=b'k' * 32)
    first_id = rows[1][rows[0].index('id')]
    bad = _edit(data, [('accounts', 3, 'id', first_id), ('ledger_entries', 2, 'account_id', None)])
    with pytest.raises(WorkbookProblems) as caught:
        prepare_import(target, bad)
    text = ' | '.join(caught.value.problems)
    assert 'Sheet "accounts", row 3, column "id"' in text and 'already used in row 2' in text
    assert 'Sheet "ledger_entries", row 2, column "account_id": this cannot be empty' in text


def test_a_missing_reference_names_the_sheet(c, tmp_path):  # BT-7AS1
    from lightning.workflows.workbook_import import WorkbookProblems
    _source(c)
    legacy = tabular_workbook_bytes([(name[:31], headers, rows, widths) for name, headers, rows, widths in _raw_tables(c)])
    target = build(tmp_path / 'new.db', key=b'k' * 32)
    bad = _edit(legacy, [('ledger_entries', 2, 'account_id', 99999)])
    with pytest.raises(WorkbookProblems) as caught:
        prepare_import(target, bad)
    assert any('points to a record that is not on sheet "accounts"' in l for l in caught.value.problems)


def test_the_preview_page_lists_every_problem(c, tmp_path):  # BT-7AS1
    _source(c)
    data, _, _ = export_all(c, 'xlsx')
    bad = _edit(data, [('transactions', 2, 'date', 'nope'), ('accounts', 2, 'opening_date', 'soon')])
    fresh = build(tmp_path / 'new.db')
    client = TestClient(create_app(fresh))
    page = client.post('/exports/import', files={'workbook': ('w.xlsx', bad)})
    assert page.status_code == 400
    assert 'import-problems' in page.text and 'row 2, column &#34;date&#34;' in page.text or 'row 2, column "date"' in page.text


def test_the_review_lists_what_comes_in_not_table_names(c, tmp_path):  # BT-7AS2
    from lightning.workflows.workbook_import import review_summary
    _source(c)
    data, _, _ = export_all(c, 'xlsx')
    fresh = build(tmp_path / 'new.db')
    rows = dict(review_summary(prepare_import(fresh, data)))
    assert rows['Accounts'] == 1 and rows['Transactions'] >= 1 and rows['Bills and plans'] == 1
    assert 'Categories' in rows and all(' ' in label or label.isalpha() for label in rows)
    assert not any('_' in label for label in rows) and len(rows) < 13
    client = TestClient(create_app(fresh))
    page = client.post('/exports/import', files={'workbook': ('w.xlsx', data)})
    assert page.status_code == 200 and 'ledger_entries' not in page.text and 'bank_import_rows' not in page.text
    assert 'Bills and plans' in page.text


def test_what_excel_and_ai_tools_do_to_plain_values_is_put_back(c, tmp_path):  # BT-7AS3
    """A workbook shaped like an AI-filled one (made here, no real data): TRUE/FALSE for yes/no columns, numbers with
    thousands separators, spaces and Arabic digits, loose dates, a blank where Excel cannot keep an empty text."""
    _source(c)
    legacy = tabular_workbook_bytes([(name[:31], headers, rows, widths) for name, headers, rows, widths in _raw_tables(c)])
    sheets = read_workbook(legacy)
    ledger = sheets['ledger_entries']
    amount = Decimal(ledger[1][ledger[0].index('amount')])
    assert abs(amount) >= 1000
    target = build(tmp_path / 'new.db')
    quirky = _edit(legacy, [
        ('accounts', 2, 'active', 'TRUE'), ('accounts', 2, 'is_system', 'FALSE'), ('accounts', 2, 'cash_at_hand', ' no '),
        ('accounts', 2, 'opening_date', '2026/1/1'), ('accounts', 2, 'notes', None),
        ('ledger_entries', 2, 'amount', f' {amount:,.2f} '),
        ('ledger_entries', 2, 'quantity', f'{amount:,.2f}'.translate(str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩')).replace(',', '٬').replace('.', '٫')),
    ])
    assert prepare_import(target, quirky) == prepare_import(target, legacy)
    confirm_import(target, quirky)
    assert target.db.scalar("SELECT active FROM accounts WHERE name='Example bank'") == 1


def test_a_cell_of_spaces_is_a_blank_cell_not_a_number_error(c, tmp_path):  # BT-7AS3
    from lightning.workflows.workbook_import import WorkbookProblems
    _source(c)
    legacy = tabular_workbook_bytes([(name[:31], headers, rows, widths) for name, headers, rows, widths in _raw_tables(c)])
    target = build(tmp_path / 'new.db')
    with pytest.raises(WorkbookProblems) as caught:
        prepare_import(target, _edit(legacy, [('ledger_entries', 2, 'account_id', '   ')]))
    assert 'Sheet "ledger_entries", row 2, column "account_id": this cannot be empty' in caught.value.problems[0]


def test_either_workbook_goes_to_its_own_review_from_either_page(c, tmp_path):  # BT-7AS4
    from lightning.workflows import starter_workbook
    from lightning.workflows.workbook_import import workbook_kind
    _source(c)
    full, _, _ = export_all(c, 'xlsx')
    starter = starter_workbook.starter_workbook(c)
    assert workbook_kind(full) == 'full' and workbook_kind(starter) == 'starter'
    fresh = build(tmp_path / 'new.db')
    client = TestClient(create_app(fresh))
    wrong = client.post('/exports/starter', files={'workbook': ('full.xlsx', full)})  # a full workbook on the starter page
    assert wrong.status_code == 200 and 'Coming in' in wrong.text and 'no Entries sheet' not in wrong.text
    wrong = client.post('/exports/import', files={'workbook': ('starter.xlsx', starter)})  # a starter on the full page
    assert wrong.status_code == 200 and 'Unsupported sheet' not in wrong.text and 'not one of Lightning' not in wrong.text
