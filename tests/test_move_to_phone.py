"""Milestone 2, step 4 (task 17): a PC moves its profile's home to the phone, through the screens.

The PC's copy is renamed and kept, never left writable; the phone opens the profile with the same password and
is its home; the PC then borrows it like any paired PC."""
import re

from test_devices_app import add_account, app_for
from test_profile_app import PASSWORD, create, token


def test_move_a_pc_profile_to_the_phone_then_borrow_it_back(tmp_path, monkeypatch):
    phone, phone_app, phone_cfg, phone_devices = app_for(tmp_path, "phone", 9881)
    pc, pc_app, pc_cfg, pc_devices = app_for(tmp_path, "pc", 9882)
    with phone, pc:
        phone.get("/__launch", params={"code": phone_cfg.launch_code})
        pc.get("/__launch", params={"code": pc_cfg.launch_code})
        create(pc, "Mohab")
        assert add_account(pc, "PC wallet").status_code == 200
        pc_db = pc_app.session.paths.db_path

        page = phone.get("/profiles/receive")
        phone.post("/profiles/receive", data={"csrf": token(page.text), "phone_name": "My phone"})
        page = phone.get("/profiles/receive").text
        code = re.search(r'aria-label="Pairing digits"[^>]*>(?:<strong[^>]*>)?(\d{2})<', page).group(1)
        assert 'href="/profiles/move"' in pc.get("/profiles").text  # Move to your phone › Find your phone
        from lightning.sync import nearby
        monkeypatch.setattr(nearby, "NEARBY_PORT", phone_devices.nearby.port)
        found = pc.get("/profiles/move").text
        assert "The two digits on My phone" in found  # the PC found the phone waiting for a profile (NF-4M)
        endpoint = re.search(r'name="endpoint" value="([^"]+)"', found).group(1)
        moved = pc.post("/profiles/move", data={"csrf": token(found), "endpoint": endpoint, "phone_name": "My phone",
                                                "code": code, "pc_name": "Office PC"})
        assert "now lives on My phone" in moved.text, moved.text[-1500:]
        assert not pc_db.exists() and pc_db.with_name(f"{pc_db.stem}.moved-to-phone.db").exists()
        arrived = phone.get("/profiles/receive").text
        assert "Mohab is here" in arrived and "Office PC" in arrived

        # The phone unlocks it with the same password, writable: it is home now.
        chooser = phone.get("/profiles").text
        db = re.search(r'/profiles/unlock\?db=([^"]+)"', chooser).group(1)
        import urllib.parse
        selected = urllib.parse.unquote(db)
        page = phone.get("/profiles/unlock", params={"db": selected})
        phone.post("/profiles/unlock", data={"csrf": token(page.text), "db": selected, "password": PASSWORD})
        assert "PC wallet" in phone.get("/accounts").text
        assert add_account(phone, "Phone wallet").status_code == 200

        # The PC borrows it back with the same password.
        listing = pc.get("/profiles").text
        assert "From your phone" in listing and "Mohab" in listing
        profile_id = re.search(r'/profiles/borrowed\?id=([0-9a-f-]{36})', listing).group(1)
        page = pc.get("/profiles/borrowed", params={"id": profile_id})
        opened = pc.post("/profiles/borrowed", data={"csrf": token(page.text), "id": profile_id, "password": PASSWORD})
        assert opened.url.path == "/", opened.text[-1500:]
        assert "Phone wallet" in pc.get("/accounts").text


def test_a_failed_move_leaves_the_profile_on_the_pc(tmp_path):
    pc, pc_app, pc_cfg, pc_devices = app_for(tmp_path, "pc", 9883)
    with pc:
        pc.get("/__launch", params={"code": pc_cfg.launch_code})
        create(pc, "Mohab")
        pc_db = pc_app.session.paths.db_path
        manage = pc.get("/profiles").text
        failed = pc.post("/profiles/move", data={"csrf": token(manage), "address": "127.0.0.1:9",
                                                 "code": "12", "pc_name": "Office PC"})
        assert failed.status_code == 400 and "stays on this PC" in failed.text
        assert pc_db.exists() and not pc_db.with_name(f"{pc_db.stem}.moving.db").exists()
