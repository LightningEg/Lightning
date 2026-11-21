"""IT-2A3: one repair for an interrupted restore, chosen by the state on disk: undo what published nothing,
finish what started, keep everything else locked with its evidence."""

from __future__ import annotations

import pytest

from lightning.runtime.session import ProfileError, ProfileSession
from tests.test_profile_session import PASSWORD, _killed_restore


def _marker(session, live):
    session.unlock(str(live), PASSWORD)
    try:
        return session.container.settings.get("restore_marker")
    finally:
        session.close()


def test_unlock_clears_an_unpublished_restore_and_its_copy(tmp_path):
    session, live, paths, selected, live_before = _killed_restore(tmp_path, "copied")
    assert len(list(paths.backups_dir.glob(".lightning-restore-source-*.db"))) == 1
    fresh = ProfileSession(session.root)
    assert _marker(fresh, live) == "current live"
    assert not list(paths.data_dir.glob(".lightning-restore-*.intent"))
    assert not list(paths.backups_dir.glob(".lightning-restore-source-*.db"))
    assert selected.exists() and not list(paths.data_dir.glob("restore-evidence-*"))


def test_an_unpublished_copy_whose_backup_is_gone_is_kept_as_evidence(tmp_path):
    session, live, paths, selected, _ = _killed_restore(tmp_path, "copied")
    copy = next(paths.backups_dir.glob(".lightning-restore-source-*.db"))
    kept = copy.read_bytes()
    selected.unlink()
    fresh = ProfileSession(session.root)
    assert _marker(fresh, live) == "current live"
    evidence = list(paths.data_dir.glob("restore-evidence-*"))
    assert len(evidence) == 1 and (evidence[0] / copy.name).read_bytes() == kept
    assert not copy.exists() and not list(paths.data_dir.glob(".lightning-restore-*.intent"))


@pytest.mark.parametrize("boundary", ["manifest", "accepted"])
def test_a_pending_restore_whose_journal_never_started_is_undone(tmp_path, boundary):
    session, live, paths, selected, live_before = _killed_restore(tmp_path, boundary)
    fresh = ProfileSession(session.root)
    with pytest.raises(ProfileError, match="needs repair"):
        fresh.unlock(str(live), PASSWORD)
    fresh.retry_at = 0.0
    assert fresh.repair_interrupted_restore(str(live), PASSWORD) == "undone"
    assert live.read_bytes() == live_before
    evidence = next(paths.data_dir.glob("restore-evidence-*"))
    names = {path.name for path in evidence.iterdir()}
    assert any(name.endswith(".state") for name in names)
    assert any(name.startswith(".lightning-restore-source-") for name in names)
    assert (boundary == "accepted") == any(name.endswith(".sqlite") for name in names)
    assert not list(paths.data_dir.glob(".lightning-restore-*"))
    assert not list(paths.backups_dir.glob(".lightning-restore-source-*"))
    assert selected.exists()
    fresh.retry_at = 0.0
    assert _marker(fresh, live) == "current live"
    # Repeating the repair finds nothing pending and changes nothing.
    fresh.retry_at = 0.0
    assert fresh.repair_interrupted_restore(str(live), PASSWORD) == "undone"
    assert live.read_bytes() == live_before


def test_an_undo_interrupted_before_its_record_moves_lands_the_same_way(tmp_path, monkeypatch):
    from lightning.runtime import restore

    session, live, paths, _selected, live_before = _killed_restore(tmp_path, "manifest")
    real_move = restore._durable_move

    def stop_at_record(source, destination):
        if str(source).endswith(".state"):
            raise OSError("injected interruption before the record moves")
        return real_move(source, destination)

    fresh = ProfileSession(session.root)
    monkeypatch.setattr(restore, "_durable_move", stop_at_record)
    with pytest.raises(ProfileError):
        fresh.repair_interrupted_restore(str(live), PASSWORD)
    monkeypatch.setattr(restore, "_durable_move", real_move)
    assert len(list(paths.data_dir.glob(".lightning-restore-*.state"))) == 1
    fresh.retry_at = 0.0
    assert fresh.repair_interrupted_restore(str(live), PASSWORD) == "undone"
    assert live.read_bytes() == live_before
    fresh.retry_at = 0.0
    assert _marker(fresh, live) == "current live"


def test_a_started_restore_is_finished_forward(tmp_path):
    session, live, paths, _selected, live_before = _killed_restore(tmp_path, "P2")
    fresh = ProfileSession(session.root)
    assert fresh.repair_interrupted_restore(str(live), PASSWORD) == "finished"
    assert not list(paths.data_dir.glob("restore-evidence-*"))
    fresh.retry_at = 0.0
    assert _marker(fresh, live) == "in the backup"


def test_an_unpublished_restore_is_not_undone_when_the_profile_changed(tmp_path):
    session, live, paths, _selected, _ = _killed_restore(tmp_path, "manifest")
    live.write_bytes(live.read_bytes()[:-1] + b"\x01")
    fresh = ProfileSession(session.root)
    with pytest.raises(ProfileError, match="changed after the restore began"):
        fresh.repair_interrupted_restore(str(live), PASSWORD)
    assert len(list(paths.data_dir.glob(".lightning-restore-*.state"))) == 1
    assert len(list(paths.backups_dir.glob(".lightning-restore-source-*.db"))) == 1


def test_the_resume_screen_says_when_a_restore_was_undone(tmp_path, monkeypatch):
    from lightning.database.promotion import SqlitePromotionJournalStore
    from tests.test_profile_app import create, start, token

    browser, app, cfg = start(tmp_path)
    with browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        live = app.session.paths.db_path
        backup = browser.portal.call(app.session.container.backup_now)
        browser.post("/profiles/lock", data={"csrf": token(browser.get("/profiles").text)})

        def fail(self, *args, **kwargs):
            raise OSError("injected interruption before the journal starts")
        monkeypatch.setattr(SqlitePromotionJournalStore, "initialize_accepted", fail)
        page = browser.get("/profiles/restore", params={"db": str(live), "backup": str(backup)})
        failed = browser.post("/profiles/restore", data={"csrf": token(page.text), "db": str(live), "backup": str(backup),
                                                         "password": PASSWORD, "confirm": "yes"})
        assert failed.status_code == 400
        app.session.retry_at = 0.0
        page = browser.get("/profiles/restore/resume", params={"db": str(live)})
        done = browser.post("/profiles/restore/resume", data={"csrf": token(page.text), "db": str(live),
                                                              "password": PASSWORD, "confirm": "yes"})
        assert done.status_code == 200 and "had not changed anything yet" in done.text, done.text
