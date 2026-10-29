import re

from fastapi.testclient import TestClient

from lightning.runtime.app import profile_app
from lightning.runtime.http import Credentials, MAX_BODY

PASSWORD = "a correct long passphrase"
SECRET = {"question": "What was the name of your first school?", "answer": "El Orman"}


def token(text, name="csrf"):
    match = re.search(r'name="' + name + r'" value="([^"]+)"', text)
    assert match, text[:500]
    return match.group(1)


def start(tmp_path):
    cfg = Credentials("http://127.0.0.1:9876")
    app = profile_app(cfg, tmp_path / "Documents" / "Lightning")
    return TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}), app, cfg


def recovery_shown(text):
    return re.search(r'aria-label="Recovery key">([0-9-]+)<', text).group(1)


def create(browser, name="Home", currency="EGP"):
    page = browser.get("/profiles/new")
    csrf = token(page.text)
    page = browser.post("/profiles/new", data={"csrf": csrf, "name": name, "currency": currency,
                                                "password": PASSWORD, "confirm": PASSWORD, **SECRET})
    assert page.status_code == 200, page.text
    assert "Save your recovery key" in page.text
    csrf = token(page.text)
    response = browser.post("/profiles/confirm", data={"csrf": csrf, "recovery": recovery_shown(page.text)})
    assert response.status_code == 200, response.text
    return response


def test_real_finance_profile_flow_and_stale_form_rejection(tmp_path):
    browser, app, cfg = start(tmp_path)
    with browser:
        assert browser.get("/").status_code == 403
        assert browser.get("/__launch", params={"code": cfg.launch_code}).status_code == 200
        assert browser.get("/").url.path == "/profiles"
        create(browser)
        page = browser.get("/accounts/new")
        old_token = token(page.text, "__session")
        response = browser.post("/accounts/new", data={"__session": old_token, "name": "My wallet", "account_type": "CASH", "currency": "EGP", "opening_balance": "0", "opening_date": "2026-09-30"})
        assert response.status_code == 200, response.text
        assert "My wallet" in browser.get("/accounts").text
        first_path = app.session.paths.db_path
        csrf = token(browser.get("/profiles").text)
        browser.post("/profiles/lock", data={"csrf": csrf})
        assert app.session.container is None
        assert browser.get("/accounts").url.path == "/profiles"
        create(browser, "Second")
        assert "My wallet" not in browser.get("/accounts").text
        assert browser.post("/accounts/new", data={"__session": old_token, "name": "Wrong profile"}).status_code == 403
        csrf = token(browser.get("/profiles").text)
        browser.post("/profiles/lock", data={"csrf": csrf})
        csrf = token(browser.get("/profiles/unlock", params={"db": str(first_path)}).text)
        page = browser.post("/profiles/unlock", data={"csrf": csrf, "db": str(first_path), "password": PASSWORD})
        assert page.status_code == 200, page.text
        assert "My wallet" in browser.get("/accounts").text
    assert app.session.container is None


def test_the_unlock_form_sent_twice_opens_the_profile_not_an_error(tmp_path):
    """BT-2AC (#193): Enter and then a click on Unlock sent the form twice; the second, with the token the first
    renewed, showed "This form expired". It now opens the app, or shows the form again while still locked."""
    browser, app, cfg = start(tmp_path)
    with browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        path = app.session.paths.db_path
        browser.post("/profiles/lock", data={"csrf": token(browser.get("/profiles").text)})
        form = {"csrf": token(browser.get("/profiles/unlock", params={"db": str(path)}).text), "db": str(path),
                "password": PASSWORD}
        assert browser.post("/profiles/unlock", data=form, follow_redirects=False).status_code == 303
        again = browser.post("/profiles/unlock", data=form, follow_redirects=False)
        assert again.status_code == 303 and again.headers["location"] == "/"
        assert app.session.container is not None
        browser.post("/profiles/lock", data={"csrf": token(browser.get("/profiles").text)})
        stale = browser.post("/profiles/unlock", data=form, follow_redirects=False)  # locked again: the form, empty
        assert stale.status_code == 303 and stale.headers["location"].startswith("/profiles/unlock?db=")
        page = browser.get(stale.headers["location"])
        assert page.status_code == 200 and PASSWORD not in page.text and app.session.container is None
        assert browser.post("/profiles/new", data={"csrf": "invalid"}).status_code == 403  # other forms unchanged
        assert "busy-toast" not in page.text and "/static/app.js?v=" in page.text  # app.js guards the button

