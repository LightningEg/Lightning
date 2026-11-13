"""The hand-over review (2026-10-06): each finding, reproduced, and the fix that holds it.

H1-H4 high, M5-M10 medium, L11-L13 low, S1-S3 security; the report is summarised in the changelog."""
from __future__ import annotations

import re
import shutil
import socket
import threading
import time
import urllib.parse

import pytest

from lightning.database.promotion import PromotionBlocked
from lightning.sync.domain import Accepted, Received
from lightning.sync.identity import load_or_create
from lightning.sync.service import LinkDown
from lightning.sync.state import BorrowerState, HomeState, ProtocolError
from lightning.sync.transport import HomeServer, PairingDesk, pair

from test_devices_app import add_account, app_for
from test_profile_app import PASSWORD, create, token
from test_sync_lend import KEY, Pair, counterparties
from test_sync_transport import Phone


def lent_through_the_screens(tmp_path, ports):
    """A phone app lends Mohab's ledger to a PC app; both left open."""
    phone, phone_app, phone_cfg, phone_devices = app_for(tmp_path, "phone", ports[0])
    pc, pc_app, pc_cfg, pc_devices = app_for(tmp_path, "pc", ports[1])
    phone.__enter__()
    pc.__enter__()
    phone.get("/__launch", params={"code": phone_cfg.launch_code})
    pc.get("/__launch", params={"code": pc_cfg.launch_code})
    create(phone, "Mohab")
    page = phone.get("/profiles/devices")
    phone.post("/profiles/devices/pair", data={"csrf": token(page.text), "phone_name": "My phone"})
    code = re.search(r'aria-label="Pairing digits"[^>]*>(?:<strong[^>]*>)?(\d{2})<', phone.get("/profiles/devices").text).group(1)
    page = pc.get("/profiles/connect")
    pc.post("/profiles/connect", data={"csrf": token(page.text), "address": f"127.0.0.1:{phone_devices.server.port}",
                                       "code": code, "pc_name": "Office PC"})
    profile_id = re.search(r'/profiles/borrowed\?id=([0-9a-f-]{36})', pc.get("/profiles").text).group(1)
    page = pc.get("/profiles/borrowed", params={"id": profile_id})
    opened = pc.post("/profiles/borrowed", data={"csrf": token(page.text), "id": profile_id, "password": PASSWORD})
    assert opened.url.path == "/", opened.text[-1500:]
    return phone, phone_app, phone_devices, pc


def close(*clients):
    for client in clients:
        client.__exit__(None, None, None)


# ------------------------------------------------------------ H1, H2: the phone's record, restore while lent
def test_lost_lending_record_opens_read_only_until_the_owner_keeps_this_copy(tmp_path):
    phone, phone_app, phone_devices, pc = lent_through_the_screens(tmp_path, (9891, 9892))
    try:
        selected = str(phone_app.session.paths.db_path)
        page = phone.get("/profiles")
        phone.post("/profiles/lock", data={"csrf": token(page.text)})
        shutil.rmtree(phone_devices.root / "home")  # as when the phone's app data is cleared
        phone_devices._nodes.clear()
        page = phone.get("/profiles/unlock", params={"db": selected})
        phone.post("/profiles/unlock", data={"csrf": token(page.text), "db": selected, "password": PASSWORD})
        assert add_account(phone, "Second writer").status_code == 403  # never a second writable ledger
        devices = phone.get("/profiles/devices").text
        assert "lending record is missing" in devices and "Keep this copy" in devices
        kept = phone.post("/profiles/devices/keep-home", data={"csrf": token(devices), "confirm": "yes"})
        assert "opens for editing" in kept.text
        assert add_account(phone, "Phone again").status_code == 200
    finally:
        close(pc, phone)


