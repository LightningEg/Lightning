"""Comprehensive workbook portability: values, joins, validation and confirmation."""
from io import BytesIO
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
    assert any(row[2] == 'Example bank' and row[10] == 'Food & Groceries' for row in ledger[2])
    target = build(tmp_path/'new.db', key=b'k' * 32)
    target.db.execute("INSERT INTO profile_identity(singleton,profile_id) VALUES(1,'00000000-0000-0000-0000-000000000001')")
    prepared = prepare_import(target, data)
    assert len(prepared) == 57
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
    for column, value, error in [('account_id','99999','missing reference'), ('fx_rate','0','inconsistent'),
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
    assert any(row[9:11]==['Personal','Food & Groceries'] for row in sheet[1:])


def test_settings_keeps_prompt_in_dialog_and_groups_data_tools(c):
    html=TestClient(create_app(c)).get('/settings?section=general').text
    assert 'class="data-settings"' in html
    assert 'id="data-portability"' in html and 'Export your data' in html and 'Import your data' in html
    assert '<dialog class="review-dialog ai-prompt-dialog"' in html
    assert html.index('data-ai-dialog') < html.index('data-ai-prompt') < html.index('</dialog>')
    assert 'Copy AI prompt' in html and 'Edit AI prompt' in html


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