def test_profile_setup_sets_the_chosen_currency(tmp_path):
    browser, app, cfg = start(tmp_path)
    with browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        setup = browser.get("/profiles/new").text
        assert 'name="currency"' in setup
        assert "USD — US Dollar" in setup
        create(browser, currency="USD")
        # The encrypted ledger stays on the app's own thread, so read the currency through a screen, as the user does.
        assert 'data-base-currency="USD"' in browser.get("/accounts").text


def test_host_auth_origin_and_body_limits(tmp_path):
    browser, app, cfg = start(tmp_path)
    with browser:
        assert browser.get("/static/profiles.css").status_code == 403
        assert browser.get("/profiles", headers={"Host": "localhost:9876"}).status_code == 400
        browser.get("/__launch", params={"code": cfg.launch_code})
        assert browser.get("/__launch", params={"code": cfg.launch_code}).status_code == 403
        assert browser.get("/profiles", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
        assert browser.post("/profiles/lock", headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "same-origin"}).status_code == 403
        assert browser.post("/profiles/new", content=b"x" * (MAX_BODY + 1)).status_code == 413
        assert browser.post("/profiles/new", data={"csrf": "invalid"}).status_code == 403
        response = browser.get("/profiles/new")
        assert response.headers["cache-control"] == "no-store"
        static = browser.get("/static/app.js")
        assert static.status_code == 200
        assert static.headers["cache-control"] == "private, max-age=86400"  # app files only; pages stay no-store
        assert response.headers["referrer-policy"] == "same-origin"
        assert "script-src-attr 'none'" in response.headers["content-security-policy"]
        assert "script-src 'self' 'nonce-" in response.headers["content-security-policy"]
        assert not app.session.root.exists()


def test_escaped_paths_and_failed_passwords_do_not_leak(tmp_path):
    browser, app, cfg = start(tmp_path)
    with browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        page = browser.get("/profiles/unlock", params={"db": '<script>alert("x")</script>'})
        assert '<script>alert("x")</script>' not in page.text
        csrf = token(page.text)
        page = browser.post("/profiles/new", data={"csrf": csrf, "name": "Home", "password": "never echo this password", "confirm": "mismatch", **SECRET})
        assert page.status_code == 400
        assert "never echo this password" not in page.text


def test_restore_chooser_requires_explicit_confirmation(tmp_path):
    browser, app, cfg = start(tmp_path)
    with browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        live_path = app.session.paths.db_path
        backup_path = browser.portal.call(app.session.container.backup_now)
        csrf = token(browser.get("/profiles").text)
        browser.post("/profiles/lock", data={"csrf": csrf})
        chooser = browser.get("/profiles")
        assert "Restore" in chooser.text
        page = browser.get("/profiles/restore", params={"db": str(live_path),
                                                       "backup": str(backup_path)})
        assert page.status_code == 200
        assert "Replace this profile with the selected backup" in page.text
        denied = browser.post("/profiles/restore", data={
            "csrf": token(page.text), "db": str(live_path), "backup": str(backup_path),
            "password": PASSWORD,
        })
        assert denied.status_code == 400
        assert "Confirm that this backup" in denied.text
        assert app.session.container is None


