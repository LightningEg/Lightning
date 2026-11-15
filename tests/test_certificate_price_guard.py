"""BT-12AQ: a market quote cannot change contractual principal or invent a certificate gain."""
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app

DAY = '2026-09-02'


@pytest.fixture
def certificate(c):
    bank = c.account_flows.open_account('Certificate bank', 'BANK', '2026-09-01', '5000')
    account = c.account_flows.open_account('Certificates', 'DEPOSIT', '2026-09-01', '0', institution='Certificate bank')
    cd, _ = c.deposits.purchase(account.id, 'Contract certificate', '2026-09-01', '2026-09-01',
        '2027-09-01', '1000', '12', 'SIMPLE', 'AT_MATURITY', 'MONTHLY', bank.id, bank.id)
    return account, bank, cd.terms.asset_id, cd.terms.id


@pytest.mark.parametrize('source', ['MANUAL', 'ONLINE', 'MARKET', 'REEVALUATION_MANUAL'])
def test_certificate_rejects_generic_price_sources(c, certificate, source):
    account, _, asset_id, _ = certificate
    with pytest.raises(ValidationError, match='principal'):
        c.assets.set_price(asset_id, DAY, '2000', source=source)
    h = c.investments.portfolio(DAY, account.id).open[0]
    assert h.value == h.cost_basis == 1000 and h.unrealized == 0
    assert c.assets.price_history(asset_id) == []


@pytest.mark.parametrize('field', ['p', 'value', 'rp'])
def test_forged_certificate_price_inputs_refuse_the_whole_batch(c, certificate, field):
    account, _, asset_id, _ = certificate
    fund = c.assets.create_investment('Ordinary fund', 'FUND.EQUITY', 'CDGUARD')
    client = TestClient(create_app(c), follow_redirects=False)
    key = f'rp_{asset_id}_{DAY}' if field == 'rp' else f'{field}_{asset_id}'
    response = client.post('/investments/prices', data={'date': DAY, f'p_{fund.id}': '12', key: '2000'})
    assert response.status_code == 303 and '/prices?' in response.headers['location']
    assert c.assets.price_history(fund.id) == c.assets.price_history(asset_id) == []
    assert c.investments.portfolio(DAY, account.id).open[0].value == 1000


def test_csv_cannot_override_principal_and_ordinary_rows_are_atomic(c, certificate):
    _, _, asset_id, _ = certificate
    fund = c.assets.create_investment('Ordinary fund', 'FUND.EQUITY', 'CDCSV')
    csv = 'Name,Date,Price\nOrdinary fund,2026-09-02,12\nContract certificate,2026-09-02,2000\n'
    response = TestClient(create_app(c), follow_redirects=False).post('/investments/prices/csv',
        files={'file': ('quotes.csv', csv.encode(), 'text/csv')})
    assert response.status_code == 303 and 'principal' in response.headers['location']
    assert c.assets.price_history(fund.id) == c.assets.price_history(asset_id) == []


@pytest.mark.parametrize('phone', [False, True])
def test_certificate_has_no_editable_market_value_on_price_forms(c, certificate, phone):
    _, _, asset_id, _ = certificate
    app = create_app(c)
    if phone:
        @app.middleware('http')
        async def use_phone(request, call_next):
            request.state.phone = True
            return await call_next(request)
    html = TestClient(app).get('/investments/prices?date=' + DAY).text
    assert 'Contract certificate' in html
    assert f'name="p_{asset_id}"' not in html and f'name="value_{asset_id}"' not in html
    assert 'Set at purchase' in html


def test_previously_stored_bad_quote_cannot_invent_a_gain(c, certificate):
    account, _, asset_id, _ = certificate
    # Simulate a profile saved before the guard existed. Keep history, but never value the contract from it.
    c.assets.repo.upsert_price(asset_id, DAY, D('2000'), 'EGP', 'MANUAL')
    h = c.investments.portfolio(DAY, account.id).open[0]
    assert h.price == h.value == h.cost_basis == 1000
    assert h.unrealized == h.total_return == 0
    assert c.reporting.account_value(account.id, DAY) == 1000


def test_legacy_opening_certificate_also_ignores_market_quotes(c):
    bank = c.account_flows.open_account('Legacy bank', 'BANK', '2026-09-01', '100')
    account = c.account_flows.open_account('Legacy certificates', 'DEPOSIT', '2026-09-01', '0', institution='Legacy bank')
    cd, _ = c.deposits.record_owned(account.id, 'Legacy certificate', '2026-08-01', '2026-09-01',
        '2027-08-01', '2000', '12', 'SIMPLE', 'AT_MATURITY', 'MONTHLY', bank.id)
    c.assets.repo.upsert_price(cd.terms.asset_id, DAY, D('3000'), 'EGP', 'ONLINE')
    h = c.investments.portfolio(DAY, account.id).open[0]
    assert h.quantity == 1 and h.value == h.cost_basis == 2000 and h.unrealized == 0


