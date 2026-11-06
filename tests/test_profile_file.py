"""BT-2AI2: a profile travels as one .lightning file and opens on a fresh device with its password only."""
import re
import zipfile
from pathlib import Path

import pytest

from lightning.runtime.paths import discover_profiles
from lightning.runtime.profile_file import export_profile_file, open_profile_file
from lightning.runtime.session import ProfileError, ProfileSession

PASSWORD = "a correct long passphrase"
QUESTION = "What was the name of your first school?"


def _pc_profile(tmp_path):
    session = ProfileSession(tmp_path / "pc")
    session.prepare("Home", PASSWORD, PASSWORD, QUESTION, "El Orman")
    session.confirm(session.pending.recovery)
    session.container.settings.set("marker", "dummy ledger")
    return session


def test_round_trip_opens_on_a_fresh_device(tmp_path):
    pc = _pc_profile(tmp_path)
    file = export_profile_file(pc.paths, pc.container.db, tmp_path / "Home.lightning")
    pc.close()
    phone_root = tmp_path / "phone"
    info = open_profile_file(phone_root, file, PASSWORD)
    assert [p.profile_id for p in discover_profiles(phone_root)] == [info.profile_id]
    phone = ProfileSession(phone_root)
    phone.unlock(str(info.db_path), PASSWORD)
    assert phone.container.settings.get("marker") == "dummy ledger"
    phone.close()
    with pytest.raises(ProfileError, match="already on this device"):
        open_profile_file(phone_root, file, PASSWORD)


def test_a_wrong_password_or_a_bad_file_changes_nothing(tmp_path):
    pc = _pc_profile(tmp_path)
    file = export_profile_file(pc.paths, pc.container.db, tmp_path / "Home.lightning")
    pc.close()
    phone_root = tmp_path / "phone"
    with pytest.raises(ProfileError, match="password"):
        open_profile_file(phone_root, file, "not the password")
    junk = tmp_path / "junk.lightning"
    junk.write_bytes(b"not a zip")
    with pytest.raises(ProfileError, match="not a Lightning profile file"):
        open_profile_file(phone_root, junk, PASSWORD)
    extra = tmp_path / "extra.lightning"
    with zipfile.ZipFile(file) as src, zipfile.ZipFile(extra, "w") as out:
        for item in src.infolist():
            out.writestr(item, src.read(item))
        out.writestr("../escape.txt", "x")
    with pytest.raises(ProfileError, match="not a Lightning profile file"):
        open_profile_file(phone_root, extra, PASSWORD)
    damaged = tmp_path / "damaged.lightning"
    with zipfile.ZipFile(file) as src, zipfile.ZipFile(damaged, "w") as out:
        for item in src.infolist():
            data = src.read(item)
            out.writestr(item, data[:-1] + bytes([data[-1] ^ 1]) if item.filename == "profile.db" else data)
    with pytest.raises(ProfileError, match="damaged"):
        open_profile_file(phone_root, damaged, PASSWORD)
    assert not discover_profiles(phone_root)
    assert not [p for p in phone_root.iterdir()] if phone_root.exists() else True


def test_screens_export_on_the_pc_and_open_on_a_fresh_phone(tmp_path):
    """The two screens: Save a profile file on the PC, Open a profile file on a phone with nothing on it."""
    from test_profile_app import PASSWORD as PW, create, start, token

    pc, pc_app, cfg = start(tmp_path / "pc")
    with pc:
        pc.get("/__launch", params={"code": cfg.launch_code})
        create(pc)
        manage = pc.get("/profiles")
        assert "Save a profile file" in manage.text
        saved = pc.post("/profiles/export-file", data={"csrf": token(manage.text)})
        assert saved.status_code == 200 and "Home.lightning" in saved.headers["content-disposition"]
        blob = saved.content
    phone, phone_app, cfg2 = start(tmp_path / "phone")
    with phone:
        phone.get("/__launch", params={"code": cfg2.launch_code})
        listing = phone.get("/profiles")
        assert "Open a profile file" in listing.text
        form = phone.get("/profiles/open-file")
        csrf = token(form.text)
        wrong = phone.post("/profiles/open-file", data={"csrf": csrf, "password": "nope nope nope nope"},
                           files={"file": ("Home.lightning", blob)})
        assert wrong.status_code == 400 and "password" in wrong.text
        phone_app.session.retry_at = 0  # the short pause between tries
        right = phone.post("/profiles/open-file", data={"csrf": token(wrong.text), "password": PW},
                           files={"file": ("Home.lightning", blob)})
        assert right.status_code == 200 and "Profile added from the file" in right.text, re.findall(r"alert-error[^<]*<|role=\"alert\"[^<]*<[^<]*", right.text)