def test_restore_is_refused_while_the_ledger_is_lent(tmp_path):
    phone, phone_app, phone_devices, pc = lent_through_the_screens(tmp_path, (9893, 9894))
    try:
        selected = str(phone_app.session.paths.db_path)
        page = phone.get("/profiles")
        refused = phone.post("/profiles/restore", data={"csrf": token(page.text), "db": selected,
                                                        "backup": "old.lightning-backup", "confirm": "yes"})
        assert refused.status_code == 400 and "lent to a PC" in refused.text
    finally:
        close(pc, phone)


# ------------------------------------------------------------ H3: a move whose confirmation is lost
def test_lost_move_confirmation_leaves_one_ledger(tmp_path, monkeypatch):
    phone, phone_app, phone_cfg, phone_devices = app_for(tmp_path, "phone", 9895)
    pc, pc_app, pc_cfg, pc_devices = app_for(tmp_path, "pc", 9896)
    import lightning.sync.transport as transport
    real = transport.move_profile

    def lost(*args, **kwargs):
        real(*args, **kwargs)
        raise LinkDown("the phone's answer was lost")
    monkeypatch.setattr(transport, "move_profile", lost)
    with phone, pc:
        phone.get("/__launch", params={"code": phone_cfg.launch_code})
        pc.get("/__launch", params={"code": pc_cfg.launch_code})
        create(pc, "Mohab")
        pc_db = pc_app.session.paths.db_path
        page = phone.get("/profiles/receive")
        phone.post("/profiles/receive", data={"csrf": token(page.text), "phone_name": "My phone"})
        code = re.search(r'aria-label="Pairing digits"[^>]*>(?:<strong[^>]*>)?(\d{2})<', phone.get("/profiles/receive").text).group(1)
        failed = pc.post("/profiles/move", data={"csrf": token(pc.get("/profiles").text), "code": code,
                                                 "address": f"127.0.0.1:{phone_devices.server.port}"})
        assert "stays on this PC" in failed.text and pc_db.exists()
        assert "Waiting for" in phone.get("/profiles/receive").text
        assert "Mohab" not in phone.get("/profiles").text  # nothing the phone can open: one ledger only


def test_a_move_cut_off_by_a_crash_is_finished_at_start(tmp_path):
    from lightning.runtime.devices import Devices, MOVING_MARK, recover_moves
    devices = Devices(tmp_path / "appdata")
    folder = tmp_path / "docs" / "Mohab_2026-10-06_001_abcd1234"
    folder.mkdir(parents=True)
    (folder / f"{folder.name}.moving.db").write_bytes(b"ledger")
    (folder / MOVING_MARK).write_text('{"profile_id": "6f1c3a8e-1d2b-4c5d-8e9f-0a1b2c3d4e5f"}')
    recover_moves(devices, tmp_path / "docs")
    assert (folder / f"{folder.name}.db").read_bytes() == b"ledger"  # the phone never kept it: the PC's again
    assert not (folder / MOVING_MARK).exists()


# ------------------------------------------------------------ H4, M5: take back and borrow mid hand-back
def test_take_back_is_refused_while_the_pcs_copy_waits_to_go_in(tmp_path):
    pair = Pair(tmp_path)
    pair.pc.fetch(pair.link, KEY)
    pair.pc.borrow(pair.link, KEY)
    pair.pc_edit()
    pair.bridge.unlocked = False
    assert isinstance(pair.pc.hand_back(pair.link), Received)
    with pytest.raises(ProtocolError) as busy:
        pair.home.take_back()
    assert busy.value.code == "BUSY"
    pair.bridge.unlocked = True
    pair.home.recover()
    assert counterparties(pair.live) == ["PC"] and pair.home.writable()


def test_take_back_and_borrow_wait_for_an_unfinished_promotion(tmp_path, monkeypatch):
    pair = Pair(tmp_path)
    monkeypatch.setattr(type(pair.home.store), "unresolved_promotion", lambda self: object())
    with pytest.raises(ProtocolError) as busy:
        pair.home.take_back()
    assert busy.value.code == "BUSY"
    pair.pc.fetch(pair.link, KEY)
    with pytest.raises(ProtocolError) as waiting:
        pair.pc.borrow(pair.link, KEY)
    assert waiting.value.code == "BUSY" and pair.bridge.mode == "home"  # never switched, never opened early


