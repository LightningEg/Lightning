"""Chromium acceptance for the isolated journal UI, including phone C05 targets."""
from __future__ import annotations

import shutil
import socket
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright

from test_journal_finance import devices as device_fixture


@pytest.fixture
def journal_server(tmp_path,request):
    executable = shutil.which("chromium") or "/opt/pw-browsers/chromium"
    if not Path(executable).exists():
        pytest.skip("Chromium is unavailable")
    from lightning.runtime.journal_lab import LabServer
    from lightning.ui.journal import create_journal_app
    import uvicorn
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    state = {}
    errors = []
    token = "browser-dummy-session-" + "s" * 40
    def run():
        fixture = None
        try:
            fixture = device_fixture.__wrapped__(tmp_path)
            home, pc = next(fixture)
            async def sync():
                pc.sync_with(home.home)
            from lightning.runtime.journal_pairing import NearbyPairing
            from lightning.sync.journal.membership import Membership
            from lightning.security.keys import create_key_file
            from lightning.sync.journal.codec import unpack
            import os
            members = {d.identity.device_id:dict(key=d.identity.public_key,incarnation=d.store.config["incarnation"]) for d in (home,pc)}
            if request.node.name.startswith("test_named_device"):
                members.pop(pc.identity.device_id)
                home.c.db.execute("DELETE FROM journal_origins WHERE device=?",(pc.identity.device_id,))
            secret = os.urandom(32)
            for device in (home,pc):
                Membership(device).initialize(members,secret)
            keys = create_key_file(home.c.db.copy_key(),"Pairing password","1234-5678-9012","School?","Cairo")
            hs = NearbyPairing(home,key_document=lambda:keys)
            hs.begin("Pairing password")
            state["code"] = hs.screen()["code"]
            candidate = unpack(hs.advertise("0"*64,47513))["body"] | dict(endpoint="https://127.0.0.1:47513/pairing/exchange")
            async def search(identity):
                return [candidate]
            def factory(endpoint,certificate,timeout):
                async def exchange(wire):
                    result = hs.exchange(wire)
                    state["digits"] = hs.screen()["digits"]
                    return result
                return exchange
            pairing = NearbyPairing(pc,search=search,client_factory=factory)
            app = create_journal_app(pc, session_token=token, synchronize=sync,pairing=pairing)
            server = LabServer(uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False, log_level="error"))
            state["server"] = server
            server.run()
        except BaseException as error:
            errors.append(error)
        finally:
            if fixture:
                try:
                    next(fixture)
                except StopIteration:
                    pass
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if errors or (state.get("server") and state["server"].started):
                break
            time.sleep(0.025)
        assert not errors, errors
        assert state.get("server") and state["server"].started
        yield f"http://127.0.0.1:{port}", token, executable, state
    finally:
        if state.get("server"):
            state["server"].should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()
        assert not errors, errors


@pytest.mark.parametrize("width,phone", [(1366, False), (360, True), (320, True)])
def test_capture_pending_balance_and_touch_layout(journal_server, width, phone):
    url, token, executable, _ = journal_server
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable)
        context = browser.new_context(viewport={"width": width, "height": 800},
                                      user_agent="Android Mobile" if phone else None)
        context.add_cookies([dict(name="journal_session", value=token, url=url, httpOnly=True, sameSite="Strict")])
        page = context.new_page()
        page.goto(url)
        if phone:
            assert page.locator("#entry").count() == 0
            page.get_by_role("link", name="Add", exact=True).click()
            assert page.locator("#balances").count() == 0
            assert page.locator("#amount").bounding_box()["height"] >= 56
        page.get_by_label("Account", exact=True).first.fill("Bank")
        page.get_by_label("Date", exact=True).fill("2026-09-01")
        page.get_by_label("Amount", exact=True).fill("-10.00")
        category = page.locator("#categories option").evaluate_all("nodes => nodes.map(n => n.value).find(v => v.startsWith('Food'))")
        page.get_by_label("Category", exact=True).first.fill(category)
        assert page.get_by_label("Date", exact=True).evaluate("n => getComputedStyle(n).backgroundColor") != "rgb(255, 255, 255)"
        page.get_by_role("button", name="Save", exact=True).click()
        page.get_by_text("Saved on this device · Pending", exact=True).wait_for()
        page.goto(url + "/balances")
        page.get_by_role("button", name="Sync now", exact=True).click()
        page.get_by_text("990 EGP", exact=True).wait_for()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if phone:
            page.get_by_role("link", name="Register", exact=True).last.click()
            assert all(height >= 56 for height in page.locator(".phone-row").evaluate_all("nodes=>nodes.map(n=>n.getBoundingClientRect().height)"))
        browser.close()


@pytest.mark.parametrize("width,phone", [(1366,False),(360,True),(320,True)])
def test_named_device_numeric_pairing_layout(journal_server,width,phone):
    url,token,executable,state = journal_server
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable)
        context = browser.new_context(viewport={"width":width,"height":800},user_agent="Android Mobile" if phone else None)
        context.add_cookies([dict(name="journal_session",value=token,url=url,httpOnly=True,sameSite="Strict")])
        page = context.new_page()
        page.goto(url + "/devices")
        page.get_by_role("button",name="Pair with",exact=False).wait_for()
        assert not page.locator('input[name="code"],input[name="address"],input[name="port"]').count()
        page.get_by_role("button",name="Pair with",exact=False).click()
        page.get_by_text("Select the number shown on the other device.",exact=True).wait_for()
        choices = page.locator('button[name="digits"]')
        assert choices.count() == 3
        assert not page.get_by_label("Profile password").count()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if phone:
            assert all(box["height"] >= 48 for box in choices.evaluate_all("nodes=>nodes.map(n=>n.getBoundingClientRect().toJSON())"))
        digits = state["digits"]
        page.locator(f'button[name="digits"][value="{digits}"]').click()
        page.get_by_label("Profile password").fill("Pairing password")
        page.get_by_role("button",name="Continue").click()
        page.get_by_text("Confirm on the home. This screen will continue automatically.",exact=True).wait_for()
        assert page.locator("[data-pairing-pending] strong").inner_text().replace(" ","").isdigit()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=f"/tmp/lightning-4d-harness-{width}.png",full_page=True)
        browser.close()
