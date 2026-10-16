"""Full-domain actions have meaningful pending/refused/home-review screens."""
import asyncio
from uuid import uuid4

import httpx
import pytest

from test_journal_commands import full_devices
from lightning.sync.journal.codec import JournalError, origin_id, unpack
from lightning.sync.journal.device import JournalDevice
from lightning.ui.journal import create_journal_app


def setting(store, signer, value):
    return store.adapter.save_action([dict(command='profile.set_financial_setting',
        arguments=dict(key='investment_monthly_goal', value=value))], signer)


def test_pending_actions_show_names_and_values_on_distinct_pc_phone_rows(full_devices):
    home, peer, identities = full_devices
    wire = setting(peer, identities[1].sign, '700')
    device = JournalDevice(peer, identities[1])
    token = 't' * 40
    app = create_journal_app(device, session_token=token)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver',
                                     cookies=dict(journal_session=token)) as client:
            for agent, phone in [('Desktop', False), ('Android Mobile', True)]:
                response = await client.get('/', headers={'user-agent': agent})
                assert response.status_code == 200
                assert 'Financial changes' in response.text
                assert 'Monthly investment goal' in response.text and '700' in response.text
                assert 'Pending' in response.text
                assert ('phone-row' in response.text) == phone
                assert 'profile.set_financial_setting' not in response.text
    asyncio.run(run())
    assert peer.pending() == [wire]
    assert peer.adapter.c.settings.get('investment_monthly_goal') != '700'


def test_home_review_shows_current_financial_preference_and_original_proposal(full_devices):
    home, peer, identities = full_devices
    initial = setting(home.store, identities[0].sign, '500')
    home.receive(initial)
    home.process()
    for commit in home.store.commits_after(peer.cursor()):
        peer.apply(commit)
    remote = setting(peer, identities[1].sign, '700')
    own = setting(home.store, identities[0].sign, '600')
    home.receive(own)
    home.process()
    home.receive(remote)
    home.process()
    identifier = origin_id(unpack(remote)['body']['origin'])
    assert home.status(identifier)['status'] == 'review'
    device = JournalDevice(home.store, identities[0], home)
    token = 't' * 40
    app = create_journal_app(device, session_token=token)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver',
                                     cookies=dict(journal_session=token)) as client:
            response = await client.get('/review', headers={'user-agent': 'Android Mobile'})
            assert response.status_code == 200
            assert 'When you edited' in response.text and 'Proposed value' in response.text and 'Current value' in response.text
            assert '500' in response.text and '700' in response.text and '600' in response.text
            review = home.review_state(identifier)
            refused = await client.post('/review', data=dict(__session=token, command=str(uuid4()), proposal=identifier,
                                       token=review['token'], choice='reject'), headers=dict(origin='http://testserver'))
            assert refused.status_code == 303
    asyncio.run(run())
    for commit in home.store.commits_after(peer.cursor()):
        peer.apply(commit)
    assert peer.adapter.c.settings.get('investment_monthly_goal') == '600'
    assert JournalDevice(peer, identities[1]).view()[-1]['state'] == 'Not taken'
    with pytest.raises(JournalError, match='original screen'):
        JournalDevice(peer, identities[1]).add_again(identifier)


def test_expired_action_payload_keeps_readable_history_without_cash_edit_link(full_devices):
    home, peer, identities = full_devices
    wire = setting(home.store, identities[0].sign, '700')
    home.receive(wire)
    home.process()
    record = unpack(wire)['body']['record']
    with home.store.db.transaction():
        home.store.db.execute('UPDATE journal_records SET groups_json=? WHERE record_id=?', ('{"action":null}', record))
    device = JournalDevice(home.store, identities[0], home)
    row = device.view()[0]
    assert row['action_shown'] == [('History', 'Detailed changes have expired')]
    with pytest.raises(JournalError, match='original screen'):
        device.form_values(row['groups'])


def test_category_preferences_describe_names_instead_of_encoded_identifiers(full_devices):
    import json
    home, peer, identities = full_devices
    category = peer.adapter.c.categories.get_by_code('EXP.PERSONAL.FOOD')
    wire = peer.adapter.save_action([dict(command='profile.set_financial_setting',
        arguments=dict(key='budget_tracked_categories', value=json.dumps([category.id])))], identities[1].sign)
    device = JournalDevice(peer, identities[1])
    shown = device.describe(unpack(wire)['body']['groups'])
    assert ('Value', category.name) in shown
    assert all(peer.adapter.graph.uid('categories', category.id) not in value for _, value in shown)
    literal = str(uuid4())
    action = peer.adapter.save_action([dict(command='categories.create', arguments=dict(parent_id=category.parent_id, name=literal))], identities[1].sign)
    assert ('Name', literal) in device.describe(unpack(action)['body']['groups'])


def test_action_rows_fit_pc_and_phone_and_keep_headings_ink(full_devices):
    import functools
    import http.server
    from pathlib import Path
    import shutil
    import threading
    browser_tools_module = pytest.importorskip('playwright.sync_api')
    chromium = shutil.which('chromium') or shutil.which('chromium-browser')
    if Path('/opt/pw-browsers/chromium').exists():
        chromium = '/opt/pw-browsers/chromium'
    if not chromium:
        pytest.skip('Chromium is unavailable')
    home, peer, identities = full_devices
    setting(peer, identities[1].sign, '700')
    token = 't' * 40
    app = create_journal_app(JournalDevice(peer, identities[1]), session_token=token)
    async def pages():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver',
                                     cookies=dict(journal_session=token)) as client:
            return [(await client.get('/', headers={'user-agent': agent})).text
                    for agent in ('Desktop', 'Android Mobile')]
    desktop, phone = asyncio.run(pages())
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(Path(__file__).parents[1]/'lightning'/'ui'))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with browser_tools_module.sync_playwright() as browser_tools:
            browser = browser_tools.chromium.launch(executable_path=chromium, args=['--no-sandbox'])
            try:
                for width, html in ((1366, desktop), (360, phone), (320, phone)):
                    page = browser.new_page(viewport=dict(width=width, height=800))
                    page.set_content(html.replace('<head>', f'<head><base href="http://127.0.0.1:{server.server_port}/">'), wait_until='networkidle')
                    page.evaluate('document.fonts.ready')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    assert all(color == 'rgb(13, 34, 51)' for color in page.locator('h1, h2, h3').evaluate_all(
                        'nodes => nodes.map(node => getComputedStyle(node).color)'))
                    page.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
