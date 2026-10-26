"""Single-owner encrypted profile lifecycle. Never opens a profile implicitly."""
from __future__ import annotations

import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from lightning.bootstrap import Container, ReadOnlyCopyError, build
from lightning.database.connection import Database
from lightning.database.currencies import CurrencyRegistry
from lightning.database.seed import CASH_ASSETS
from lightning.database.migrator import inspect_schema
from lightning.database.snapshot import verify_connection
from lightning.security.keys import (clean_question, create_key_file, key_id, new_data_key, new_recovery_key,
                                     normalize_answer, normalize_recovery_key, open_with_recovery, proof_kind,
                                     unwrap_key, validate_key_file, with_password, with_question, with_recovery_key)

from .instance import InstanceAlreadyRunning, InstanceLock
from .paths import ProfilePaths, choose_data_root, create_profile, resolve_profile
from .roles import SessionRole


class ProfileError(ValueError):
    """Safe, deliberately authored messages suitable for the locked UI."""


PROFILE_CURRENCIES = frozenset(code for code, _ in CASH_ASSETS)


def validate_password(password: str, confirm: str) -> None:
    """Any password the person can type twice (owner decision 2026-10-05: no length rule, only advice)."""
    if password != confirm:
        raise ProfileError("The passwords do not match.")
    if not password or len(password.encode("utf-8")) > 4096:
        raise ProfileError("Type a password.")


def _readable(exc: ValueError) -> ProfileError:
    return ProfileError(str(exc))


# Owner decision 2026-10-05: five free tries, then a growing wait. Never a permanent lockout: that would
# mostly lock out the owner, and someone with copied files is not slowed by the app anyway.
FREE_TRIES = 5
WAITS = (60, 300, 900, 3600)


class AttemptGuard:
    """Wrong passwords, recovery keys and answers for one profile, kept beside its key file."""

    def __init__(self, path: Path, clock=None):
        self.path, self.clock = path, clock or time.time

    def _read(self) -> tuple[int, float]:
        try:
            with self.path.open("rb") as handle:
                document = json.loads(handle.read(1025))
            failures, last = document["failures"], document["last"]
            if type(failures) is not int or failures < 0 or not isinstance(last, (int, float)):
                raise ValueError
            return failures, float(last)
        except FileNotFoundError:
            return 0, 0.0
        except (OSError, ValueError, KeyError, TypeError):
            return FREE_TRIES, self.clock()  # a damaged record waits once, never locks out

    def wait_left(self) -> int:
        failures, last = self._read()
        if failures < FREE_TRIES:
            return 0
        now = self.clock()
        wait = WAITS[min(failures - FREE_TRIES, len(WAITS) - 1)]
        return max(0, int(min(last, now) + wait - now + 0.999))

    def check(self) -> None:
        left = self.wait_left()
        if left:
            minutes = (left + 59) // 60
            wait = "1 hour" if minutes >= 60 else f"{minutes} minute{'s' if minutes != 1 else ''}"
            raise ProfileError(f"Too many wrong tries. Try again in {wait}.")

    def failed(self) -> None:
        failures, _ = self._read()
        if self.path.parent.is_dir() and not self.path.is_symlink():
            temporary = self.path.with_name(f".attempts-{secrets.token_hex(8)}.partial")
            temporary.write_text(json.dumps({"failures": failures + 1, "last": self.clock()}), "utf-8")
            os.replace(temporary, self.path)

    def succeeded(self) -> None:
        if not self.path.is_symlink():
            self.path.unlink(missing_ok=True)


def read_slot(path: Path) -> dict:
    if path.is_symlink():
        raise ProfileError("A password file must not be a symbolic link.")
    try:
        with path.open("rb") as handle:
            raw = handle.read(16385)
        if len(raw) > 16384:
            raise ValueError("oversized")
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise ValueError("object required")
        return document
    except (OSError, ValueError) as exc:
        raise ProfileError("The password file is missing or invalid. Use your recovery key.") from exc


def publish_new(temporary: Path, target: Path) -> None:
    """Put a finished file at a name that must not exist yet, never replacing one. A hard link does this on
    Windows and POSIX; Android refuses hard links in app storage, so there, with the name still free, the file
    is renamed into place (the profile folder is private to the app, so nothing else races for the name)."""
    try:
        os.link(temporary, target)
    except PermissionError:
        if os.path.lexists(target):
            raise FileExistsError(target) from None
        os.rename(temporary, target)
        return
    temporary.unlink()