# ------------------------------------------------------------ M6, M7, L13: the PC after a take back
def test_pc_borrows_again_after_a_take_back_and_keeps_its_copy(tmp_path):
    pair = Pair(tmp_path)
    pair.pc.fetch(pair.link, KEY)
    pair.pc.borrow(pair.link, KEY)
    pair.pc_edit()
    pair.home.take_back()
    with pytest.raises(ProtocolError):
        pair.pc.hand_back(pair.link)
    assert pair.pc.model.state is BorrowerState.NEEDS_REPAIR
    kept = pair.pc.start_over()
    assert counterparties(kept) == ["PC"]  # the PC's edits stay on it, as a backup
    pair.pc.fetch(pair.link, KEY)  # follows the phone's new lineage
    pair.pc.borrow(pair.link, KEY)
    assert pair.pc.writable and pair.home.model.state is HomeState.LENT


def test_a_copy_that_will_never_go_in_is_not_received_forever(tmp_path):
    pair = Pair(tmp_path)
    pair.pc.fetch(pair.link, KEY)
    pair.pc.borrow(pair.link, KEY)
    pair.pc_edit()
    pair.bridge.unlocked = False
    begin_receipt = pair.pc.hand_back(pair.link)
    incoming = pair.home._incoming(begin_receipt.return_id)
    incoming.write_bytes(incoming.read_bytes()[:-10] + b"x" * 10)  # damaged on the phone
    pair.bridge.unlocked = True
    with pytest.raises(Exception):
        pair.home.recover()
    assert pair.home.model.state is HomeState.NEEDS_REPAIR
    pair.home.take_back()
    with pytest.raises(ProtocolError) as stale:
        pair.pc.check_return(pair.link)
    assert stale.value.code == "STALE_AUTHORITY" and pair.pc.model.state is BorrowerState.NEEDS_REPAIR


def test_hand_back_after_a_take_back_is_a_message_not_an_error(tmp_path):
    from lightning.runtime.devices import Devices
    pair = Pair(tmp_path)
    pair.pc.fetch(pair.link, KEY)
    pair.pc.borrow(pair.link, KEY)
    pair.home.take_back()
    devices = Devices(tmp_path / "appdata")
    devices.link = lambda node, timeout=None: pair.link
    assert devices.hand_back_or_seal(pair.pc) == "refused"


def test_sealed_copy_is_not_reopened_after_a_take_back(tmp_path):
    from lightning.runtime.devices import Devices
    pair = Pair(tmp_path)
    pair.pc.fetch(pair.link, KEY)
    pair.pc.borrow(pair.link, KEY)
    pair.pc.seal()
    pair.home.take_back()
    devices = Devices(tmp_path / "appdata")
    devices.link = lambda node, timeout=None: pair.link
    assert devices.taken_back(pair.pc) and pair.pc.model.state is BorrowerState.NEEDS_REPAIR


# ------------------------------------------------------------ M8, M9, L11, L12: the phone stays usable
def test_take_back_answers_busy_instead_of_freezing(tmp_path, monkeypatch):
    import lightning.sync.service as service
    monkeypatch.setattr(service, "OWNER_WAIT", 0.2)
    pair = Pair(tmp_path)
    pair.pc.fetch(pair.link, KEY)
    pair.pc.borrow(pair.link, KEY)
    held, release = threading.Event(), threading.Event()

    def transfer():
        with pair.home._lock:
            held.set()
            release.wait(5)
    worker = threading.Thread(target=transfer)
    worker.start()
    held.wait(5)
    started = time.monotonic()
    try:
        with pytest.raises(ProtocolError) as busy:
            pair.home.take_back()
        assert busy.value.code == "BUSY" and time.monotonic() - started < 2
    finally:
        release.set()
        worker.join()


