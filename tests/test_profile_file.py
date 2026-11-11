"""BT-2AI5: one portable profile file. A fresh device opens a book from it with the profile password alone."""
from __future__ import annotations

import json
import zipfile

import pytest

from lightning.runtime import profile_file
from lightning.runtime.paths import discover_profiles
from lightning.runtime.profile_file import read_profile_file, write_profile_file
from lightning.runtime.session import ProfileError, ProfileSession

PASSWORD = "a correct long passphrase"
ANSWER = "El Orman"


@pytest.fixture(autouse=True)
def inexpensive_owner_wraps(monkeypatch):
    from lightning.sync.journal import owner
    monkeypatch.setattr(owner, "RECOVERY_MEMORY_KIB", 32768)
    monkeypatch.setattr(owner, "RECOVERY_ITERATIONS", 2)


def _book(root, *, journal=False):
    """A dummy profile with two accounts; returns the saved profile file and what it should hold."""
    session = ProfileSession(root)
    session.prepare("Home", PASSWORD, PASSWORD, "Which school?", ANSWER)
    recovery = session.pending.recovery
    session.confirm(recovery)
    session.container.account_flows.open_account("Current", "BANK", "2026-09-01", "10000", institution="CIB")
    session.container.account_flows.open_account("Wallet", "CASH", "2026-09-01", "350.25")
    if journal:
        path = session.paths.db_path
        session.close()
        session.unlock(str(path), PASSWORD)
        session.enable_journal(PASSWORD, recovery, ANSWER)
    # A journal profile's own connection refuses ATTACH, so its snapshot runs on a second, read-only one.
    saved = write_profile_file(session.paths, session.container.db.copy_key(), root.parent / "out",
                               db=None if journal else session.container.db)
    expected = _balances(session)
    session.close()
    return saved, expected


def _balances(session):
    return sorted(tuple(row) for row in session.container.db.all(
        "SELECT a.name, COALESCE(SUM(l.amount_e6), 0) FROM accounts a LEFT JOIN ledger_entries l ON l.account_id = a.id "
        "GROUP BY a.id"))


def _rebuilt(source, target, change):
    """The same ZIP with its members changed by `change(name, data) -> [(name, data), ...]`."""
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as new:
        for entry in old.infolist():
            for name, data in change(entry.filename, old.read(entry)):
                new.writestr(zipfile.ZipInfo(name), data)
    return target


def _folders(root):
    return sorted(child.name for child in root.iterdir()) if root.is_dir() else []


def test_a_profile_file_opens_on_a_fresh_device_with_the_same_balances(tmp_path):
    saved, expected = _book(tmp_path / "old" / "Lightning")
    assert saved.name.startswith("Home-") and saved.suffix == ".lightning"
    with zipfile.ZipFile(saved) as archive:
        assert sorted(archive.namelist()) == ["keys.json", "manifest.json", "profile.db"]
        assert all(entry.compress_type == zipfile.ZIP_STORED for entry in archive.infolist())
        assert json.loads(archive.read("manifest.json"))["format"] == "lightning-profile-v1"
        assert b"SQLite format 3" not in archive.read("profile.db")[:16]  # the copy stays encrypted

    fresh = tmp_path / "new" / "Lightning"
    opened = read_profile_file(saved, PASSWORD, fresh)
    assert opened.name == "Home" and not opened.review_copy
    assert [info.name for info in discover_profiles(fresh)] == ["Home"]
    session = ProfileSession(fresh)
    session.unlock(str(opened.paths.db_path), PASSWORD)
    try:
        assert session.role.writable and _balances(session) == expected
    finally:
        session.close()
    assert not [name for name in _folders(fresh) if name.startswith(".open-profile-file-")]


def test_a_profile_file_never_lands_on_an_existing_profile(tmp_path):
    root = tmp_path / "Documents" / "Lightning"
    saved, _ = _book(root)
    before = _folders(root)
    opened = read_profile_file(saved, PASSWORD, root)
    assert opened.name == "Home_(2)"
    assert sorted(info.name for info in discover_profiles(root)) == ["Home", "Home_(2)"]
    assert set(before) < set(_folders(root))
    again = write_profile_file(opened.paths, _key(opened), saved.parent)
    assert again != saved and saved.exists()  # a second file the same day gets its own name