def write_slot(path: Path, document: dict, *, replace: bool = False) -> None:
    """Durable atomic slot publication, never truncate the working password file."""
    if path.is_symlink():
        raise ProfileError("A password file must not be a symbolic link.")
    temporary = path.with_name(f".keys-{secrets.token_hex(12)}.partial")
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(json.dumps(document, sort_keys=True).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            publish_new(temporary, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def key_file_copy(paths: ProfilePaths) -> Path:
    """A second copy of the key file. The recovery lock lives in the key file, so losing that one file
    would make the password, the recovery key and the answer all useless; this copy survives it."""
    return paths.backups_dir / "keys.json"


def publish_keys(paths: ProfilePaths, document: dict, *, replace: bool = True) -> None:
    write_slot(paths.keys_path, document, replace=replace)
    paths.backups_dir.mkdir(exist_ok=True)
    write_slot(key_file_copy(paths), document, replace=True)


def read_keys(paths: ProfilePaths) -> dict:
    """The key file, or its copy when the key file is missing or damaged."""
    for path in (paths.keys_path, key_file_copy(paths)):
        try:
            document = read_slot(path)
            validate_key_file(document)
            return document
        except (ProfileError, ValueError):
            continue
    raise ProfileError("The key file and its copy are missing or damaged. Restore them from a backup of this profile's folder.")


def _fill_prices(container: Container) -> None:
    """Prices, missing month-end closes (fetched on another thread) and due month-end checkpoints; the same
    list `python -m lightning` runs. Opening a profile never fails because of it."""
    from lightning.workflows.profile_open import open_profile_tasks
    open_profile_tasks(container, wait=False)


@dataclass
class PendingProfile:
    paths: ProfilePaths
    recovery: str
    key: bytes
    slot: dict          # the whole key file: both locks, the question and the checks
    base_currency: str
    expires: float


@dataclass
class PendingRecoveryKey:
    recovery: str
    base: dict          # the key file it replaces; publishing refuses if that changed meanwhile
    key_file: dict
    expires: float


class ProfileSession:
    """All methods are called on the ASGI owning thread under the request gate."""

    def __init__(self, root: str | Path | None = None):
        self.root = choose_data_root(root)
        self.container: Container | None = None
        self.role = SessionRole.HOME
        self.paths: ProfilePaths | None = None
        self.lock: InstanceLock | None = None
        self.pending: PendingProfile | None = None
        self.pending_recovery: PendingRecoveryKey | None = None
        self.token = secrets.token_urlsafe(32)
        self.csrf = secrets.token_urlsafe(32)
        self.retry_at = 0.0
        self.last_activity = time.monotonic()
        self.idle_seconds = 15 * 60
        self.sync_key: bytes | None = None   # for the sync thread while unlocked (multiple devices); wiped on close
        self.label = ""                       # a borrowed profile's name (its working file has none)
        self.borrowed = None                  # the BorrowerNode of an open borrowed profile, else None
        self.journal = None
        self.enrollment = None

    @property
    def name(self) -> str:
        if self.paths is None:
            return ""
        if self.label:
            return self.label
        return self.paths.profile.name if self.paths.profile else self.paths.db_path.stem

    def _locked(self) -> None:
        if self.container is not None:
            raise ProfileError("Lock the current profile before choosing another one.")

    def prepare(self, name: str, password: str, confirm: str, question: str, answer: str,
                currency: str = "EGP") -> PendingProfile:
        self._locked()
        validate_password(password, confirm)
        if not name.strip() or len(name) > 200:
            raise ProfileError("Enter a profile name of 1–200 characters.")
        currency = currency.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", currency) or currency not in PROFILE_CURRENCIES:
            raise ProfileError("Choose a currency from the list.")
        try:
            question, _ = clean_question(question), normalize_answer(answer)
        except ValueError as exc:
            raise _readable(exc) from exc
        paths = create_profile(name, root=self.root)
        key, recovery = new_data_key(), new_recovery_key()
        self.pending = PendingProfile(paths, recovery, key, create_key_file(key, password, recovery, question, answer),
                                      currency, time.monotonic() + 900)
        # Invalidate confirmation forms from any older setup tab. Otherwise a
        # user could acknowledge key A while the pending database uses key B.
        self.csrf = secrets.token_urlsafe(32)
        return self.pending

    def confirm(self, typed_recovery: str) -> None:
        """Create the profile once its recovery key is typed back, so a copying mistake shows now."""
        self._locked()
        pending = self.pending
        if pending is None or time.monotonic() >= pending.expires:
            self.pending = None
            raise ProfileError("Setup expired. Create the profile again.")
        try:
            typed = normalize_recovery_key(typed_recovery)
        except ValueError:
            typed = ""
        if not secrets.compare_digest(typed, normalize_recovery_key(pending.recovery)):
            raise ProfileError("That is not the recovery key shown. Check what you wrote down and type it again.")
        paths = pending.paths
        paths.prepare()  # Exclusive directory; never reuse a failed or existing profile.
        lock = InstanceLock(paths.lock_path).acquire()
        candidate = paths.db_path.with_suffix(".partial")
        container = None
        try:
            publish_keys(paths, pending.slot, replace=False)
            container = build(candidate, key=pending.key, backup_dir=paths.backups_dir)
            verify_connection(container.db.conn, encrypted=True)
            container.db.close()
            container = None
            with candidate.open("r+b") as handle:
                os.fsync(handle.fileno())
            publish_new(candidate, paths.db_path)  # No replacement even in a collision.
            if os.name != "nt":
                directory = os.open(paths.data_dir, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            container = build(paths.db_path, key=pending.key, backup_dir=paths.backups_dir)
            CurrencyRegistry(container.db).register(pending.base_currency)
            container.set_profile_currency(pending.base_currency)
            self._activate(paths, lock, container)
        except BaseException:
            if container is not None:
                container.db.close()
            lock.close()
            raise
        finally:
            # Failed directories remain as recognizable recovery evidence.
            self.pending = None

    def _activate(self, paths: ProfilePaths, lock: InstanceLock, container: Container,
                  role: SessionRole = SessionRole.HOME, *, journal=None) -> None:
        if container.db.read_only == role.writable:
            raise ProfileError("The profile opened with the wrong kind of connection for its role.")
        self.paths, self.lock, self.container, self.role = paths, lock, container, role
        self.journal = journal
        self.sync_key = container.db.copy_key() if container.db.encrypted else None
        if role.writable and journal is None:
            _fill_prices(container)
        self.token = secrets.token_urlsafe(32)
        self.csrf = secrets.token_urlsafe(32)
        self.pending = None
        self.retry_at = 0.0
        self.last_activity = time.monotonic()

    def _select(self, selected: str) -> ProfilePaths:
        self._locked()
        if not selected or len(selected) > 4096:
            raise ProfileError("Choose an existing database file.")
        paths = resolve_profile(db_path=selected)
        if not paths.db_path.is_file() or paths.db_path.stat().st_size == 0:
            raise ProfileError("The selected database does not exist or is empty.")
        # Completed snapshots must never become live databases through the picker.
        if paths.db_path.parent.name == "backups" or "_backup_" in paths.db_path.stem or "_upgrade_" in paths.db_path.stem:
            raise ProfileError("This is a backup. Keep it unchanged; restoring into a new profile is not available yet.")
        with paths.db_path.open("rb") as handle:
            if handle.read(16) == b"SQLite format 3\x00":
                raise ProfileError("This is an unencrypted legacy database. It has not been changed. Explicit import is not available yet.")
        for companion in (paths.data_dir, paths.keys_path, paths.backups_dir, paths.lock_path):
            if companion.is_symlink():
                raise ProfileError("Profile companion files must not be symbolic links.")
        return paths

    def _acquire(self, paths: ProfilePaths) -> InstanceLock:
        paths.prepare()
        try:
            return InstanceLock(paths.lock_path).acquire()
        except InstanceAlreadyRunning as exc:
            raise ProfileError("This profile is open in another Lightning process. Close it there first.") from exc

    def _attempt(self) -> None:
        """A short pause between tries within this window (restore uses it; unlock and recovery also wait)."""
        if time.monotonic() < self.retry_at:
            raise ProfileError("Please wait a moment before trying again.")
        self.retry_at = time.monotonic() + 2

    @staticmethod
    def attempts(paths: ProfilePaths) -> AttemptGuard:
        return AttemptGuard(paths.keys_path.with_name("attempts.json"))

    def current_question(self) -> str:
        if self.paths is None:
            return ""
        try:
            return read_keys(self.paths)["question"]
        except ProfileError:
            return ""

    def question(self, selected: str) -> str:
        """The security question shown on the recovery page (it is not secret)."""
        paths = self._select(selected)
        return read_keys(paths)["question"]

    def unlock(self, selected: str, password: str, *, role: SessionRole = SessionRole.HOME) -> None:
        """Open a profile. A reader opens a real read-only connection with no startup writes (no backup,
        migration or seed), and refuses a copy that would need an upgrade."""
        paths = self._select(selected)
        attempts = self.attempts(paths)
        attempts.check()
        lock = self._acquire(paths)
        try:
            try:
                document = read_keys(paths)
                key = unwrap_key(document, password)
            except ProfileError:
                raise
            except ValueError as exc:
                attempts.failed()
                raise ProfileError("The password is incorrect.") from exc
            attempts.succeeded()
            self._open(paths, lock, document, key, role)
        except BaseException:
            lock.close()
            raise

    def _open(self, paths: ProfilePaths, lock: InstanceLock, document: dict, key: bytes, role: SessionRole) -> None:
        """What follows any unlock that has the data key, whichever way it was obtained: put back a missing key
        file, check an interrupted restore, verify the database, open it in `role`. The caller closes `lock`
        if this raises."""
        try:
            if read_slot(paths.keys_path) != document:
                raise ProfileError("damaged")
        except ProfileError:
            publish_keys(paths, document)  # put back a missing or damaged key file from its copy
        from lightning.runtime.restore import EncryptedBackupRestorer
        EncryptedBackupRestorer._check_restore_control(paths, key)
        self._verify(paths, key)
        probe = Database(paths.db_path, key=key, read_only=True)
        try:
            is_journal = probe.has_table("journal_meta")
        finally:
            probe.close()
        restore_descriptor = paths.db_path.with_name(paths.db_path.name + ".journal-restore.json")
        if restore_descriptor.exists():
            restored = read_slot(restore_descriptor)
            if restored.get("status") != "requires-enrollment":
                raise ProfileError("The restored comparison copy is incomplete. Preserve it for repair.")
            role = SessionRole.READER
        if is_journal and role is not SessionRole.READER:
            from .journal_profile import JournalRuntime
            from lightning.sync.journal.upgrades import upgrade_profile
            upgrade_profile(paths, key)
            container = build(paths.db_path, key=key, backup_dir=paths.backups_dir, experimental_journal=True)
            runtime = None
            try:
                runtime = JournalRuntime(container, paths, document)
                self._activate(paths, lock, runtime.services, SessionRole.HOME, journal=runtime)
            except BaseException:
                if runtime is not None:
                    runtime.close()
                container.db.close()
                raise
            return
        if role.writable:
            # _verify just checked this file: the start backup (at most one a day) checks only its copy (2J).
            container = build(paths.db_path, key=key, backup_dir=paths.backups_dir, backup_on_start=True,
                              source_verified=True)
        else:
            try:
                container = build(paths.db_path, key=key, read_only=True, experimental_journal=is_journal)
            except ReadOnlyCopyError as exc:
                raise ProfileError(str(exc)) from exc
        self._activate(paths, lock, container, role)

    def fingerprint_target(self, selected: str) -> tuple[str, str]:
        """(profile id, key id) of a locked profile, for the phone's fingerprint unlock; ("", "") when the profile
        has no identifier or its key file cannot be read (the password screen says why)."""
        paths = self._select(selected)
        if paths.profile is None:
            return "", ""
        try:
            return paths.profile.profile_id, read_keys(paths)["key_id"]
        except ProfileError:
            return "", ""

    def enable_journal(self, password: str, recovery: str, answer: str, *, selected: str = "",
                       legacy_state: str = "AT_HOME", retain_stranded: bool = False) -> None:
        """Explicitly convert or finish an interrupted conversion under the profile lock."""
        from lightning.security.keys import open_with_recovery
        from lightning.sync.identity import load_or_create
        from lightning.sync.journal.cutover import begin
        from .journal_profile import JournalRuntime, provision
        if self.journal is not None:
            return
        if self.borrowed is not None:
            raise ProfileError("Return this borrowed copy before changing its synchronization.")
        paths = self.paths if self.container is not None else self._select(selected)
        lock = self.lock if self.container is not None else self._acquire(paths)
        original = self.container
        container = original
        runtime = None
        try:
            attempts = self.attempts(paths)
            attempts.check()
            document = read_keys(paths)
            try:
                key = unwrap_key(document, password)
                recovered = open_with_recovery(document, recovery, answer)
                if not secrets.compare_digest(key, recovered):
                    raise ValueError("key mismatch")
            except ValueError as error:
                attempts.failed()
                raise ProfileError("Check your password, recovery key and security answer.") from error
            attempts.succeeded()
            if container is None or container.db.read_only:
                if container is not None:
                    container.db.close()
                    self.container = None
                probe = Database(paths.db_path, key=key, read_only=True)
                try:
                    is_journal = probe.has_table("journal_meta")
                finally:
                    probe.close()
                container = build(paths.db_path, key=key, backup_dir=paths.backups_dir,
                                  experimental_journal=is_journal)
            identity = load_or_create(paths.data_dir / "identity", "This device")
            store, _ = begin(container, paths, identity, legacy_state=legacy_state,
                             retain_stranded=retain_stranded)
            provision(store, identity, paths, password=password, recovery=recovery, answer=answer)
            runtime = JournalRuntime(container, paths, document)
            self._activate(paths, lock, runtime.services, journal=runtime)
        except BaseException:
            # Once journal metadata exists, the ordinary service graph must never
            # remain available to legacy writers, including on setup failure.
            if runtime is not None:
                runtime.close()
            if container is not None:
                container.db.close()
            self.container = None
            if self.lock is lock:
                self.close()
            else:
                lock.close()
            raise

    def unlock_with_key(self, selected: str, key: bytes, *, role: SessionRole = SessionRole.HOME) -> None:
        """Open a profile with its data key, already released by the phone's fingerprint. It takes the same road
        as a password unlock after the password step (restore checks, verification, roles), refuses a key that is
        not the one in keys.json, and counts nothing: Android counts fingerprint failures, and a fingerprint
        neither guesses the password nor clears its wait."""
        paths = self._select(selected)
        lock = self._acquire(paths)
        try:
            document = read_keys(paths)
            if not isinstance(key, bytes) or len(key) != 32 or not secrets.compare_digest(key_id(key), document["key_id"]):
                raise ProfileError("That fingerprint key does not belong to this profile. Unlock with your password.")
            self._open(paths, lock, document, key, role)
        except BaseException:
            lock.close()
            raise

    def change_role(self, role: SessionRole) -> None:
        """Reopen the open profile in another role, keeping its instance lock and needing no password.

        The caller holds the request gate (`SessionGate.change_role`), so no request is in flight: the gate is
        closed and drained before the new role is published (plan section 5, rule 1). A new generation token
        means no form rendered under the old role can save. If the reopen fails, the profile is locked."""
        if self.container is None or self.paths is None:
            raise ProfileError("Unlock a profile first.")
        if self.journal is not None:
            raise ProfileError("Synchronized profiles use journal authority. Legacy lending cannot change their role.")
        if role is self.role:
            return
        key = self.container.db.copy_key()
        self.container.db.close()
        self.container = None
        try:
            container = build(self.paths.db_path, key=key, read_only=not role.writable)
        except BaseException:
            self.close()
            raise
        self._activate(self.paths, self.lock, container, role)

    def restore_backup(self, selected: str, backup_path: str, password: str) -> str | None:
        from lightning.runtime.restore import EncryptedBackupRestorer
        candidate = Path(backup_path)
        manifest = candidate.with_suffix(".journal-manifest.json")
        if manifest.exists():
            from lightning.sync.journal.backups import restore_copy
            from uuid import uuid4
            paths = self._select(selected)
            if candidate.is_symlink() or candidate.resolve().parent != paths.backups_dir.resolve():
                raise ProfileError("Choose a backup belonging to this profile.")
            document = read_keys(paths)
            attempts = self.attempts(paths)
            attempts.check()
            try:
                key = unwrap_key(document, password)
            except ValueError as error:
                attempts.failed()
                raise ProfileError("The password is incorrect.") from error
            attempts.succeeded()
            restored = create_profile((paths.profile.name if paths.profile else "Profile") + " restored", root=self.root)
            restored.prepare()
            with InstanceLock(restored.lock_path):
                restore_copy(candidate, manifest.read_bytes(), backup_key=key, target=restored.db_path,
                             new_device=str(uuid4()), new_incarnation=str(uuid4()))
                publish_keys(restored, document, replace=False)
            return str(restored.db_path)
        # A journal snapshot must never enter legacy promotion: it could rewind
        # authority or reuse an origin counter. Only signed package recovery above
        # can create a quarantined comparison copy.
        paths = self._select(selected)
        if (paths.data_dir / "journal-native.json").exists() or (paths.data_dir / "complete.json").exists():
            raise ProfileError("Choose a signed journal backup. Upgrade checkpoints are retained for explicit repair.")
        EncryptedBackupRestorer(self).restore_backup(selected, backup_path, password)

    def resume_interrupted_restore(self, selected: str, password: str) -> None:
        from lightning.runtime.restore import EncryptedBackupRestorer

        EncryptedBackupRestorer(self).resume_interrupted_restore(selected, password)

    @staticmethod
    def _verify(paths: ProfilePaths, key: bytes) -> None:
        db = Database(paths.db_path, key=key, read_only=True)
        try:
            if not db.has_table("schema_migrations"):
                raise ProfileError("The selected file is not a Lightning database.")
            inspect_schema(db)
            verify_connection(db.conn, encrypted=True)
        finally:
            db.close()

    def recover(self, selected: str, recovery: str, answer: str, password: str, confirm: str) -> None:
        """Forgot the password: the recovery key and the security answer together set a new one."""
        validate_password(password, confirm)
        paths = self._select(selected)
        attempts = self.attempts(paths)
        attempts.check()
        lock = self._acquire(paths)
        try:
            document = read_keys(paths)
            try:
                key = open_with_recovery(document, recovery, answer)
            except ValueError as exc:
                attempts.failed()
                raise ProfileError("The recovery key and answer do not open this profile. Check both and try again.") from exc
            try:
                self._verify(paths, key)
            except Exception as exc:
                raise ProfileError("The recovery key opened the key file, but the database needs repair or a newer app.") from exc
            attempts.succeeded()
            publish_keys(paths, with_password(document, key, password))
        finally:
            lock.close()

    # ------------------------------------------------------------ changes while the profile is open
    # Owner decision 2026-10-05: an unlocked profile counts as the password, so each change asks for one
    # more proof. Any two of password, recovery key and answer can always restore the third.
    def _open_key_file(self) -> tuple[dict, bytes, AttemptGuard]:
        if self.paths is None or self.container is None:
            raise ProfileError("Unlock a profile first.")
        attempts = self.attempts(self.paths)
        attempts.check()
        return read_keys(self.paths), self.container.db.copy_key(), attempts

    def _prove(self, document: dict, key: bytes, attempts: AttemptGuard, proof: str, *accepted: str) -> str:
        try:
            kind = proof_kind(document, key, proof)
        except ValueError as exc:
            raise _readable(exc) from exc
        if kind not in accepted:
            attempts.failed()
            names = " or ".join({"answer": "your security answer", "recovery": "your recovery key"}[k] for k in accepted)
            raise ProfileError(f"That is not {names}.")
        attempts.succeeded()
        return kind

    def change_password(self, proof: str, password: str, confirm: str) -> None:
        """New password: the open profile plus the security answer or the recovery key."""
        validate_password(password, confirm)
        document, key, attempts = self._open_key_file()
        self._prove(document, key, attempts, proof, "answer", "recovery")
        publish_keys(self.paths, with_password(document, key, password))

    def prove_password(self, password: str) -> bytes:
        """The password typed again by the person with the profile open (fresh proof before fingerprint unlock is
        turned on). Returns the data key. A wrong password counts like any other wrong try."""
        document, key, attempts = self._open_key_file()
        try:
            same = secrets.compare_digest(key_id(unwrap_key(document, password)), key_id(key))
        except ValueError as exc:
            attempts.failed()
            raise ProfileError("The password is incorrect.") from exc
        if not same:
            raise ProfileError("The password is incorrect.")
        attempts.succeeded()
        return key

    def change_question(self, recovery: str, question: str, answer: str) -> None:
        """New security question: the open profile plus the recovery key (the old answer may be forgotten)."""
        document, key, attempts = self._open_key_file()
        self._prove(document, key, attempts, recovery, "recovery")
        try:
            updated = with_question(document, key, recovery, question, answer)
        except ValueError as exc:
            raise _readable(exc) from exc
        publish_keys(self.paths, updated)

    def prepare_recovery_key(self, answer: str) -> PendingRecoveryKey:
        """A new recovery key: the open profile plus the answer. It replaces the old one only once typed back."""
        document, key, attempts = self._open_key_file()
        self._prove(document, key, attempts, answer, "answer")
        recovery = new_recovery_key()
        self.pending_recovery = PendingRecoveryKey(recovery, document, with_recovery_key(document, key, answer, recovery),
                                                   time.monotonic() + 900)
        return self.pending_recovery

    def confirm_recovery_key(self, typed_recovery: str) -> None:
        pending = self.pending_recovery
        if self.paths is None or pending is None or time.monotonic() >= pending.expires:
            self.pending_recovery = None
            raise ProfileError("This new recovery key expired. Ask for a new one.")
        try:
            typed = normalize_recovery_key(typed_recovery)
        except ValueError:
            typed = ""
        if not secrets.compare_digest(typed, normalize_recovery_key(pending.recovery)):
            raise ProfileError("That is not the recovery key shown. Check what you wrote down and type it again.")
        if read_keys(self.paths) != pending.base:
            self.pending_recovery = None
            raise ProfileError("The profile's keys changed meanwhile. Ask for a new recovery key.")
        publish_keys(self.paths, pending.key_file)
        self.pending_recovery = None

    def set_mode(self, mode: str) -> None:
        """For sync (multiple devices): "home" writable, "reader" read-only, "closed" no connection at all
        while keeping the profile's lock and key, so it can reopen without a password. The caller holds the
        request gate, so no request is in flight."""
        if self.paths is None or self.sync_key is None:
            return  # the profile is locked: nothing is open to change
        key = self.sync_key
        if self.container is not None:
            self.container.db.close()
            self.container = None
        if mode == "closed":
            return
        role = SessionRole.HOME if mode == "home" else SessionRole.READER
        try:
            container = build(self.paths.db_path, key=key, read_only=not role.writable)
        except BaseException:
            self.close()
            raise
        label, borrowed = self.label, self.borrowed
        self._activate(self.paths, self.lock, container, role)
        self.label, self.borrowed = label, borrowed

    def open_borrowed(self, node, key: bytes, *, name: str, writable: bool) -> None:
        """Open a borrowed profile's working copy on this PC: writable only under a permit (BORROWING)."""
        self._locked()
        paths = node.paths
        if writable and not node.writable:
            raise ProfileError("This PC does not hold the ledger now.")
        profile_paths = ProfilePaths(None, paths.data_dir, paths.working_path, paths.keys_path,
                                     paths.data_dir / "backups", paths.lock_path)
        profile_paths.backups_dir.mkdir(mode=0o700, exist_ok=True)
        lock = self._acquire(profile_paths)
        try:
            role = SessionRole.BORROWER if writable else SessionRole.READER
            container = build(paths.working_path, key=key, backup_dir=profile_paths.backups_dir,
                              read_only=not writable)
            self._activate(profile_paths, lock, container, role)
            self.label, self.borrowed = name, node
        except BaseException:
            lock.close()
            raise

    def close(self) -> None:
        # Do not release the OS lock if closing the database fails.
        if self.journal is not None:
            self.journal.close()
            self.journal = None
        if self.container is not None:
            self.container.db.close()
        self.container = None
        self.role = SessionRole.HOME
        self.sync_key = None
        self.label = ""
        self.borrowed = None
        self.paths = None
        if self.lock is not None:
            self.lock.close()
            self.lock = None
        self.pending = None
        self.pending_recovery = None
        self.token = secrets.token_urlsafe(32)
        self.csrf = secrets.token_urlsafe(32)
