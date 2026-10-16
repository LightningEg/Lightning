"""Ordinary financial route handlers save pending intents across the domains."""
import asyncio
from urllib.parse import urlsplit

import httpx
import pytest

from test_journal_commands import full_devices
from test_journal_forms import accept
from lightning.runtime.journal_forms import JournalFormGate
from lightning.sync.journal.device import JournalDevice
from lightning.sync.journal.forms import issue_form
from lightning.ui.web import create_app


def case_form(c, case):
    accounts = {account.name: account.id for account in c.accounts.list()}
    bank, broker, cd, circle = (accounts[name] for name in ('Bank', 'Broker', 'Certificate', 'Circle'))
    food = c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    if case == 'account':
        return '/accounts/new', dict(name='Second bank', account_type='BANK', opening_balance='500', currency='EGP')
    if case == 'category':
        parent = c.categories.get_by_code('EXP.PERSONAL').id
        return f'/categories/new?parent={parent}', dict(name='Journal category', code='', confirm_similar='1')
    if case == 'person':
        return '/counterparties', dict(name='Journal tutor', kind='PERSON', counterparty_action='create')
    if case == 'asset':
        return '/investments/assets/new', dict(name='New stock', class_code='STOCK', symbol='NWT', currency='EGP')
    if case == 'trade':
        stock = next(asset for asset in c.assets.list_assets() if asset.ticker == 'JRN')
        return '/investments/new?kind=buy', dict(date='01/09/2026', account_id=str(broker), asset_id=str(stock.id),
            quantity='10', price='20', fees='2', total='202', cash_account_id='', notes='Purchase')
    if case == 'loan':
        return '/plan/purchases/new', dict(intent='save', name='Laptop', price='12000', fee='600', months='12',
            first_date='01/09/2026', account_id=str(bank))
    if case == 'reserve':
        return '/reserves', dict(name='Holiday', target='1000', allocated='100', recurrence='NONE')
    if case == 'budget':
        return f'/budget/limit/{food}', dict(month='2026-09', amount='450')
    if case == 'zakat':
        return '/zakat/enabled', dict(on='1')
    if case == 'fx':
        return '/settings/fx-rate', dict(currency='USD', date='01/09/2026', rate='50')
    if case == 'health':
        return '/settings/financial-health-limit', dict(key='debt_to_net_worth', value='25', alert='70')
    if case == 'certificate':
        return f'/deposits/{cd}/purchase', dict(name='One year', start_date='01/09/2026', lockup_end_date='01/10/2026',
            maturity_date='01/09/2027', principal='5000', annual_rate='12', interest_method='SIMPLE',
            payout_frequency='AT_MATURITY', compounding_frequency='MONTHLY', destination_account_id=str(bank), funding_account_id=str(bank))
    if case == 'circle':
        return f'/gameya/{circle}/terms', dict(organiser='Office', members='10', installment='1000', first_date='01/09/2026',
            my_turn='3', funding_account_id=str(bank), payout_account_id=str(bank), interest='none')
    raise AssertionError(case)


@pytest.mark.parametrize('case', ['account', 'category', 'person', 'asset', 'trade', 'loan', 'reserve', 'budget',
                                 'zakat', 'fx', 'health', 'certificate', 'circle'])
def test_native_financial_form_saves_pending_and_converges_without_service_replay(full_devices, case):
    home, peer, identities = full_devices
    c = peer.adapter.c
    device = JournalDevice(peer, identities[1])
    gate = JournalFormGate(create_app(c), device)
    path, data = case_form(c, case)
    token = issue_form(peer, urlsplit(path).path)
    before = peer.fingerprint()
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gate), base_url='http://testserver') as client:
            response = await client.post(path, data=data | dict(__journal_form=token))
            assert response.status_code == 303, response.text
            assert response.headers['location'].startswith('/edit-journal/'), response.headers['location']
            pending = await client.get(response.headers['location'])
            assert pending.status_code == 200
            assert pending.headers['X-Lightning-Journal'] == 'page'
            assert 'Financial changes' in pending.text and 'Pending' in pending.text
            assert '/edit-journal/devices' in pending.text
            assert 'href="/"' in pending.text  # Way back to the finance screens.
    asyncio.run(run())
    assert peer.fingerprint() == before
    wire, = peer.pending()
    accept(home, peer, wire)


def test_reading_plan_after_a_loan_is_confirmed_does_not_run_unjournaled_matching(full_devices):
    home, peer, identities = full_devices
    c = peer.adapter.c
    gate = JournalFormGate(create_app(c), JournalDevice(peer, identities[1]))
    path, data = case_form(c, 'loan')
    token = issue_form(peer, path)
    async def save():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gate), base_url='http://testserver') as client:
            assert (await client.post(path, data=data | dict(__journal_form=token))).status_code == 303
    asyncio.run(save())
    accept(home, peer, peer.pending()[0])
    before = peer.fingerprint(), peer.cursor()
    async def read():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gate), base_url='http://testserver') as client:
            for path in ('/', '/plan/loans', '/plan/recurring', '/budget'):
                response = await client.get(path)
                assert response.status_code == 200, (path, response.text[:200])
    asyncio.run(read())
    assert (peer.fingerprint(), peer.cursor()) == before