def _key(opened):
    from lightning.runtime.session import read_keys
    from lightning.security.keys import unwrap_key
    return unwrap_key(read_keys(opened.paths), PASSWORD)


def test_a_wrong_password_or_a_changed_file_leaves_nothing_behind(tmp_path, monkeypatch):
    saved, _ = _book(tmp_path / "old" / "Lightning")
    fresh = tmp_path / "new" / "Lightning"

    def refused(path, message, password=PASSWORD):
        with pytest.raises(ProfileError, match=message):
            read_profile_file(path, password, fresh)
        assert _folders(fresh) == []

    refused(saved, "password is incorrect", "not the password at all")

    flipped = tmp_path / "flipped.lightning"
    raw = bytearray(saved.read_bytes())
    raw[len(raw) // 2] ^= 0x01  # one byte inside profile.db
    flipped.write_bytes(raw)
    refused(flipped, "damaged")

    def swapped_hash(name, data):
        if name == "manifest.json":
            manifest = json.loads(data)
            manifest["sha256"]["profile.db"] = "0" * 64
            data = json.dumps(manifest).encode()
        return [(name, data)]
    refused(_rebuilt(saved, tmp_path / "hash.lightning", swapped_hash), "damaged")

    refused(_rebuilt(saved, tmp_path / "path.lightning",
                     lambda name, data: [("../x" if name == "profile.db" else name, data)]), "not a Lightning profile file")
    refused(_rebuilt(saved, tmp_path / "extra.lightning",
                     lambda name, data: [(name, data)] + ([("../x", b"x")] if name == "keys.json" else [])),
            "not a Lightning profile file")
    assert not (tmp_path / "x").exists() and not (tmp_path / "new" / "x").exists()

    packed = tmp_path / "packed.lightning"
    with zipfile.ZipFile(saved) as old, zipfile.ZipFile(packed, "w", zipfile.ZIP_DEFLATED) as new:
        for entry in old.infolist():
            new.writestr(entry.filename, old.read(entry))
    refused(packed, "not a Lightning profile file")

    link = tmp_path / "link.lightning"
    link.symlink_to(saved)
    refused(link, "not a Lightning profile file")
    plain = tmp_path / "plain.lightning"
    plain.write_bytes(b"not a zip")
    refused(plain, "not a Lightning profile file")

    monkeypatch.setattr(profile_file, "MAX_BYTES", saved.stat().st_size - 1)  # the cap, without a 256 MB fixture
    refused(saved, "too large")


def test_a_journal_profile_arrives_as_a_review_copy_never_a_second_home(tmp_path):
    saved, expected = _book(tmp_path / "old" / "Lightning", journal=True)
    fresh = tmp_path / "new" / "Lightning"
    opened = read_profile_file(saved, PASSWORD, fresh)
    assert opened.review_copy
    session = ProfileSession(fresh)
    session.unlock(str(opened.paths.db_path), PASSWORD)
    try:
        assert session.role.value == "reader" and session.journal is None and session.container.db.read_only
        assert _balances(session) == expected
    finally:
        session.close()


def test_save_a_copy_sends_the_profile_file(tmp_path):
    """Settings > Save a copy: the file that leaves the device is one a fresh device can open."""
    from tests.test_phone_downloads import PASSWORD as PHONE_PASSWORD, Saver, opened, token
    saver = Saver()
    with opened(tmp_path, saver=saver) as browser:
        session = token(browser.get("/settings").text, "__session")
        browser.post("/settings/backup", data={"__session": session})
        browser.get("/settings/backup/latest", headers={"Referer": "http://127.0.0.1:9872/settings"}, follow_redirects=False)
        browser.get("/settings/backup/latest", headers={"Referer": "http://127.0.0.1:9872/settings"}, follow_redirects=False)
    name, _, data = saver.offers[-1]
    assert name.startswith("Home-") and name.endswith(".lightning")
    backups = next((tmp_path / "Documents" / "Lightning").glob("Home_*")) / "backups"
    assert not [child.name for child in backups.iterdir() if child.name.startswith(".")]  # no staging left
    carried = tmp_path / name
    carried.write_bytes(data)
    assert read_profile_file(carried, PHONE_PASSWORD, tmp_path / "fresh").name == "Home"


# --- BT-2AI2: "Open a profile file" on the profile chooser -------------------------------------------------------

def _locked_app(root, *, phone=True):
    from fastapi.testclient import TestClient
    from lightning.runtime.app import profile_app
    from lightning.runtime.http import Credentials
    cfg = Credentials("http://127.0.0.1:9872")
    app = profile_app(cfg, root, phone=phone)
    browser = TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin})
    browser.__enter__()
    browser.get("/__launch", params={"code": cfg.launch_code})
    return app, browser


