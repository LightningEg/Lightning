"""Actual native first-enrollment and Devices pages discover and match in Chromium."""
import shutil
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright

from test_journal_finance import devices as device_fixture
from test_journal_nearby import setup


@pytest.fixture
def native_pairing_server(tmp_path):
    executable = shutil.which("chromium")
    if not executable:
        pytest.skip("Chromium unavailable")
    probe = socket.socket()
    probe.bind(("127.0.0.1",0))
    port = probe.getsockname()[1]
    probe.close()
    state, errors = {}, []
    def run():
        fixture = device_fixture.__wrapped__(tmp_path)
        try:
            from fastapi import FastAPI, Request
            from fastapi.staticfiles import StaticFiles
            import uvicorn
            from lightning.runtime.journal_lab import LabServer
            from lightning.runtime.journal_enrollment import NewJournalReplica
            from lightning.runtime.journal_enrollment_routes import journal_enrollment_router
            from lightning.runtime.journal_ui_routes import journal_ui_router
            from lightning.sync.journal.codec import unpack
            devices = next(fixture)
            home, _ = devices
            pairing = setup(devices)
            pairing.begin("Pairing password")
            candidate = unpack(pairing.advertise("0"*64,47513))["body"] | dict(endpoint="https://127.0.0.1:47513/pairing/exchange")
            async def search(identity):
                return [candidate]
            def factory(endpoint,certificate,timeout):
                async def exchange(wire):
                    return pairing.enrollment.exchange(wire) if endpoint.endswith('/enrollment/exchange') else pairing.exchange(wire)
                return exchange
            replica = NewJournalReplica(tmp_path/'first-native-copy',"New laptop",search=search,client_factory=factory)
            locked = SimpleNamespace(container=None, paths=None, root=tmp_path/'profiles',csrf='test-native-csrf',enrollment=replica)
            native = SimpleNamespace(token='test-native-token',container=None,journal=SimpleNamespace(device=home,pairing=pairing,trust=None))
            app = FastAPI()
            @app.middleware("http")
            async def device_frame(request: Request, call_next):
                request.state.phone = "Mobile" in request.headers.get("user-agent","")
                return await call_next(request)
            app.mount('/static',StaticFiles(directory=Path(__file__).parents[1]/'lightning/ui/static'),name='static')
            app.include_router(journal_ui_router(native))
            app.include_router(journal_enrollment_router(locked))
            server = LabServer(uvicorn.Config(app,host='127.0.0.1',port=port,access_log=False,log_level='error'))
            state['server'] = server
            server.run()
        except BaseException as exc:
            errors.append(exc)
        finally:
            try:
                next(fixture)
            except StopIteration:
                pass
    thread = threading.Thread(target=run,daemon=True)
    thread.start()
    try:
        for _ in range(240):
            if errors or state.get('server') and state['server'].started:
                break
            time.sleep(.025)
        assert not errors, errors
        assert state.get('server') and state['server'].started
        yield f'http://127.0.0.1:{port}', executable
    finally:
        if state.get('server'):
            state['server'].should_exit = True
        thread.join(10)
        assert not thread.is_alive()
        assert not errors, errors


@pytest.mark.parametrize('width,phone',[(1366,False),(360,True),(320,True)])
def test_native_discovery_number_choices_and_password(native_pairing_server,width,phone):
    url, executable = native_pairing_server
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable)
        context = browser.new_context(viewport=dict(width=width,height=900),user_agent='Android Mobile' if phone else None)
        home = context.new_page()
        home.goto(url+'/journal/devices')
        joining = context.new_page()
        joining.goto(url+'/profiles/journal/join')
        joining.get_by_role('button',name='Pair with this device').wait_for()
        assert joining.locator('input[name="code"]').count() == 0
        joining.get_by_role('button',name='Pair with this device').click()
        choices = joining.locator('button[name="digits"]')
        assert choices.count() == 3
        assert len(set(choices.all_text_contents())) == 3
        assert joining.locator('input[name="digits"], input[name="password"]').count() == 0
        joining.screenshot(path=f'/tmp/lightning-4d-native-{width}.png',full_page=True)
        assert joining.evaluate('document.documentElement.scrollWidth <= innerWidth'), joining.locator('*').evaluate_all('nodes=>nodes.filter(n=>n.getBoundingClientRect().right>innerWidth).map(n=>[n.tagName,n.className,n.getBoundingClientRect().right,n.textContent.slice(0,80)])')
        # The existing home notices the incoming request through its own polling.
        home.bring_to_front()
        home.get_by_role('button',name='Approve this device').wait_for()
        digits = home.locator('input[name="digits"]').input_value()
        home.screenshot(path=f'/tmp/lightning-4d-home-{width}.png',full_page=True)
        joining.bring_to_front()
        joining.locator(f'button[name="digits"][value="{digits}"]').click()
        joining.get_by_label('Profile password',exact=True).fill('Pairing password')
        joining.get_by_role('button',name='Continue',exact=True).click()
        joining.get_by_role('heading',name='Waiting for the home device').wait_for()
        home.bring_to_front()
        home.get_by_role('button',name='Approve this device').click()
        # First enrollment retains the password required to unwrap the checkpoint.
        joining.bring_to_front()
        assert joining.get_by_label('Profile password',exact=True).count() == 1
        denied = joining.request.post(url+'/profiles/journal/join/poll',form={'csrf':'wrong'})
        assert denied.status == 400
        native_denied = joining.request.post(url+'/journal/devices/poll',form={'__session':'wrong'})
        assert not native_denied.headers.get('content-type','').startswith('application/json')
        browser.close()
