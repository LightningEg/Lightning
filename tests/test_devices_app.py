"""Milestone 1 through the screens: a phone app and a PC app, each a real profile app with its own data.

The phone pairs a PC, the PC borrows the ledger, edits it while the phone only reads, and hands it back; then
the phone goes away and the PC keeps its changes sealed."""
import re

from fastapi.testclient import TestClient

from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Credentials

from test_profile_app import PASSWORD, create, token



def app_for(tmp_path, name, port):
    cfg = Credentials(f"http://127.0.0.1:{port}")
    devices = Devices(tmp_path / f"{name}-appdata", port=0, host="127.0.0.1")
    app = profile_app(cfg, tmp_path / f"{name}-docs", devices=devices)
    client = TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin})
    return client, app, cfg, devices


def add_account(browser, name):
    page = browser.get("/accounts/new")
    return browser.post("/accounts/new", data={"__session": token(page.text, "__session"), "name": name,
                                               "account_type": "CASH", "currency": "EGP", "opening_balance": "0",
                                               "opening_date": "2026-09-30"})


DIGITS = re.compile(r'aria-label="Pairing digits"[^>]*>(?:<strong[^>]*>)?(\d{2})<')


def test_pair_borrow_edit_hand_back_and_seal_through_the_screens(tmp_path, monkeypatch):
    phone, phone_app, phone_cfg, phone_devices = app_for(tmp_path, "phone", 9871)
    pc, pc_app, pc_cfg, pc_devices = app_for(tmp_path, "pc", 9872)
    with phone, pc:
        phone.get("/__launch", params={"code": phone_cfg.launch_code})
        pc.get("/__launch", params={"code": pc_cfg.launch_code})
        create(phone, "Mohab")
        assert add_account(phone, "Phone wallet").status_code == 200

        # The phone shows two digits; the PC finds the phone by itself and asks only for them (NF-4M).
        from lightning.sync import nearby
        page = phone.get("/profiles/devices")
        assert "Pair a PC" in page.text
        assert pc.get("/profiles/connect").text.count('name="endpoint"') == 0  # no phone is pairing yet
        phone.post("/profiles/devices/pair", data={"csrf": token(page.text), "phone_name": "My phone"})
        page = phone.get("/profiles/devices")
        code = DIGITS.search(page.text).group(1)
        assert 'data-refresh-seconds="3"' in page.text  # new digits after a wrong try show without a tap
        monkeypatch.setattr(nearby, "NEARBY_PORT", phone_devices.nearby.port)
        page = pc.get("/profiles/connect")
        assert "The two digits on My phone" in page.text
        endpoint = re.search(r'name="endpoint" value="([^"]+)"', page.text).group(1)
        assert endpoint == f"127.0.0.1:{phone_devices.server.port}"
        page = pc.post("/profiles/connect", data={"csrf": token(page.text), "endpoint": endpoint, "phone_name": "My phone",
                                                  "code": code, "pc_name": "Office PC"})
        assert "Connected to My phone" in page.text, page.text[-2000:]
        assert "Paired with Office PC" in phone.get("/profiles/devices").text

        # The PC borrows: it edits, the phone reads.
        listing = pc.get("/profiles").text
        assert "From your phone" in listing and "On My phone" in listing
        profile_id = re.search(r'/profiles/borrowed\?id=([0-9a-f-]{36})', listing).group(1)
        page = pc.get("/profiles/borrowed", params={"id": profile_id})
        opened = pc.post("/profiles/borrowed", data={"csrf": token(page.text), "id": profile_id,
                                                     "password": PASSWORD})
        assert opened.url.path == "/", opened.text[-1500:]
        assert "Borrowed from My phone" in pc.get("/accounts").text
        assert add_account(pc, "PC wallet").status_code == 200
        accounts = phone.get("/accounts").text
        assert "Lent to Office PC · read only" in accounts and "Phone wallet" in accounts
        refused = add_account(phone, "Not allowed")
        assert refused.status_code == 403

        # Hand back: the phone has the PC's account and writes again.
        page = pc.get("/accounts")
        done = pc.post("/sync/hand-back", data={"__session": token(page.text, "__session")})
        assert "is back on My phone" in done.text, done.text[-1500:]
        accounts = phone.get("/accounts").text
        assert "PC wallet" in accounts and "Lent to" not in accounts
        assert add_account(phone, "After").status_code == 200

        # Borrow again, then the phone goes away: closing the PC keeps the lend sealed here.
        page = pc.get("/profiles/borrowed", params={"id": profile_id})
        pc.post("/profiles/borrowed", data={"csrf": token(page.text), "id": profile_id, "password": PASSWORD})
        assert "After" in pc.get("/accounts").text
        add_account(pc, "Offline edit")
        phone_devices.stop()
        page = pc.get("/accounts")
        sealed = pc.post("/sync/hand-back", data={"__session": token(page.text, "__session")})
        assert "did not answer" in sealed.text
        assert "On this PC, not handed back" in pc.get("/profiles").text
        page = pc.get("/profiles/borrowed", params={"id": profile_id})
        reopened = pc.post("/profiles/borrowed", data={"csrf": token(page.text), "id": profile_id,
                                                       "password": PASSWORD})
        assert reopened.url.path == "/" and "Offline edit" in pc.get("/accounts").text


def test_wrong_pc_password_and_wrong_code_are_explained(tmp_path):
    phone, phone_app, phone_cfg, phone_devices = app_for(tmp_path, "phone", 9873)
    pc, pc_app, pc_cfg, pc_devices = app_for(tmp_path, "pc", 9874)
    with phone, pc:
        phone.get("/__launch", params={"code": phone_cfg.launch_code})
        pc.get("/__launch", params={"code": pc_cfg.launch_code})
        create(phone, "Mohab")
        page = phone.get("/profiles/devices")
        phone.post("/profiles/devices/pair", data={"csrf": token(page.text), "phone_name": "My phone"})
        address = f"127.0.0.1:{phone_devices.server.port}"
        page = pc.get("/profiles/connect")
        shown = DIGITS.search(phone.get("/profiles/devices").text).group(1)
        wrong = pc.post("/profiles/connect", data={"csrf": token(page.text), "address": address,
                                                   "code": f"{(int(shown) + 1) % 100:02d}", "pc_name": "Office PC"})
        assert wrong.status_code == 400 and "not the ones on the phone" in wrong.text
        assert 'value="' + address + '"' in wrong.text  # the address stays typed for the next try