def _post_file(browser, saved, password, *, path="/profiles/open-file"):
    from tests.test_phone_downloads import token
    csrf = token(browser.get("/profiles/open-file").text, "csrf")
    return browser.post(path, data={"csrf": csrf, "password": password},
                        files={"profile": (saved.name, saved.read_bytes(), "application/octet-stream")},
                        follow_redirects=False)


@pytest.mark.parametrize("phone", [True, False])
def test_the_chooser_opens_a_profile_file_as_a_new_unlocked_profile(tmp_path, phone):
    saved, expected = _book(tmp_path / "old" / "Lightning")
    fresh = tmp_path / "new" / "Lightning"
    app, browser = _locked_app(fresh, phone=phone)
    try:
        chooser = browser.get("/profiles").text
        assert 'href="/profiles/open-file"' in chooser
        form = browser.get("/profiles/open-file").text
        assert 'type="file"' in form and 'accept=".lightning"' in form and 'enctype="multipart/form-data"' in form

        answer = _post_file(browser, saved, PASSWORD)
        assert answer.status_code == 303 and answer.headers["location"] == "/"
        session = app.gate.session
        assert session.container is not None and session.role.writable and session.name == "Home"
        assert browser.portal.call(_balances, session) == expected
        assert [info.name for info in discover_profiles(fresh)] == ["Home"]
        assert not [name for name in _folders(fresh) if name.startswith(".")]  # the upload's temporary file is gone
    finally:
        browser.__exit__(None, None, None)


def test_a_wrong_password_or_a_bad_upload_adds_no_profile(tmp_path):
    saved, _ = _book(tmp_path / "old" / "Lightning")
    fresh = tmp_path / "new" / "Lightning"
    app, browser = _locked_app(fresh)
    try:
        answer = _post_file(browser, saved, "not the password at all")
        assert answer.status_code == 400 and "The password is incorrect." in answer.text
        junk = tmp_path / "junk.lightning"
        junk.write_bytes(b"not a profile file")
        answer = _post_file(browser, junk, PASSWORD)
        assert answer.status_code == 400 and "This is not a Lightning profile file." in answer.text
        assert app.gate.session.container is None
        assert _folders(fresh) == [] or not discover_profiles(fresh)
        assert not [name for name in _folders(fresh) if name.startswith(".")]

        # Any other form still refuses a file part: the request is turned away before its route runs.
        refused = _post_file(browser, junk, PASSWORD, path="/profiles/new")
        assert refused.status_code == 403
        assert not discover_profiles(fresh)
    finally:
        browser.__exit__(None, None, None)


def test_the_open_file_screen_speaks_arabic(tmp_path):
    saved, _ = _book(tmp_path / "old" / "Lightning")
    _, browser = _locked_app(tmp_path / "new" / "Lightning")
    try:
        browser.cookies.set("lightning_ui_locale", "ar")
        assert "افتح ملف بروفايل" in browser.get("/profiles").text
        page = browser.get("/profiles/open-file").text
        assert "<h1 id=\"page-title\">افتح ملف بروفايل</h1>" in page and "اختيار الملف" in page
        junk = tmp_path / "junk.lightning"
        junk.write_bytes(b"x")
        assert "ده مش ملف بروفايل من لايتنينج." in _post_file(browser, junk, PASSWORD).text
    finally:
        browser.__exit__(None, None, None)