def test_restore_screen_replaces_only_after_confirmed_encrypted_backup(tmp_path):
    browser, app, cfg = start(tmp_path)
    with browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        live_path = app.session.paths.db_path
        browser.portal.call(app.session.container.settings.set, "restore_ui_marker", "saved version")
        backup_path = browser.portal.call(app.session.container.backup_now)
        browser.portal.call(app.session.container.settings.set, "restore_ui_marker", "newer version")
        csrf = token(browser.get("/profiles").text)
        browser.post("/profiles/lock", data={"csrf": csrf})
        page = browser.get("/profiles/restore", params={"db": str(live_path),
                                                       "backup": str(backup_path)})
        restored = browser.post("/profiles/restore", data={
            "csrf": token(page.text), "db": str(live_path), "backup": str(backup_path),
            "password": PASSWORD, "confirm": "yes",
        })
        assert restored.status_code == 200, restored.text
        assert "Backup restored" in restored.text
        assert app.session.container is None
        unlocked = browser.post("/profiles/unlock", data={
            "csrf": token(restored.text), "db": str(live_path), "password": PASSWORD,
        })
        assert unlocked.status_code == 200, unlocked.text
        assert browser.portal.call(app.session.container.settings.get, "restore_ui_marker") == "saved version"


def test_restore_repair_screen_requires_confirmation_and_finishes_pending_operation(tmp_path, monkeypatch):
    from lightning.database.promotion import SqlitePromotionJournalStore

    browser, app, cfg = start(tmp_path)
    with browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        live_path = app.session.paths.db_path
        backup_path = browser.portal.call(app.session.container.backup_now)
        csrf = token(browser.get("/profiles").text)
        browser.post("/profiles/lock", data={"csrf": csrf})

        original_prepare = SqlitePromotionJournalStore.prepare
        injected = {"done": False}

        def fail_after_p1(self, journal):
            result = original_prepare(self, journal)
            if not injected["done"]:
                injected["done"] = True
                raise OSError("injected interruption")
            return result

        monkeypatch.setattr(SqlitePromotionJournalStore, "prepare", fail_after_p1)
        restore_page = browser.get("/profiles/restore", params={"db": str(live_path),
                                                             "backup": str(backup_path)})
        failed = browser.post("/profiles/restore", data={
            "csrf": token(restore_page.text), "db": str(live_path),
            "backup": str(backup_path), "password": PASSWORD, "confirm": "yes",
        })
        assert failed.status_code == 400
        assert "Check interrupted restore" in failed.text
        repair = browser.get("/profiles/restore/resume", params={"db": str(live_path)})
        denied = browser.post("/profiles/restore/resume", data={
            "csrf": token(repair.text), "db": str(live_path), "password": PASSWORD,
        })
        assert denied.status_code == 400
        app.session.retry_at = 0.0
        resumed = browser.post("/profiles/restore/resume", data={
            "csrf": token(denied.text), "db": str(live_path),
            "password": PASSWORD, "confirm": "yes",
        })
        assert resumed.status_code == 200, resumed.text
        assert "Restore checks finished" in resumed.text
        assert app.session.container is None
        unlocked = browser.post("/profiles/unlock", data={
            "csrf": token(resumed.text), "db": str(live_path), "password": PASSWORD,
        })
        assert unlocked.status_code == 200, unlocked.text


def test_finance_routes_are_all_async():
    import inspect
    from fastapi.routing import APIRoute
    from lightning.ui.web import create_app
    pending = list(create_app(None).routes)
    checked = 0
    while pending:
        route = pending.pop()
        # FastAPI's pinned release stores included routers lazily.
        nested = getattr(route, "original_router", None)
        if nested is not None:
            pending.extend(nested.routes)
        if isinstance(route, APIRoute):
            assert inspect.iscoroutinefunction(route.endpoint), route.path
            checked += 1
    assert checked > 50


