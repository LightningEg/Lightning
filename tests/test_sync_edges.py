"""Phone and PC sync paths the other sync tests leave out: a version mismatch, a cancelled request, an expired or
revoked pairing, a phone without room for the copy, and a status check for a copy that never arrived."""
from __future__ import annotations

import types

import pytest

from lightning.sync import service, transport
from lightning.sync.control import new_id
from lightning.sync.domain import Accepted, BorrowActivated, ReturnStatus, Status
from lightning.sync.identity import load_or_create
from lightning.sync.service import LinkDown, require_space
from lightning.sync.state import BorrowerState, HomeState, ProtocolError
from lightning.sync.transport import link_to_home, pair as pair_with

from test_sync_lend import KEY, Pair
from test_sync_transport import Phone, join


@pytest.fixture
def pair(tmp_path):
    return Pair(tmp_path)


@pytest.fixture
def phone(tmp_path):
    phone = Phone(tmp_path)
    yield phone
    phone.server.stop()


def refused(code, call, *args, **kwargs):
    with pytest.raises(ProtocolError) as error:
        call(*args, **kwargs)
    assert error.value.code == code
    return error.value


def test_a_pc_on_another_ledger_version_is_refused_and_the_phone_stays_home(pair, monkeypatch):
    pair.pc.fetch(pair.link, KEY)
    monkeypatch.setattr(service, "BUNDLED_LATEST_VERSION", service.BUNDLED_LATEST_VERSION + 1)
    refused("INCOMPATIBLE", pair.pc.borrow, pair.link, KEY)
    assert pair.pc.model.state is BorrowerState.ABORTED and not pair.pc.writable
    assert not pair.pc.paths.working_path.exists()
    home = pair.home.model
    assert home.state is HomeState.AT_HOME and home.active is None and home.epoch == 0
    assert pair.bridge.mode == "home"


def test_a_cancelled_request_is_never_granted_and_cancelling_again_is_safe(pair):
    pair.pc.fetch(pair.link, KEY)
    granted, real = [], pair.link.borrow

    def lose_reply(request):
        granted.append(real(request))
        raise LinkDown("reply lost")
    pair.link.borrow = lose_reply
    with pytest.raises(LinkDown):
        pair.pc.borrow(pair.link, KEY)
    pair.link.borrow = real
    assert pair.pc.model.state is BorrowerState.BORROW_PREPARED and pair.home.model.state is HomeState.LENT
    pair.link.down = True
    pair.pc.cancel(pair.link)  # recorded on the PC; the phone hears it later
    assert pair.pc.model.state is BorrowerState.ABORTED and not pair.pc.writable
    assert pair.home.model.state is HomeState.LENT and pair.bridge.mode == "reader"
    pair.link.down = False
    pair.pc.cancel(pair.link)
    assert pair.home.model.state is HomeState.AT_HOME and pair.home.model.active is None
    assert pair.bridge.mode == "home"
    pair.pc.cancel(pair.link)
    grant, request = granted[0], pair.pc.model.request
    refused("CANCELLED", pair.home.activate, BorrowActivated(new_id(), grant.checkout_id, pair.device, grant.epoch),
            peer=pair.device)
    refused("CANCELLED", pair.home.borrow, request, peer=pair.device)
    refused("CANCELLED", pair.pc.store.borrower, lambda m: m.granted(grant))
    assert pair.pc.model.state is BorrowerState.ABORTED and not pair.pc.paths.working_path.exists()
    refused("STALE_AUTHORITY", pair.pc.borrow, pair.link, KEY)
    pair.pc.fetch(pair.link, KEY)
    assert pair.pc.borrow(pair.link, KEY).epoch == grant.epoch + 1


def test_a_pairing_code_older_than_ten_minutes_is_refused_and_no_pc_is_saved(phone, tmp_path, monkeypatch):
    pending = phone.open_pairing()
    later = transport.time.monotonic
    monkeypatch.setattr(transport, "time",
                        types.SimpleNamespace(monotonic=lambda: later() + transport.PAIRING_MINUTES * 60))
    pc_id = load_or_create(tmp_path / "pc", "Office PC")
    error = refused("PAIRING_FAILED", pair_with, phone.endpoint, pending.code, pc_id)
    assert str(error) == "Open Pair a PC on the phone again and type the digits it shows."
    assert pc_id.device_id not in phone.pair.home.model.paired_devices
    assert phone.pair.home.store.peer(pc_id.device_id) is None
    assert pending.paired_name == ""


def test_a_revoked_pc_pairs_again_with_a_new_code_and_borrows_at_a_higher_epoch(phone, tmp_path):
    node, pc_id = join(phone, tmp_path)
    link = link_to_home(node, pc_id)
    node.fetch(link, KEY)
    first = node.borrow(link, KEY)
    assert isinstance(node.hand_back(link), Accepted)
    phone.pair.home.revoke(pc_id.device_id)
    refused("UNAUTHORIZED", link_to_home(node, pc_id).status, Status(pc_id.device_id))
    node, again = join(phone, tmp_path)
    assert again.device_id == pc_id.device_id and pc_id.device_id in phone.pair.home.model.paired_devices
    link = link_to_home(node, pc_id)
    node.fetch(link, KEY)
    assert node.borrow(link, KEY).epoch == first.epoch + 1
    assert phone.pair.home.model.state is HomeState.LENT


def test_a_pc_without_the_phones_record_is_asked_to_pair_again(pair, tmp_path):
    assert pair.pc.store.peer(pair.pc.model.home_id) is None
    error = refused("UNAUTHORIZED", link_to_home, pair.pc, load_or_create(tmp_path / "pc-id", "Office PC"))
    assert str(error) == "Pair this PC with the phone again."


def test_space_check_leaves_64_mb_free_after_the_copy(tmp_path, monkeypatch):
    free = {"bytes": 1000 + service.SPARE_BYTES}
    monkeypatch.setattr(service.shutil, "disk_usage", lambda folder: types.SimpleNamespace(free=free["bytes"]))
    require_space(tmp_path, 1000)
    free["bytes"] -= 1
    error = refused("NO_SPACE", require_space, tmp_path, 1000)
    assert str(error).startswith("The phone does not have enough free space for the ledger.")


def test_a_phone_without_room_refuses_the_copy_keeps_the_lend_and_takes_it_once_there_is_room(pair, monkeypatch):
    pair.pc.fetch(pair.link, KEY)
    grant = pair.pc.borrow(pair.link, KEY)
    pair.pc_edit()
    real = service.shutil.disk_usage
    monkeypatch.setattr(service.shutil, "disk_usage", lambda folder: real(folder)._replace(free=service.SPARE_BYTES))
    refused("NO_SPACE", pair.pc.hand_back, pair.link)
    home = pair.home.model
    assert home.state is HomeState.LENT and home.active.grant == grant and home.epoch == grant.epoch
    assert pair.bridge.mode == "reader"
    assert list(pair.live.parent.glob("*.incoming-*")) == []
    assert pair.pc.model.state is BorrowerState.RETURNING and not pair.pc.writable
    monkeypatch.setattr(service.shutil, "disk_usage", real)
    assert isinstance(pair.pc.check_return(pair.link), Accepted)  # never arrived, so it is sent again
    assert pair.home.model.state is HomeState.AT_HOME


def test_status_of_a_copy_the_phone_never_received_is_unknown_return(pair):
    error = refused("UNKNOWN_RETURN", pair.home.return_status, ReturnStatus(new_id(), pair.device), peer=pair.device)
    assert str(error) == "The phone has not received that copy."
