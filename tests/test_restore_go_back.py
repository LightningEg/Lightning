"""IT-2C4 (owner 2026-11-08, 2C7 a): a restore whose resume is blocked can go back to the copy from before it."""

from __future__ import annotations

from lightning.database.promotion import CandidatePromotionService, PromotionBlocked, SqlitePromotionJournalStore
from tests.test_profile_app import PASSWORD, create, start, token


def _interrupted(browser, app, cfg, monkeypatch):
    browser.get("/__launch", params={"code": cfg.launch_code})
    create(browser)
    live = app.session.paths.db_path
    browser.portal.call(app.session.container.settings.set, "restore_ui_marker", "old backup")
    backup = browser.portal.call(app.session.container.backup_now)
    browser.portal.call(app.session.container.settings.set, "restore_ui_marker", "before the restore")
    browser.post("/profiles/lock", data={"csrf": token(browser.get("/profiles").text)})
    original = SqlitePromotionJournalStore.prepare
    injected = {"done": False}

    def fail_after_p1(self, journal):
        result = original(self, journal)
        if not injected["done"]:
            injected["done"] = True
            raise OSError("injected interruption")
        return result
    monkeypatch.setattr(SqlitePromotionJournalStore, "prepare", fail_after_p1)
    page = browser.get("/profiles/restore", params={"db": str(live), "backup": str(backup)})
    failed = browser.post("/profiles/restore", data={"csrf": token(page.text), "db": str(live), "backup": str(backup),
                                                     "password": PASSWORD, "confirm": "yes"})
    assert failed.status_code == 400

    def blocked(self, **_kwargs):
        raise PromotionBlocked("evidence does not match")
    monkeypatch.setattr(CandidatePromotionService, "recover", blocked)
    app.session.retry_at = 0.0
    page = browser.get("/profiles/restore/resume", params={"db": str(live)})
    resumed = browser.post("/profiles/restore/resume", data={"csrf": token(page.text), "db": str(live),
                                                             "password": PASSWORD, "confirm": "yes"})
    assert resumed.status_code == 400 and "blocked" in resumed.text
    assert "/profiles/restore/repair" in resumed.text
    app.session.retry_at = 0.0
    return live


def _go_back(browser, app, live, password=PASSWORD):
    page = browser.get("/profiles/restore/repair", params={"db": str(live)})
    assert page.status_code == 200 and "Restore needs checking" in page.text
    assert "Matches the record" in page.text
    app.session.retry_at = 0.0
    return browser.post("/profiles/restore/repair", data={"csrf": token(page.text), "db": str(live),
                                                          "password": password, "confirm": "yes"})


def _unlocked_marker(browser, app, live, text):
    unlocked = browser.post("/profiles/unlock", data={"csrf": token(text), "db": str(live), "password": PASSWORD})
    assert unlocked.status_code == 200, unlocked.text
    return browser.portal.call(app.session.container.settings.get, "restore_ui_marker")


def test_go_back_through_the_normal_restore_when_the_live_file_opens(tmp_path, monkeypatch):
    browser, app, cfg = start(tmp_path)
    with browser:
        live = _interrupted(browser, app, cfg, monkeypatch)
        wrong = _go_back(browser, app, live, password="not the password at all")
        assert wrong.status_code == 400
        done = _go_back(browser, app, live)
        assert done.status_code == 200 and "Back to the copy from before the restore" in done.text, done.text
        evidence = list(live.parent.glob("restore-evidence-*"))
        assert len(evidence) == 1 and any(path.suffix == ".state" for path in evidence[0].iterdir())
        assert _unlocked_marker(browser, app, live, done.text) == "before the restore"


def test_go_back_replaces_a_live_file_that_no_longer_opens(tmp_path, monkeypatch):
    browser, app, cfg = start(tmp_path)
    with browser:
        live = _interrupted(browser, app, cfg, monkeypatch)
        damaged = b"\x00" * 4096
        live.write_bytes(damaged)
        done = _go_back(browser, app, live)
        assert done.status_code == 200, done.text
        evidence = next(live.parent.glob("restore-evidence-*"))
        assert (evidence / live.name).read_bytes() == damaged
        assert _unlocked_marker(browser, app, live, done.text) == "before the restore"


def test_a_changed_copy_from_before_is_refused_and_nothing_moves(tmp_path, monkeypatch):
    browser, app, cfg = start(tmp_path)
    with browser:
        live = _interrupted(browser, app, cfg, monkeypatch)
        restorer_files = sorted(path.name for path in live.parent.iterdir())
        pre = next(path for path in (live.parent / "backups").iterdir() if "_upgrade_" in path.name)
        pre.write_bytes(pre.read_bytes()[:-1] + b"\x01")
        page = browser.get("/profiles/restore/repair", params={"db": str(live)})
        assert "Does not match the record" in page.text and 'action="/profiles/restore/repair"' not in page.text
        refused = browser.post("/profiles/restore/repair", data={"csrf": token(page.text), "db": str(live),
                                                                 "password": PASSWORD, "confirm": "yes"})
        assert refused.status_code == 400 and "does not match its record" in refused.text
        assert sorted(path.name for path in live.parent.iterdir()) == restorer_files


def test_repair_with_no_restore_record_offers_nothing(tmp_path):
    browser, app, cfg = start(tmp_path)
    with browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        live = app.session.paths.db_path
        browser.post("/profiles/lock", data={"csrf": token(browser.get("/profiles").text)})
        page = browser.get("/profiles/restore/repair", params={"db": str(live)})
        assert "No readable restore record" in page.text
        refused = browser.post("/profiles/restore/repair", data={"csrf": token(page.text), "db": str(live),
                                                                 "password": PASSWORD, "confirm": "yes"})
        assert refused.status_code == 400 and "cannot find the record" in refused.text
        assert not list(live.parent.glob("restore-evidence-*"))



def test_repair_and_pick_refuse_a_database_outside_the_profiles_folder(tmp_path):
    from lightning.runtime import file_picker
    browser, app, cfg = start(tmp_path)
    with browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        page = browser.get("/profiles/restore/repair", params={"db": str(tmp_path / "elsewhere.db")})
        assert page.status_code == 400 and "named Lightning profile" in page.text
        file_picker.register(lambda: None)
        try:
            refused = browser.post("/profiles/restore/pick", data={"csrf": token(page.text),
                                                                   "db": str(tmp_path / "elsewhere.db")})
        finally:
            file_picker.register(None)
        assert refused.status_code == 400