# --- BT-2AI3: a copy outside the app ---------------------------------------------------------------------------

class _Folder:
    """A fake of the phone's chosen folder (`BackupFolderBridge`)."""

    def __init__(self, state="ok", name="Lightning copies"):
        self.kind, self.name, self.files, self.asked, self.fail = state, name, {}, 0, False

    def state(self):
        return self.kind, self.name if self.kind == "ok" else ""

    def choose(self):
        self.asked += 1

    def forget(self):
        self.kind = "none"

    def write(self, path, name):
        from pathlib import Path
        if self.fail:
            return ""
        given, n = name, 1
        while given in self.files:  # the system renames a second file of the same name
            n += 1
            given = name.replace(".lightning", f" ({n}).lightning")
        self.files[given] = Path(path).read_bytes()
        return given

    def names(self):
        return list(self.files)

    def delete(self, name):
        return self.files.pop(name, None) is not None


def _outside(tmp_path, folder):
    from lightning.runtime.outside_copy import OutsideCopy
    return OutsideCopy(folder, tmp_path / "files" / "outside-copy", tmp_path / "files" / "appdata" / "outside-copy.json")


def _open_session(root):
    session = ProfileSession(root)
    session.prepare("Home", PASSWORD, PASSWORD, "Which school?", ANSWER)
    session.confirm(session.pending.recovery)
    session.container.account_flows.open_account("Current", "BANK", "2026-09-01", "10000", institution="CIB")
    return session


def test_the_outside_folder_gets_one_copy_a_day_and_keeps_the_newest_three(tmp_path, monkeypatch):
    from lightning.runtime import outside_copy
    folder = _Folder()
    folder.files["holiday.jpg"] = b"theirs"
    folder.files["Other-2020-01-01.lightning"] = b"not written by this phone"
    outside = _outside(tmp_path, folder)
    session = _open_session(tmp_path / "Documents" / "Lightning")
    try:
        profile = session.paths.profile.profile_id
        assert outside.status(profile) == {"chosen": True, "folder": "Lightning copies", "last": "", "problem": ""}
        days = ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"]
        for day in days:
            monkeypatch.setattr(outside_copy, "_today", lambda day=day: day)
            monkeypatch.setattr(profile_file, "_today", lambda day=day: day)
            assert outside.keep(session) is True
            assert outside.keep(session) is False  # once a day
        ours = sorted(name for name in folder.files if name.startswith("Home-"))
        assert ours == [f"Home-{day}.lightning" for day in days[-3:]]
        assert {"holiday.jpg", "Other-2020-01-01.lightning"} <= set(folder.files)  # never a file Lightning did not write
        assert outside.status(profile)["last"] == "2026-11-05"
        assert list((tmp_path / "files" / "outside-copy").iterdir()) == []  # nothing waits in the app's folder

        carried = tmp_path / "carried.lightning"
        carried.write_bytes(folder.files["Home-2026-11-05.lightning"])
    finally:
        session.close()
    # After an uninstall the folder is all that is left: the copy opens on a fresh install.
    assert read_profile_file(carried, PASSWORD, tmp_path / "fresh").name == "Home"


