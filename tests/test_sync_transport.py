"""Tasks 09 and 10 over real sockets on this machine: pairing, the pinned TLS link and the whole lend cycle."""
from __future__ import annotations

import json
import socket
import ssl
import uuid

import pytest

from lightning.runtime.paths import borrowed_profile
from lightning.security.keys import unwrap_key
from lightning.sync.domain import Accepted, Hello, Status
from lightning.sync.identity import load_or_create, normalize_code, show_code
from lightning.sync.service import LinkDown
from lightning.sync.state import BorrowerState, HomeState, ProtocolError
from lightning.sync.transport import (HomeServer, PairingDesk, TlsLink, join_home, link_to_home, pair, receive_message)

from test_sync_lend import KEY, Pair


class Phone:
    def __init__(self, tmp):
        self.pair = Pair(tmp)  # a phone ledger with its home node (and one in-process PC we ignore here)
        self.identity = load_or_create(tmp / "phone-id", "Mohab's phone")
        self.desk = PairingDesk()
        self.server = HomeServer(self.identity, lambda: [self.pair.home], self.desk, host="127.0.0.1", port=0).start()
        self.endpoint = f"127.0.0.1:{self.server.port}"

    def open_pairing(self):
        return self.desk.open(self.pair.home, home_name="Mohab's phone", profile_name="Mohab")


@pytest.fixture
def phone(tmp_path):
    phone = Phone(tmp_path)
    yield phone
    phone.server.stop()


def join(phone, tmp_path, name="Office PC"):
    pending = phone.open_pairing()
    pc_id = load_or_create(tmp_path / f"pc-id-{name}", name)
    paired = pair(phone.endpoint, show_code(pending.code), pc_id)
    assert paired.digits == pending.digits and pending.paired_name == name  # both screens show the same digits
    node = join_home(paired, endpoint=phone.endpoint, identity=pc_id, borrowed_profile=borrowed_profile,
                     root=tmp_path / f"pc-data-{name}")
    return node, pc_id


def test_pair_then_lend_edit_and_hand_back_over_tls(phone, tmp_path):
    node, pc_id = join(phone, tmp_path)
    from lightning.runtime.roundtrip import PASSWORD
    key = unwrap_key(json.loads(node.paths.keys_path.read_text()), PASSWORD)
    assert key == KEY  # the PC opens the profile with the same password as the phone
    link = link_to_home(node, pc_id)
    assert link.status(Status(pc_id.device_id)).state == "AT_HOME"
    node.fetch(link, key)
    node.borrow(link, key)
    assert phone.pair.home.model.state is HomeState.LENT and phone.pair.bridge.mode == "reader"
    from lightning.bootstrap import build
    container = build(node.paths.working_path, key=key)
    try:
        account = container.accounts.list()[0]
        food = container.categories.get_by_code("EXP.PERSONAL.FOOD").id
        container.transactions.record_outflow("2026-06-30", account.id, "321", food, counterparty="PC")
    finally:
        container.db.close()
    assert isinstance(node.hand_back(link), Accepted)
    assert node.model.state is BorrowerState.HANDED_BACK and phone.pair.home.model.state is HomeState.AT_HOME
    from test_sync_lend import counterparties
    assert counterparties(phone.pair.live) == ["PC"]


def test_wrong_code_three_times_closes_the_pairing(phone, tmp_path):
    pending = phone.open_pairing()
    pc_id = load_or_create(tmp_path / "pc", "Office PC")
    wrong = "".join("A" if c != "A" else "B" for c in pending.code)
    for _ in range(3):
        with pytest.raises(ProtocolError) as refused:
            pair(phone.endpoint, wrong, pc_id)
        assert refused.value.code == "PAIRING_FAILED"
    with pytest.raises(ProtocolError):
        pair(phone.endpoint, pending.code, pc_id)  # even the right code: the desk closed
    assert pc_id.device_id not in phone.pair.home.model.paired_devices