@pytest.mark.parametrize('path', ['/settings/fresh', '/settings/backup', '/settings/ai-analysis', '/investments/prices/online',
                                  '/investments/prices/market/import', '/accounts/1/import', '/history/undo'])
def test_unsafe_or_unadapted_file_and_legacy_operations_fail_before_dispatch(full_devices, path):
    home, peer, identities = full_devices
    c = peer.adapter.c
    gate = JournalFormGate(create_app(c), JournalDevice(peer, identities[1]))
    before = peer.fingerprint()
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gate), base_url='http://testserver') as client:
            assert (await client.post(path, data={})).status_code == 409
    asyncio.run(run())
    assert peer.fingerprint() == before
    assert peer.db.scalar('SELECT next_seq FROM journal_meta') == 1


def test_native_autosave_navigates_to_pending_then_confirms_through_same_window(tmp_path):
    from contextlib import asynccontextmanager
    import os
    from pathlib import Path
    import shutil
    from uuid import uuid4
    from starlette.responses import JSONResponse
    from lightning.bootstrap import build
    from lightning.runtime.http import Guard, Host
    from lightning.sync.identity import load_or_create
    from lightning.sync.journal.finance import initialize
    from lightning.sync.journal.full import enable
    from lightning.sync.journal.home import JournalHome
    browser_module = pytest.importorskip('playwright.sync_api')
    chromium = '/opt/pw-browsers/chromium' if Path('/opt/pw-browsers/chromium').exists() else shutil.which('chromium')
    if not chromium:
        pytest.skip('Chromium is unavailable')
    holder = {}
    def factory(credentials):
        app = create_app(None)
        @asynccontextmanager
        async def lifespan(_):
            # SQLCipher and every service are created/closed on the ASGI
            # owning thread, exactly as in the native profile lifecycle.
            c = build(tmp_path/'ledger.db', key=os.urandom(32))
            c.account_flows.open_account('Bank', 'BANK', '2026-01-01', '1000')
            party = c.counterparties.create('Tutor')
            identity = load_or_create(tmp_path/'identity', 'Home')
            store = initialize(c, profile=str(uuid4()), generation=str(uuid4()), device=identity.device_id,
                incarnation=str(uuid4()), home_key=identity.public_key, origin_key=identity.public_key,
                role='home', dummy_profile=True)
            enable(store)
            home = JournalHome(store, identity.sign)
            home.approve_origin(identity.device_id, store.config['incarnation'], identity.public_key)
            device = JournalDevice(store, identity, home)
            app.state.container = c
            gate = JournalFormGate(app, device)
            holder.update(c=c, party=party, gate=gate)
            try:
                async with gate.journal.router.lifespan_context(gate.journal):
                    yield
            finally:
                c.db.close()
        app.router.lifespan_context = lifespan
        @app.get('/__test/record')
        async def record():
            return JSONResponse(dict(name=holder['c'].counterparties.get(holder['party'])['name'],
                                     pending=len(holder['gate'].device.store.pending())))
        class Dispatch:
            async def __call__(self, scope, receive, send):
                target = app if scope['type'] == 'lifespan' else holder['gate']
                await target(scope, receive, send)
        return Guard(Dispatch(), credentials)
    host = Host(factory).start()
    try:
        with browser_module.sync_playwright() as browser_tools:
            browser = browser_tools.chromium.launch(executable_path=chromium, args=['--no-sandbox'])
            try:
                page = browser.new_page(viewport=dict(width=1366, height=800))
                page.goto(host.launch_url)
                page.goto(host.origin+'/counterparties')
                form = page.locator('form[data-counterparty-autosave]').first
                assert form.locator('input[name=__journal_form]').count() == 1
                form.locator('input[type=text]').fill('Tutor renamed')
                form.locator('input[type=text]').press('Tab')
                page.wait_for_url('**/edit-journal/**')
                assert 'Financial changes' in page.locator('body').inner_text()
                assert 'Pending' in page.locator('body').inner_text()
                record = page.evaluate("async () => (await fetch('/__test/record')).json()")
                assert record == dict(name='Tutor', pending=1)
                page.get_by_role('button', name='Sync now').click()
                page.wait_for_load_state('networkidle')
                record = page.evaluate("async () => (await fetch('/__test/record')).json()")
                assert record == dict(name='Tutor renamed', pending=0)
                assert 'Confirmed' in page.locator('body').inner_text()
                page.get_by_role('link', name='Overview', exact=True).click()
                page.wait_for_url(host.origin+'/')
            finally:
                browser.close()
    finally:
        host.stop()