def test_a_lost_folder_or_a_failed_copy_is_said_and_never_breaks_a_page(tmp_path, monkeypatch):
    from lightning.runtime import outside_copy
    folder = _Folder()
    outside = _outside(tmp_path, folder)
    session = _open_session(tmp_path / "Documents" / "Lightning")
    try:
        profile = session.paths.profile.profile_id
        folder.fail = True
        assert outside.keep(session) is False
        assert outside.status(profile)["problem"] == outside_copy.WRITE_FAILED
        folder.fail = False
        assert outside.keep(session) is False          # not hammered: once a day
        outside.choose()                               # choosing the folder again tries again at once
        assert folder.asked == 1 and outside.keep(session) is True
        assert outside.status(profile)["problem"] == "" and outside.status(profile)["last"]

        folder.kind = "lost"
        assert outside.keep(session) is False
        assert outside.status(profile) == {"chosen": True, "folder": "", "last": "", "problem": outside_copy.FOLDER_LOST}

        monkeypatch.setattr(session, "write_profile_file", lambda out: (_ for _ in ()).throw(OSError("disk")))
        folder.kind, folder.name = "ok", "Another folder"
        assert outside.keep(session) is False          # an error is a line in Settings, not an exception
        assert outside.status(profile)["problem"] == outside_copy.WRITE_FAILED

        kept = dict(folder.files)
        outside.stop()
        assert folder.files == kept and outside.status(profile)["chosen"] is False  # the copies stay the person's
    finally:
        session.close()


def test_phone_settings_offers_the_outside_copy_and_writes_it(tmp_path):
    import re
    from fastapi.testclient import TestClient
    from lightning.runtime.app import profile_app
    from lightning.runtime.http import Credentials
    from tests.test_phone_downloads import _created
    folder = _Folder(state="none")
    cfg = Credentials("http://127.0.0.1:9872")
    app = profile_app(cfg, tmp_path / "Documents" / "Lightning", phone=True, outside=_outside(tmp_path, folder))
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as phone:
        phone.get("/__launch", params={"code": cfg.launch_code})
        _created(phone)
        page = phone.get("/settings").text
        assert "Keep a copy outside the app" in page and "Choose a folder" in page and folder.files == {}
        csrf = re.search(r'action="/profiles/outside-copy".*?name="csrf" value="([^"]+)"', page, re.S).group(1)
        answer = phone.post("/profiles/outside-copy", data={"csrf": csrf, "action": "choose"}, follow_redirects=False)
        assert answer.status_code == 303 and folder.asked == 1
        folder.kind = "ok"                              # the person picked a folder; the app shows Settings again
        page = phone.get("/settings").text
        assert len(folder.files) == 1 and next(iter(folder.files)).startswith("Home-")
        row = page[page.index("Keep a copy outside the app"):][:200]
        assert "Last copy: Today, in Lightning copies." in row and "Change folder" in page, row
        phone.post("/profiles/outside-copy", data={"csrf": csrf, "action": "stop"})
        assert "Choose a folder" in phone.get("/settings").text and len(folder.files) == 1
    # A PC never offers it, and neither does a phone without the bridge.
    pc = profile_app(Credentials("http://127.0.0.1:9873"), tmp_path / "pc", outside=_outside(tmp_path / "pc-files", _Folder()))
    assert pc.gate.outside is None


def test_the_android_shell_keeps_the_folder_permission_and_writes_through_documents():
    from pathlib import Path
    java = Path(__file__).resolve().parents[1] / "android/app/src/main/java/org/lightning/app"
    bridge = (java / "BackupFolderBridge.java").read_text()
    main = (java / "MainActivity.java").read_text()
    assert "Intent.ACTION_OPEN_DOCUMENT_TREE" in bridge and "takePersistableUriPermission(tree, FLAGS)" in bridge
    assert "DocumentsContract.createDocument" in bridge and "DocumentsContract.deleteDocument" in bridge
    assert '"outside-copy"' in bridge                    # only a file from the app's own staging folder is copied out
    assert "BackupFolderBridge.activity = this;" in main and "BackupFolderBridge.REQUEST_FOLDER" in main
    manifest = (java.parents[3] / "AndroidManifest.xml").read_text()
    assert "MANAGE_EXTERNAL_STORAGE" not in manifest and "WRITE_EXTERNAL_STORAGE" not in manifest  # no storage permission
    adapter = (java.parents[3] / "python/lightning_android.py").read_text()
    assert 'jclass("org.lightning.app.BackupFolderBridge")' in adapter and "outside=outside" in adapter