def test_code_is_used_once_and_needs_an_unlocked_phone(phone, tmp_path):
    pending = phone.open_pairing()
    phone.pair.bridge.unlocked = False
    with pytest.raises(ProtocolError) as locked:
        pair(phone.endpoint, pending.code, load_or_create(tmp_path / "a", "A"))
    assert locked.value.code == "UNLOCK_NEEDED"
    phone.pair.bridge.unlocked = True
    pair(phone.endpoint, pending.code, load_or_create(tmp_path / "b", "B"))
    with pytest.raises(ProtocolError):
        pair(phone.endpoint, pending.code, load_or_create(tmp_path / "c", "C"))


def test_another_device_at_the_phones_address_is_refused(phone, tmp_path):
    node, pc_id = join(phone, tmp_path)
    impostor = load_or_create(tmp_path / "impostor", "Impostor")
    fake = HomeServer(impostor, lambda: [phone.pair.home], PairingDesk(), host="127.0.0.1", port=0).start()
    try:
        home = node.store.peer(node.model.home_id)
        link = TlsLink(f"127.0.0.1:{fake.port}", home.certificate_sha256, pc_id)
        with pytest.raises(ProtocolError) as refused:
            link.status(Status(pc_id.device_id))
        assert refused.value.code == "UNAUTHORIZED"
    finally:
        fake.stop()


@pytest.mark.parametrize("protected", [False, True], ids=["native-default", "injected-protection"])
def test_unpaired_or_revoked_pc_and_forged_signature_are_refused(phone, tmp_path, protected):
    node, pc_id = join(phone, tmp_path)
    from test_device_credentials import TestProtector
    stranger = load_or_create(tmp_path / "stranger", "Stranger",
                              protector=TestProtector() if protected else None)
    home = node.store.peer(node.model.home_id)
    with pytest.raises(ProtocolError) as unknown:
        TlsLink(phone.endpoint, home.certificate_sha256, stranger).status(Status(stranger.device_id))
    assert unknown.value.code == "UNAUTHORIZED"
    # Lie on the wire while signing with the stranger's intact identity. Changing
    # DeviceIdentity.device_id also changes its OS key binding and fails locally.
    from types import SimpleNamespace
    forged = SimpleNamespace(device_id=pc_id.device_id, sign=stranger.sign)
    with pytest.raises(ProtocolError) as invalid_signature:
        TlsLink(phone.endpoint, home.certificate_sha256, forged).status(Status(pc_id.device_id))
    assert invalid_signature.value.code == "UNAUTHORIZED"
    assert link_to_home(node, pc_id).status(Status(pc_id.device_id)).state == "AT_HOME"
    phone.pair.home.revoke(pc_id.device_id)
    with pytest.raises(ProtocolError):
        link_to_home(node, pc_id).status(Status(pc_id.device_id))


def test_phone_out_of_reach_is_link_down(phone, tmp_path):
    node, pc_id = join(phone, tmp_path)
    phone.server.stop()
    with pytest.raises(LinkDown):
        link_to_home(node, pc_id).status(Status(pc_id.device_id))


def test_oversized_or_garbage_frames_are_refused_without_harm(phone):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
    with context.wrap_socket(socket.create_connection(("127.0.0.1", phone.server.port), timeout=5)) as stream:
        assert isinstance(receive_message(stream), Hello)
        stream.sendall((10_000_000).to_bytes(4, "big"))
        answer = receive_message(stream)
    assert answer.code == "BAD_REQUEST"
    assert phone.pair.home.model.state is HomeState.AT_HOME


def test_codes_are_typed_forgivingly():
    assert normalize_code("abcd efgh-jkmn") == "ABCDEFGHJKMN"
    with pytest.raises(ValueError):
        normalize_code("ABCD-EFGH-JKL0")  # 0 is never in a code


def test_codes_from_the_wrong_screen_say_which_screen_to_use(phone, tmp_path):
    pending = phone.desk.open_move(lambda message, source: ("", ""), home_name="My phone")
    with pytest.raises(ProtocolError) as refused:
        pair(phone.endpoint, pending.code, load_or_create(tmp_path / "pc", "Office PC"))
    assert "Move to your phone" in str(refused.value)