def test_one_damaged_record_does_not_cut_off_other_profiles(tmp_path):
    class Damaged:
        @property
        def store(self):
            raise RuntimeError("damaged record")
    good = Pair(tmp_path)
    identity = load_or_create(tmp_path / "phone-id", "My phone")
    server = HomeServer(identity, lambda: [Damaged(), good.home], PairingDesk(), host="127.0.0.1", port=0)
    try:
        assert server._node_for(good.device) is good.home
    finally:
        server.listener.close()


def test_a_tampered_copy_needs_repair_instead_of_retrying_every_unlock(tmp_path, monkeypatch):
    pair = Pair(tmp_path)
    pair.pc.fetch(pair.link, KEY)
    pair.pc.borrow(pair.link, KEY)
    pair.bridge.unlocked = False
    begin = pair.pc.hand_back(pair.link)
    pair.bridge.unlocked = True
    sidecar = pair.home._incoming(begin.return_id).with_name(pair.home._incoming(begin.return_id).name + "-wal")
    sidecar.write_bytes(b"planted")
    with pytest.raises(PromotionBlocked):
        pair.home.recover()
    assert pair.home.model.state is HomeState.NEEDS_REPAIR


def test_old_copies_from_hand_backs_do_not_pile_up(tmp_path):
    pair = Pair(tmp_path)
    for amount in ("1", "2", "3", "4", "5"):
        pair.pc.fetch(pair.link, KEY)
        pair.pc.borrow(pair.link, KEY)
        pair.pc_edit(amount)
        assert isinstance(pair.pc.hand_back(pair.link), Accepted)
    assert len(list(pair.live.parent.glob("*.before-*.db"))) <= 3


# ------------------------------------------------------------ S1, S2: other devices on the Wi-Fi
def test_wrong_codes_from_another_device_do_not_close_the_owners_code(tmp_path):
    from lightning.sync.domain import PasskeyCommit, PasskeyReveal
    from lightning.sync.passkey import V2_MARKER
    phone = Phone(tmp_path)
    try:
        pending = phone.open_pairing()
        for _ in range(3):  # another device on the Wi-Fi guesses: each try fails at its first bit
            with phone.desk._lock:
                digits = phone.desk._begin(pending, V2_MARKER, "192.168.1.66")
            answers = iter([PasskeyCommit(0, "0" * 64), PasskeyReveal(0, "0" * 64)])
            with pytest.raises(ProtocolError):
                phone.desk._rounds(pending, digits, b"guess", lambda message: None, lambda: next(answers), "192.168.1.66")
        with pytest.raises(ProtocolError) as blocked:
            with phone.desk._lock:
                phone.desk._begin(pending, V2_MARKER, "192.168.1.66")
        assert "Three tries" in str(blocked.value)
        paired = pair(phone.endpoint, pending.code, load_or_create(tmp_path / "pc", "Office PC"))
        assert paired.digits == pending.digits  # the owner's PC still pairs, with the digits shown now
    finally:
        phone.server.stop()


def test_one_device_cannot_take_every_connection(tmp_path):
    import lightning.sync.transport as transport
    phone = Phone(tmp_path)
    held = []
    try:
        for _ in range(transport.MAX_PER_ADDRESS):
            held.append(socket.create_connection(("127.0.0.1", phone.server.port)))
        time.sleep(0.2)
        extra = socket.create_connection(("127.0.0.1", phone.server.port))
        extra.settimeout(3)
        assert extra.recv(1) == b""  # closed at once: that address already holds its share
        extra.close()
    finally:
        for sock in held:
            sock.close()
        phone.server.stop()


def test_hand_back_to_a_phone_that_forgot_this_pc_says_so(tmp_path):
    from lightning.runtime.devices import Devices
    pair = Pair(tmp_path)
    pair.pc.fetch(pair.link, KEY)
    pair.pc.borrow(pair.link, KEY)
    pair.home.revoke(pair.device)
    devices = Devices(tmp_path / "appdata")
    devices.link = lambda node, timeout=None: pair.link
    assert devices.hand_back_or_seal(pair.pc) == "unpaired" and pair.pc.model.state is BorrowerState.SEALED