def test_actual_redemption_still_records_the_real_proceeds(c, certificate):
    account, bank, asset_id, certificate_id = certificate
    c.deposits.redeem(certificate_id, DAY, '1050', bank.id)
    h = next(p for p in c.investments.portfolio(DAY, account.id).positions if p.asset_id == asset_id)
    assert h.quantity == 0 and h.realized == 50
    assert c.reporting.account_balance(bank.id, DAY) == 5050


def test_principal_dates_share_one_read_and_void_or_rollback_cannot_leave_stale_values(c, certificate):
    from lightning.core.memo import request_cache
    _, _, asset_id, _ = certificate
    purchase_id = c.deposits.certificate_for_asset(asset_id).terms.purchase_transaction_id
    with request_cache(c.db):
        statements = []
        c.db.conn.set_trace_callback(statements.append)
        try:
            assert c.reporting.q.certificate_principal(asset_id, '2026-08-31') is None
            for day in ('2026-09-01', DAY, '2026-09-30', '2026-10-31'):
                principal = c.reporting.q.certificate_principal(asset_id, day)
                assert principal == {'amount': 1_000_000_000, 'qty': 1_000_000, 'date': '2026-09-01'}
        finally:
            c.db.conn.set_trace_callback(None)
        assert sum(sql.lstrip().upper().startswith('SELECT') for sql in statements) == 1
        with pytest.raises(RuntimeError, match='roll back'):
            with c.db.transaction():
                c.transactions.void(purchase_id)
                assert c.reporting.q.certificate_principal(asset_id, DAY) is None
                raise RuntimeError('roll back')
        assert c.reporting.q.certificate_principal(asset_id, DAY)['amount'] == 1_000_000_000
        c.transactions.void(purchase_id)
        assert c.reporting.q.certificate_principal(asset_id, DAY) is None


def test_existing_inflated_checkpoint_is_rebuilt_on_upgrade_and_then_stays_idempotent(c, certificate, monkeypatch):
    import lightning.reevaluations as reevaluations
    account, bank, asset_id, _ = certificate
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-10-02')
    c.assets.repo.upsert_price(asset_id, '2026-09-30', D('2000'), 'EGP', 'MANUAL')
    original_price, original_dumps = c.reporting.valuer._price, reevaluations.json.dumps

    def legacy_payload(value, **kwargs):
        # The old fingerprint contained these seven inputs, with no valuation-rule revision.
        if isinstance(value, list) and value and value[0] == 'MONTH_END':
            value = value[:7]
        return original_dumps(value, **kwargs)

    with monkeypatch.context() as legacy:
        legacy.setattr(reevaluations.json, 'dumps', legacy_payload)
        legacy.setattr(c.reporting.valuer, '_price', lambda asset, day:
            (D('2000'), '2026-09-30', 'MANUAL') if asset.id == asset_id else original_price(asset, day))
        assert c.reevaluations.process_date('2026-09-30', 'MONTH_END')
    old = c.db.one('SELECT return_base_e6,journal_transaction_id FROM reevaluation_entries WHERE asset_id=?', (asset_id,))
    assert old['return_base_e6'] == 1_000_000_000

    c.reevaluations.process_due()
    row = c.db.one('SELECT value_base_e6,return_base_e6,journal_transaction_id FROM reevaluation_entries WHERE asset_id=?',
                   (asset_id,))
    assert row['value_base_e6'] == 1_000_000_000 and row['return_base_e6'] == 0
    assert c.transactions.get(old['journal_transaction_id']).is_void
    assert c.transactions.get(row['journal_transaction_id']).lines[0].amount_base == 0
    assert c.reporting.account_balance(bank.id, DAY) == 4000
    assert c.investments.portfolio('2026-10-02', account.id).open[0].value == 1000
    assert len(c.assets.price_history(asset_id)) == 1  # Preserve the original quote as history.
    journal_count = c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='VAL'")
    c.reevaluations.process_due()
    assert c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='VAL'") == journal_count
    assert c.db.scalar('SELECT journal_transaction_id FROM reevaluation_entries WHERE asset_id=?',
                       (asset_id,)) == row['journal_transaction_id']


def test_desktop_certificate_opens_its_actual_management_workflow(c, certificate, tmp_path):
    import re
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright, expect
    from tests.browser_support import require_chromium
    from lightning.runtime.http import Host
    account, _, asset_id, certificate_id = certificate
    host = Host(lambda cfg: create_app(c)).start()
    try:
        with sync_playwright() as pw:
            with pw.chromium.launch(executable_path=require_chromium(), args=['--no-sandbox']) as browser:
                page = browser.new_page(viewport={'width': 1366, 'height': 768})
                page.goto(host.origin + '/investments/prices?date=' + DAY)
                row = page.locator(f'#asset-{asset_id}')
                expect(row.locator('input')).to_have_count(0)
                expect(row.locator('[data-current-value]')).to_have_text('1,000 EGP')
                row.get_by_role('link', name='View certificate', exact=True).click()
                expect(page).to_have_url(re.compile(f'/deposits/{account.id}#certificate-{certificate_id}'))
                expect(page.locator('body')).to_contain_text('Contract certificate')
                page.wait_for_function("!document.getAnimations().some(a => a.playState === 'running')")
                page.screenshot(path=str(tmp_path / 'certificate-management-desktop.png'), animations='disabled')
    finally:
        host.stop()
