"""Nearby pairing is the primary path; existing address/code sessions remain usable (BT-4L)."""
import re
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Credentials
from test_profile_app import create, token


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.details = []
        self.links = []
        self.forms = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'details':
            self.details.append('open' in attrs)
        elif tag == 'a':
            self.links.append((attrs.get('href'), attrs.get('class', ''), tuple(self.details)))
        elif tag == 'form':
            self.forms.append((attrs.get('action'), tuple(self.details)))

    def handle_endtag(self, tag):
        if tag == 'details':
            self.details.pop()


@pytest.fixture(params=[False, True], ids=['pc', 'phone'])
def device(request, tmp_path):
    cfg = Credentials('http://127.0.0.1:9868')
    devices = Devices(tmp_path / 'app', port=0, host='127.0.0.1')
    app = profile_app(cfg, tmp_path / 'profiles', devices=devices, phone=request.param)
    with TestClient(app, base_url=cfg.origin, headers={'Origin': cfg.origin}) as client:
        client.get('/__launch', params={'code': cfg.launch_code})
        yield client, app, devices, request.param


@pytest.mark.parametrize('locale', ['en', 'ar'])
def test_locked_picker_leads_to_nearby_pairing(device, locale):
    client, app, _, phone = device
    client.cookies.set('lightning_ui_locale', locale)
    page = client.get('/profiles')
    links = Links(page.text).links
    assert ('/profiles/journal/join', 'button button-primary', ()) in links
    if not phone:
        assert ('/profiles/connect', 'button button-secondary', (False,)) in links
    assert ('دور على موبايلك أو الكمبيوتر' if locale == 'ar' else 'Find your phone or PC') in page.text
    assert app.session.journal is None and app.session.container is None


def test_old_connect_address_keeps_manual_form_secondary_and_errors_visible(device):
    client, app, _, _ = device
    page = client.get('/profiles/connect')
    parsed = Links(page.text)
    assert ('/profiles/journal/join', 'button button-primary', ()) in parsed.links
    assert ('/profiles/connect', (False,)) in parsed.forms
    assert 'name="address"' in page.text and 'name="code"' in page.text
    refused = client.post('/profiles/connect', data={'csrf': token(page.text), 'address': '', 'code': '', 'pc_name': 'PC'})
    assert refused.status_code == 400
    assert ('/profiles/connect', (True,)) in Links(refused.text).forms
    assert app.session.journal is None


@pytest.mark.parametrize('locale', ['en', 'ar'])
def test_existing_profile_gets_explicit_setup_without_conversion(device, locale):
    client, app, _, phone = device
    create(client)
    settings = client.get('/settings')
    saved = client.post('/settings/locale', data={'__session': token(settings.text, '__session'), 'locale': locale})
    assert saved.status_code == 200
    client.cookies.set('lightning_ui_locale', locale)
    page = client.get('/profiles/devices')
    parsed = Links(page.text)
    setup = [item for item in parsed.links if item[0] == '/profiles/journal/setup']
    assert len(setup) == 1 and 'primary' in setup[0][1] and setup[0][2] == ()
    assert ('/profiles/devices/pair', (False,)) in parsed.forms
    assert ('جهّز الاقتران بالأجهزة القريبة' if locale == 'ar' else 'Set up nearby pairing') in page.text
    assert client.get('/profiles/journal/setup').status_code == 200
    assert app.session.journal is None
    if phone:
        settings = client.get('/settings').text
        assert ('اربط موبايلك أو الكمبيوتر' if locale == 'ar' else 'Pair your phone or PC') in settings


def test_pending_pairing_and_damaged_record_keep_the_existing_flow(device, monkeypatch):
    client, app, devices, _ = device
    create(client)
    page = client.get('/profiles/devices')
    pending = client.post('/profiles/devices/pair', data={'csrf': token(page.text), 'phone_name': 'Phone'})
    assert pending.status_code == 200
    assert re.search(r'[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}', pending.text)
    assert not any(link[0] == '/profiles/journal/setup' for link in Links(pending.text).links)
    monkeypatch.setattr(devices, 'lending_state', lambda paths: 'damaged')
    damaged = client.get('/profiles/devices')
    assert damaged.status_code == 200
    assert not any(link[0] == '/profiles/journal/setup' for link in Links(damaged.text).links)
    assert '/profiles/devices/keep-home' in damaged.text
    assert app.session.journal is None


def test_lent_profile_keeps_recovery_without_offering_conversion(device, tmp_path):
    from test_devices_app import app_for
    from test_profile_app import PASSWORD

    home, app, devices, _ = device
    create(home)
    pc, pc_app, cfg, _ = app_for(tmp_path, 'other-pc', 9877)
    with pc:
        pc.get('/__launch', params={'code': cfg.launch_code})
        page = home.get('/profiles/devices')
        pairing = home.post('/profiles/devices/pair', data={'csrf': token(page.text), 'phone_name': 'Home'})
        code = re.search(r'[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}', pairing.text).group()
        connect = pc.get('/profiles/connect')
        paired = pc.post('/profiles/connect', data={'csrf': token(connect.text), 'address': f'127.0.0.1:{devices.server.port}',
                                                    'code': code, 'pc_name': 'Other PC'})
        assert paired.status_code == 200
        listing = pc.get('/profiles').text
        profile = re.search(r'/profiles/borrowed\?id=([0-9a-f-]{36})', listing).group(1)
        opening = pc.get('/profiles/borrowed', params={'id': profile})
        opened = pc.post('/profiles/borrowed', data={'csrf': token(opening.text), 'id': profile, 'password': PASSWORD})
        assert opened.status_code == 200
        # Stop the completed pairing so this covers the no-pending, actively lent branch.
        page = home.get('/profiles/devices')
        home.post('/profiles/devices/stop-pairing', data={'csrf': token(page.text)})
        page = home.get('/profiles/devices')
        assert page.status_code == 200
        assert not any(link[0] == '/profiles/journal/setup' for link in Links(page.text).links)
        assert '/profiles/devices/take-back' in page.text
        assert app.session.journal is None and pc_app.session.journal is None
