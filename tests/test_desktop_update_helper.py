"""NF-9B3: the update helper's folder swap with rollback, on a fake disk and fake processes, and the lend rule.

The swap logic is platform-neutral; every OS call goes through a host object, so these run on Linux. A power cut is
simulated between each pair of disk operations.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from lightning.desktop import update_helper as uh
from lightning.desktop.update_guard import BLOCKING, refusals
from lightning.runtime.devices import Devices
from lightning.sync.state import BorrowerState

ROOT = Path("/pc")
INSTALL, STAGED, UPDATES = ROOT / "Lightning", ROOT / "updates/2.0.4/staged", ROOT / "updates"
OLD = {"Lightning.exe": b"old exe", "lib/a.dll": b"old dll"}
NEW = {"Lightning.exe": b"new exe", "lib/a.dll": b"new dll", "lib/b.dll": b"more"}


class PowerLoss(Exception):
    pass


class Fake:
    """An in-memory disk (files by path; a folder exists while it holds a file) plus scripted processes."""

    def __init__(self, files=None, *, old_alive=0, new="ok", rename_blocked=False, corrupt_copy=False, cut_at=None):
        self.files = dict(files) if files is not None else {}
        self.clock, self.old_alive, self.new, self.rename_blocked, self.corrupt_copy = 0.0, old_alive, new, rename_blocked, corrupt_copy
        self.ops, self.cut_at, self.launched, self.terminated = 0, cut_at, [], []

    def _op(self):
        self.ops += 1
        if self.cut_at is not None and self.ops >= self.cut_at:
            raise PowerLoss

    def tree(self, folder: Path) -> dict[str, bytes]:
        prefix = str(folder) + "/"
        return {k[len(prefix):]: v for k, v in self.files.items() if k.startswith(prefix)}

    def exists(self, path):
        return str(path) in self.files or bool(self.tree(path))

    def rename(self, source, target):
        if self.rename_blocked and source == INSTALL:
            raise PermissionError("in use")
        self._op()
        assert not self.exists(target), f"rename onto {target}"
        for key in [k for k in self.files if k == str(source) or k.startswith(str(source) + "/")]:
            self.files[str(target) + key[len(str(source)):]] = self.files.pop(key)

    def rmtree(self, path):
        for key in [k for k in self.files if k.startswith(str(path) + "/")]:
            self._op()
            del self.files[key]

    def copytree(self, source, target):
        for name, body in sorted(self.tree(source).items()):
            self._op()
            self.files[f"{target}/{name}"] = body[:-1] + b"?" if self.corrupt_copy and name == "lib/a.dll" else body

    def read_text(self, path):
        try:
            return self.files[str(path)].decode()
        except KeyError:
            raise FileNotFoundError(str(path)) from None

    def write_text(self, path, text):
        self._op()
        self.files[str(path)] = text.encode()

    def append_log(self, path, line):
        self.files[str(path)] = self.files.get(str(path), b"") + line.encode() + b"\n"

    def file_hashes(self, folder):
        return {k: hashlib.sha256(v).hexdigest() for k, v in self.tree(folder).items()}

    def pid_alive(self, pid):
        return self.clock < self.old_alive

    def launch(self, exe, args):
        self.launched.append((str(exe), tuple(args)))
        if args and args[0] == "--after-update":
            if self.new == "ok":
                self.files[str(UPDATES / "ok-2.0.4")] = b"ok"
        return {"args": args}

    def exited(self, process):
        return self.new == "crash" and process["args"][0] == "--after-update"

    def terminate(self, process):
        self.terminated.append(process)

    def sleep(self, seconds):
        self.clock += seconds

    def now(self):
        return self.clock


def seed(**kw):
    files = {f"{INSTALL}/{k}": v for k, v in OLD.items()}
    files.update({f"{STAGED}/{k}": v for k, v in NEW.items()})
    fake = Fake(files, **kw)
    lines = sorted(f"{hashlib.sha256(v).hexdigest()}  {k}" for k, v in NEW.items())
    fake.files[f"{STAGED}/FILES.sha256"] = ("\n".join(lines) + "\n").encode()
    return fake


def swap(fake):
    return uh.run(fake, uh.Paths(INSTALL, STAGED, UPDATES), old_pid=7, old_version="2.0.3", new_version="2.0.4")


def installed(fake):
    return {k: v for k, v in fake.tree(INSTALL).items() if k != "FILES.sha256"}


def test_success_deletes_the_old_folder_and_launches_the_new_one():
    fake = seed()
    assert swap(fake) == "updated"
    assert installed(fake) == NEW and not fake.exists(Path(f"{INSTALL}.previous"))
    assert not fake.exists(Path(f"{INSTALL}.incoming"))
    assert fake.launched == [(f"{INSTALL}/Lightning.exe", ("--after-update", "2.0.3"))]
    assert json.loads(fake.files[str(UPDATES / "update.json")])["step"] == "ok"
    assert b"2.0.4" in fake.files[str(UPDATES / "update.log")]


def test_an_older_previous_folder_is_replaced():
    fake = seed()
    fake.files[f"{INSTALL}.previous/stale.txt"] = b"from two updates ago"
    assert swap(fake) == "updated"
    assert not fake.exists(Path(f"{INSTALL}.previous"))


def test_an_old_folder_left_by_an_earlier_update_is_deleted_at_the_next_start():
    fake = seed()
    assert swap(fake) == "updated"
    fake.files.update({f"{INSTALL}.previous/{name}": body for name, body in OLD.items()})  # left by a version that kept it
    after = Fake(fake.files)
    assert uh.repair(after, uh.Paths(INSTALL, STAGED, UPDATES)) == "cleaned"
    assert installed(after) == NEW and not after.exists(Path(f"{INSTALL}.previous"))


def test_the_old_app_never_exiting_changes_nothing_and_launches_nothing():
    fake = seed(old_alive=10**6)
    assert swap(fake) == "old app still open"
    assert installed(fake) == OLD and fake.launched == [] and 60 <= fake.clock < 62


def test_a_blocked_rename_is_retried_ten_times_then_the_old_app_comes_back_with_a_message():
    fake = seed(rename_blocked=True)
    assert swap(fake) == "rename blocked"
    assert installed(fake) == OLD and fake.clock == 9 * uh.RENAME_PAUSE
    assert fake.launched == [(f"{INSTALL}/Lightning.exe", ("--update-failed", "2.0.4"))]


def test_a_corrupt_copy_is_never_installed():
    fake = seed(corrupt_copy=True)
    assert swap(fake) == "copy corrupt"
    assert installed(fake) == OLD and not fake.exists(Path(f"{INSTALL}.incoming")) and not fake.exists(Path(f"{INSTALL}.previous"))
    assert fake.launched == [(f"{INSTALL}/Lightning.exe", ("--update-failed", "2.0.4"))]


@pytest.mark.parametrize("behaviour", ["crash", "hang"])
def test_a_new_app_that_crashes_or_hangs_is_rolled_back(behaviour):
    fake = seed(new=behaviour)
    assert swap(fake) == "new app failed"
    assert installed(fake) == OLD and fake.tree(Path(f"{INSTALL}.failed")) == {**NEW, "FILES.sha256": fake.tree(Path(f"{INSTALL}.failed"))["FILES.sha256"]} \
        or fake.tree(Path(f"{INSTALL}.failed")).keys() >= NEW.keys()
    assert fake.launched[-1] == (f"{INSTALL}/Lightning.exe", ("--update-failed", "2.0.4"))
    assert (len(fake.terminated) == 1) == (behaviour == "hang") and (behaviour == "crash" or fake.clock >= uh.WAIT_NEW_START)


def test_power_loss_between_any_two_steps_repairs_to_one_working_folder():
    total = seed()
    swap(total)
    cuts = total.ops
    assert cuts > 8
    for cut in range(1, cuts + 1):
        fake = seed(cut_at=cut)
        with pytest.raises(PowerLoss):
            swap(fake)
        disk = fake.files
        after = Fake(disk)  # the next start: a fresh process on the same disk
        uh.repair(after, uh.Paths(INSTALL, STAGED, UPDATES))
        assert not after.exists(Path(f"{INSTALL}.incoming")), cut
        got = installed(after)
        ok = after.exists(UPDATES / "ok-2.0.4")
        assert got == (NEW if ok else OLD), f"cut {cut}: only a verified new version may stay ({sorted(got)})"
        # and a second repair changes nothing
        snapshot = dict(after.files)
        uh.repair(after, uh.Paths(INSTALL, STAGED, UPDATES))
        assert after.files == snapshot


def test_a_new_version_that_wrote_its_ok_marker_before_the_cut_is_kept():
    fake = seed()
    assert swap(fake) == "updated"
    state = json.loads(fake.files[str(UPDATES / "update.json")])
    fake.files[str(UPDATES / "update.json")] = json.dumps({**state, "step": "launched"}).encode()  # cut before "ok" was written
    fake.files.update({f"{INSTALL}.previous/{name}": body for name, body in OLD.items()})  # and before the old folder went
    after = Fake(fake.files)
    assert uh.repair(after, uh.Paths(INSTALL, STAGED, UPDATES)) == "accepted"
    assert installed(after) == NEW and not after.exists(Path(f"{INSTALL}.previous"))


def test_real_host_mark_ok_writes_the_marker(tmp_path):
    uh.mark_ok(tmp_path / "updates", "2.0.4")
    assert (tmp_path / "updates" / "ok-2.0.4").exists()


# ---------------------------------------------------------------- the lend rule, with real borrower control stores

def lend_pair(tmp_path, state):
    """A real Pair (phone home + borrowing PC, encrypted files) driven to `state`."""
    import io
    from test_sync_lend import KEY, Pair
    pair = Pair(tmp_path)
    pc, link = pair.pc, pair.link
    if state is BorrowerState.PREFETCHED:
        pc.fetch(link, KEY)
    elif state is BorrowerState.BORROW_PREPARED:
        pc.fetch(link, KEY)
        link.drop_reply = True
        with pytest.raises(Exception):
            pc.borrow(link, KEY)
    elif state is BorrowerState.ABORTED:
        pc.fetch(link, KEY)
        pair.bridge.write()
        with pytest.raises(Exception):
            pc.borrow(link, KEY)
    elif state is not BorrowerState.HANDED_BACK:
        pc.fetch(link, KEY)
        pc.borrow(link, KEY)
        if state is BorrowerState.SEALED:
            pc.seal()
        elif state is BorrowerState.RETURNING:
            pair.bridge.unlocked = False
            pc.hand_back(link)
        elif state is BorrowerState.NEEDS_REPAIR:
            pair.home.take_back()
            with pytest.raises(Exception):
                pc.hand_back(link)
    assert pc.model.state is state, (state, pc.model.state)
    (pc.paths.data_dir / "profile.json").write_text(json.dumps({"name": "Mona"}))
    return pair


@pytest.mark.parametrize("state", list(BorrowerState))
def test_only_active_lends_block_an_update(tmp_path, state):
    pair = lend_pair(tmp_path, state)
    root = pair.pc.paths.data_dir.parents[1]
    found = refusals(Devices(root), None, root / "borrowed")
    if state in BLOCKING:
        assert [(r.kind, r.names) for r in found] == [("lend", ("Mona",))]
    else:
        assert found == []
    assert BLOCKING == {BorrowerState.BORROW_PREPARED, BorrowerState.BORROWING, BorrowerState.SEALED,
                        BorrowerState.RETURNING, BorrowerState.NEEDS_REPAIR}


def test_a_damaged_borrowed_store_blocks_rather_than_being_skipped(tmp_path):
    pair = lend_pair(tmp_path, BorrowerState.HANDED_BACK)
    root = pair.pc.paths.data_dir.parents[1]
    pair.pc.paths.control_path.write_bytes(b"not a database")
    assert [(r.kind, r.names) for r in refusals(Devices(root), None, root / "borrowed")] == [("lend", ("Mona",))]


def test_an_unfinished_journal_move_blocks_an_update(tmp_path):
    (tmp_path / "Home" / ".journal-move").mkdir(parents=True)
    (tmp_path / "Other").mkdir()
    assert refusals(Devices(tmp_path), tmp_path) == []
    (tmp_path / "Home" / ".journal-move" / "client.state").write_bytes(b"x")
    assert [(r.kind, r.names) for r in refusals(Devices(tmp_path), tmp_path)] == [("move", ("Home",))]