def test_finance_templates_include_form_tokens_and_no_inline_handlers():
    from lightning.ui.web import UI_DIR
    for path in (UI_DIR / "templates").rglob("*.html"):
        if path.name == "profiles.html":
            continue
        source = path.read_text(encoding="utf-8")
        assert not re.search(r'\bon(?:click|submit|change|input)\s*=', source), path
        for opening in re.findall(r'<script\b[^>]*>', source):
            assert 'nonce="{{ request.state.csp_nonce' in opening, path
        for form in re.findall(r'<form\b.*?</form>', source, re.S):
            if re.search(r'<form\b[^>]*method="post"', form, re.I):
                # Profile routes (the phone's Devices page) carry the profile CSRF token instead.
                expected = 'name="csrf"' if re.search(r'<form\b[^>]*action="/profiles/', form) else 'name="__session"'
                assert expected in form, path


def test_setup_confirmation_cannot_acknowledge_another_tabs_key(tmp_path):
    browser, app, cfg = start(tmp_path)
    with browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        csrf = token(browser.get("/profiles/new").text)
        first = browser.post("/profiles/new", data={"csrf": csrf, "name": "A", "password": PASSWORD, "confirm": PASSWORD, **SECRET})
        first_token = token(first.text)
        second = browser.post("/profiles/new", data={"csrf": first_token, "name": "B", "password": PASSWORD, "confirm": PASSWORD, **SECRET})
        assert token(second.text) != first_token
        assert browser.post("/profiles/confirm", data={"csrf": first_token, "recovery": recovery_shown(first.text)}).status_code == 403
        assert not app.session.root.exists()


def test_idle_lock_closes_database_and_health_does_not_extend_session(tmp_path):
    import time
    browser, app, cfg = start(tmp_path)
    with browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        last = app.session.last_activity
        assert browser.get("/profiles/health").json()["locked"] is False
        assert app.session.last_activity == last
        app.session.last_activity = time.monotonic() - 1000
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not browser.get("/profiles/health").json()["locked"]:
            time.sleep(.1)
        assert app.session.container is None


def test_lock_drains_request_and_rejects_queued_old_generation(tmp_path):
    import asyncio
    import httpx
    from starlette.responses import PlainTextResponse

    async def scenario():
        cfg = Credentials("http://127.0.0.1:9876")
        app = profile_app(cfg, tmp_path / "profiles")
        session = app.session
        session.prepare("Home", PASSWORD, PASSWORD, SECRET["question"], SECRET["answer"])
        session.confirm(session.pending.recovery)
        entered, release = asyncio.Event(), asyncio.Event()
        writes = []
        inner = app.app.app

        @inner.post("/slow-save")
        async def slow_save():
            entered.set()
            await release.wait()
            session.container.settings.set("race_marker", "saved")
            writes.append("saved")
            return PlainTextResponse("saved")

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=cfg.origin,
                                     headers={"Origin": cfg.origin}, cookies={cfg.cookie_name: cfg.token}) as client:
            first = asyncio.create_task(client.post("/slow-save", data={"__session": session.token}))
            await entered.wait()
            locking = asyncio.create_task(client.post("/profiles/lock", data={"csrf": session.csrf}))
            await asyncio.sleep(0)
            queued = asyncio.create_task(client.post("/slow-save", data={"__session": session.token}))
            await asyncio.sleep(0)
            assert session.container is not None
            release.set()
            assert (await first).status_code == 200
            assert (await locking).status_code == 303
            assert (await queued).status_code in (303, 409)
            assert writes == ["saved"]
            assert session.container is None
        session.close()
    asyncio.run(scenario())


def test_settings_start_fresh_locks_this_profile_and_opens_new_profile_setup(tmp_path):
    browser, app, cfg = start(tmp_path)
    with browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser, "Home")
        page = browser.get("/settings")
        assert "Start a new profile" in page.text and "Start a fresh database" not in page.text
        response = browser.post("/settings/fresh", data={"__session": token(page.text, "__session")}, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"].startswith("/profiles/new")
        assert app.session.container is None  # the old profile is locked, untouched
        assert "Home" in browser.get("/profiles").text
