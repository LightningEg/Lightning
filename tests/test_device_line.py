"""Rendered device banners retain their action, translate and escape peer names."""
from types import SimpleNamespace
import shutil

import pytest
from fastapi.testclient import TestClient

from lightning.runtime.app import SessionGate
from lightning.runtime.http import Credentials, Guard, Host
from lightning.runtime.roles import SessionRole
from lightning.sync.state import HomeState
from lightning.ui.web import create_app


def banner_app(c, *, phone=False, lent=False, name="Office PC"):
    session = SimpleNamespace(container=c, paths=SimpleNamespace(profile=None), journal=None,
                              borrowed=None if lent else object(), borrowed_home=name,
                              role=SessionRole.READER if lent else SessionRole.BORROWER,
                              token="test-banner-session", csrf="test-banner-csrf")
    node = SimpleNamespace(model=SimpleNamespace(state=HomeState.LENT,
                            active=SimpleNamespace(grant=SimpleNamespace(borrower_id="pc"))),
                           store=SimpleNamespace(peer=lambda _: SimpleNamespace(name=name)))
    app = create_app(c)

    @app.get("/profiles/health")
    async def health():
        return {"locked": False, "session": session.token}

    gate = SessionGate(app, session)
    gate.phone = phone
    gate.devices = SimpleNamespace(lending_state=lambda _: "ok", home_node=lambda _: node)
    return gate


@pytest.fixture
def browser():
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    if not shutil.which("chromium"):
        pytest.skip("Chromium is not installed")
    with sync_playwright() as p:
        with p.chromium.launch(executable_path=shutil.which("chromium"), args=["--no-sandbox"]) as browser:
            yield browser


@pytest.mark.parametrize("phone", [False, True])
@pytest.mark.parametrize("lent", [False, True])
def test_arabic_banner_stays_in_flow_after_notices_expire(c, browser, phone, lent):
    c.settings.set("locale", "ar")
    gate = banner_app(c, phone=phone, lent=lent, name="Office-PC-" * 20)
    host = Host(lambda cfg: Guard(gate, cfg)).start()
    try:
        page = browser.new_page(viewport={"width": 320 if phone else 1280, "height": 900})
        page.clock.install(time=1000)
        page.clock.pause_at(2000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(host.launch_url)
        page.goto(f"{host.origin}/accounts")
        page.evaluate('sessionStorage.setItem("lightning-popup-success", "Saved")')
        response = page.reload()
        assert response.status == 200, response.text()
        assert page.locator(".flash:not(.device-line)").count() == 1
        page.clock.fast_forward(6000)
        banner = page.locator(".device-line")
        assert banner.is_visible()
        assert banner.evaluate("el => getComputedStyle(el).position") == "static"
        assert page.locator(".flash:not(.device-line)").count() == 0
        text = banner.inner_text()
        assert "Office-PC-" in text
        assert "Lent to" not in text and "Borrowed from" not in text and "read only" not in text
        action = banner.locator('a[href="/profiles/devices"]') if lent else banner.locator('form[action="/sync/hand-back"]')
        assert action.is_visible()
        if not lent:
            assert action.locator('input[name="__session"]').input_value() == gate.session.token
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors
        page.close()
    finally:
        host.stop()


@pytest.mark.parametrize("phone", [False, True])
@pytest.mark.parametrize("locale", ["en", "ar"])
@pytest.mark.parametrize("lent", [False, True])
@pytest.mark.parametrize("name", ['<img src=x onerror="alert(1)"> {name}', "Settings"])
def test_custom_device_name_cannot_inject_markup_or_format_fields(c, phone, locale, lent, name):
    c.settings.set("locale", locale)
    gate = banner_app(c, phone=phone, lent=lent, name=name)
    with TestClient(gate, base_url="http://127.0.0.1") as client:
        html = client.get("/accounts").text
    from markupsafe import escape
    import re
    banner_text = re.search(r'class="flash device-line"[^>]*><span>(.*?)</span>', html, re.S).group(1)
    assert str(escape(name)) in banner_text
    assert '<img' not in banner_text
    if not lent:
        assert f'name="__session" value="{gate.session.token}"' in html


def test_hand_back_still_requires_the_current_profile_token(c):
    gate = banner_app(c)
    cfg = Credentials("http://127.0.0.1:9876")
    with TestClient(Guard(gate, cfg), base_url=cfg.origin, headers={"Origin": cfg.origin}) as client:
        client.get("/__launch", params={"code": cfg.launch_code})
        for values in ({}, {"__session": "stale-profile"}):
            response = client.post("/sync/hand-back", data=values)
            assert response.status_code == 403
            assert "form expired" in response.text


def test_popup_success_preserves_phone_undo_as_well_as_device_action(c, setup, browser):
    bank = setup[0]['cib']
    txn = c.transactions.record_outflow('2026-09-03', bank.id, '10', setup[1]['EXP.PERSONAL.FOOD'].id,
                                        notes='original')
    gate = banner_app(c, phone=True)
    host = Host(lambda cfg: Guard(gate, cfg)).start()
    try:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(host.launch_url)
        response = page.request.post(f'{host.origin}/transactions/bulk-edit', headers={'Origin': host.origin}, form={
            '__session': gate.session.token, 'txn_ids': str(txn.id), 'notes': 'changed',
            'back': f'/accounts/{bank.id}'})
        assert response.ok, response.text()
        assert c.transactions.get(txn.id).notes == 'changed'
        page.goto(f'{host.origin}/accounts/{bank.id}?msg=Saved')
        page.evaluate('sessionStorage.setItem("lightning-popup-success", "Saved from popup")')
        page.reload()
        assert page.locator('.device-line form[action="/sync/hand-back"]').is_visible()
        undo = page.locator('form[action="/history/undo"] button')
        assert undo.is_visible()
        undo.click()
        page.wait_for_url('**/?msg=*')
        assert c.transactions.get(txn.id).notes == 'original'
        assert c.reporting.account_balance(bank.id) == 49990
        page.close()
    finally:
        host.stop()


def test_read_only_refusal_formats_the_peer_without_translating_its_name(c):
    gate = banner_app(c, lent=True, name='Settings')
    with TestClient(gate, base_url='http://127.0.0.1') as client:
        response = client.post('/transactions/bulk-delete', headers={'X-Requested-With': 'fetch'})
    assert response.status_code == 403
    assert 'Lent to Settings' in response.text
    assert '{name}' not in response.text


@pytest.mark.parametrize('lent', [False, True])
def test_missing_device_name_keeps_a_translated_system_fallback(c, lent):
    c.settings.set('locale', 'ar')
    gate = banner_app(c, lent=lent, name='')
    if lent:
        node = gate.devices.home_node(None)
        node.store.peer = lambda _: None
        from lightning.runtime.devices import home_state_line
        assert home_state_line(node) == 'Lent to a PC · read only'
    with TestClient(gate, base_url='http://127.0.0.1') as client:
        html = client.get('/accounts').text
    import re
    banner_text = re.search(r'class="flash device-line"[^>]*><span>(.*?)</span>', html, re.S).group(1)
    assert 'Borrowed' not in banner_text and 'Lent' not in banner_text
    assert 'your phone' not in banner_text and 'a PC' not in banner_text
    assert ('كمبيوتر' if lent else 'موبايلك') in banner_text
