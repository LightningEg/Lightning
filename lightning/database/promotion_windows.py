"""Windows file-operation adapter for the promotion journal.

Windows does not expose the POSIX parent-directory fsync contract used by the
POSIX adapter. This adapter flushes file handles with FlushFileBuffers and uses
MoveFileExW with MOVEFILE_WRITE_THROUGH for sibling moves/replacements. The
documented write-through guarantee covers the move operation (and explicitly
flushes copy/delete moves); it is not a promise against every power loss, storage
controller cache, filesystem bug, or device failure. Recovery must still inspect
the journal and hashes after restart. ReplaceFileW's WRITE_THROUGH flag is
documented as unsupported, so it is deliberately not used.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import stat
import uuid
from ctypes import wintypes
from pathlib import Path

FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_READ_ATTRIBUTES = 0x0080
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
CREATE_NEW = 1
OPEN_EXISTING = 3
MOVEFILE_REPLACE_EXISTING = 0x1
MOVEFILE_WRITE_THROUGH = 0x8

_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def move_write_through(source: str | Path, destination: str | Path) -> None:
    """Move one file on the same volume, never over another, returning only once the move is on disk.

    IT-2A2: restore's moves and discards outside the promotion adapter use this, so their order
    survives a power cut as far as MOVEFILE_WRITE_THROUGH promises (see the module docstring)."""
    if os.name != "nt":
        raise OSError("move_write_through is available only on Windows")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.MoveFileExW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
    kernel.MoveFileExW.restype = wintypes.BOOL
    if not kernel.MoveFileExW(WindowsPromotionFileOps._extended(Path(os.path.abspath(source))),
                              WindowsPromotionFileOps._extended(Path(os.path.abspath(destination))),
                              MOVEFILE_WRITE_THROUGH):
        error = ctypes.WinError(ctypes.get_last_error())
        error.strerror = f"Move restore file: {error.strerror}"
        raise error


class _FileTime(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]


class _ByHandleFileInformation(ctypes.Structure):
    _fields_ = [
        ("attributes", wintypes.DWORD),
        ("creation_time", _FileTime),
        ("last_access_time", _FileTime),
        ("last_write_time", _FileTime),
        ("volume_serial", wintypes.DWORD),
        ("file_size_high", wintypes.DWORD),
        ("file_size_low", wintypes.DWORD),
        ("links", wintypes.DWORD),
        ("file_index_high", wintypes.DWORD),
        ("file_index_low", wintypes.DWORD),
    ]


class WindowsPromotionFileOps:
    """No-follow, same-volume operations below one pinned local directory.

    Construct only on Windows. The root handle denies delete sharing so the
    directory cannot be renamed/replaced while the adapter is active. Reparse
    points, hard-linked files and non-regular file handles fail closed.
    """

    def __init__(self, directory: str | Path):
        if os.name != "nt":
            raise OSError("WindowsPromotionFileOps is available only on Windows")
        self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure_api()
        path = Path(os.path.abspath(directory))
        if not path.drive or str(path).startswith("\\\\"):
            raise ValueError("Promotion directory must be on a local Windows drive")
        self._validate_path_components(path)
        if self._kernel.GetDriveTypeW(str(path.anchor)) != 3:  # DRIVE_FIXED
            raise ValueError("Promotion directory must be on a fixed local drive")
        if not path.is_dir():
            raise ValueError("Promotion root must be an existing directory")
        self._directory = path
        self._root_handle = self._open_directory(path)
        self._root_identity = self._identity(self._file_info(self._root_handle))
        self._closed = False
        self._ensure_open()

    def _configure_api(self) -> None:
        self._kernel.CreateFileW.argtypes = (
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        )
        self._kernel.CreateFileW.restype = wintypes.HANDLE
        self._kernel.GetFileInformationByHandle.argtypes = (
            wintypes.HANDLE, ctypes.POINTER(_ByHandleFileInformation),
        )
        self._kernel.GetFileInformationByHandle.restype = wintypes.BOOL
        self._kernel.FlushFileBuffers.argtypes = (wintypes.HANDLE,)
        self._kernel.FlushFileBuffers.restype = wintypes.BOOL
        self._kernel.MoveFileExW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
        self._kernel.MoveFileExW.restype = wintypes.BOOL
        self._kernel.GetDriveTypeW.argtypes = (wintypes.LPCWSTR,)
        self._kernel.GetDriveTypeW.restype = wintypes.UINT
        self._kernel.DeleteFileW.argtypes = (wintypes.LPCWSTR,)
        self._kernel.DeleteFileW.restype = wintypes.BOOL
        self._kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        self._kernel.CloseHandle.restype = wintypes.BOOL

    @staticmethod
    def validate_name(name: str) -> str:
        if (not isinstance(name, str) or not name or len(name) > 240
                or name in {".", ".."} or any(char in name for char in '/\\:*?"<>|')
                or any(ord(char) < 32 for char in name) or name.endswith((" ", "."))):
            raise ValueError("Promotion paths must be safe Windows sibling file names")
        base = name.split(".", 1)[0].rstrip(" .").upper()
        if base in _WINDOWS_RESERVED_NAMES:
            raise ValueError("Reserved Windows device names are not allowed")
        return name

    @classmethod
    def _validate_path_components(cls, path: Path) -> None:
        current = Path(path.anchor)
        for part in path.parts[1:]:
            current = current / part
            try:
                info = os.lstat(current)
            except FileNotFoundError:
                # Missing components will be caught by the full root check;
                # never walk through a later component after a missing parent.
                raise ValueError("Promotion directory path must already exist")
            attrs = getattr(info, "st_file_attributes", 0)
            if attrs & FILE_ATTRIBUTE_REPARSE_POINT or stat.S_ISLNK(info.st_mode):
                raise ValueError("Promotion directory path must not contain reparse points")

    @staticmethod
    def _extended(path: Path) -> str:
        value = str(path)
        return value if value.startswith("\\\\?\\") else "\\\\?\\" + value

    def _path(self, name: str) -> Path:
        return self._directory / self.validate_name(name)

    def _raise_last_error(self, operation: str) -> OSError:
        error = ctypes.WinError(ctypes.get_last_error())
        error.strerror = f"{operation}: {error.strerror}"
        return error

    def _open_directory(self, path: Path):
        handle = self._kernel.CreateFileW(
            self._extended(path), FILE_READ_ATTRIBUTES,
            FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, None,
        )
        if handle == _INVALID_HANDLE_VALUE:
            raise self._raise_last_error("Open promotion directory")
        try:
            info = self._file_info(handle)
            if not info.attributes & FILE_ATTRIBUTE_DIRECTORY:
                raise ValueError("Promotion root is not a directory")
            if info.attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError("Promotion root must not be a reparse point")
            return handle
        except BaseException:
            self._kernel.CloseHandle(handle)
            raise

    def _file_info(self, handle) -> _ByHandleFileInformation:
        info = _ByHandleFileInformation()
        if not self._kernel.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise self._raise_last_error("Inspect promotion file")
        return info

    @staticmethod
    def _identity(info: _ByHandleFileInformation) -> tuple[int, int, int]:
        index = (info.file_index_high << 32) | info.file_index_low
        return info.volume_serial, index, info.links

    @staticmethod
    def _stability(info: _ByHandleFileInformation) -> tuple[int, int, int, int, int]:
        size = (info.file_size_high << 32) | info.file_size_low
        write_time = (info.last_write_time.high << 32) | info.last_write_time.low
        return (*WindowsPromotionFileOps._identity(info), size, write_time)

    def _check_regular(self, info: _ByHandleFileInformation, name: str) -> None:
        if info.attributes & FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f"Reparse-point promotion file rejected: {name}")
        if info.attributes & FILE_ATTRIBUTE_DIRECTORY:
            raise ValueError(f"Promotion path is not a regular file: {name}")
        if info.links != 1:
            raise ValueError(f"Hard-linked promotion file rejected: {name}")

    def _open(self, path: Path, access: int, share: int, disposition: int):
        handle = self._kernel.CreateFileW(
            self._extended(path), access, share, None, disposition,
            FILE_FLAG_OPEN_REPARSE_POINT, None,
        )
        if handle == _INVALID_HANDLE_VALUE:
            error = ctypes.get_last_error()
            if error in (2, 3):  # ERROR_FILE_NOT_FOUND / ERROR_PATH_NOT_FOUND
                raise FileNotFoundError(error, "Promotion file not found", str(path))
            raise self._raise_last_error("Open promotion file")
        try:
            self._ensure_open()
            info = self._file_info(handle)
            self._check_regular(info, path.name)
            return handle, info
        except BaseException:
            self._kernel.CloseHandle(handle)
            raise

    @staticmethod
    def _fd_from_handle(handle, flags: int) -> int:
        import msvcrt

        return msvcrt.open_osfhandle(int(handle), flags | os.O_BINARY)

    @staticmethod
    def _handle_from_fd(fd: int):
        import msvcrt

        return wintypes.HANDLE(msvcrt.get_osfhandle(fd))

    def _flush_file(self, handle) -> None:
        if not self._kernel.FlushFileBuffers(handle):
            raise self._raise_last_error("Flush promotion file")

    def _move_file(self, source: Path, destination: Path, flags: int) -> None:
        if not self._kernel.MoveFileExW(self._extended(source), self._extended(destination), flags):
            raise self._raise_last_error("Move promotion file")

    def _ensure_open(self) -> None:
        if getattr(self, "_closed", False):
            raise RuntimeError("Promotion file adapter is closed")
        current = self._open_directory(self._directory)
        try:
            if self._identity(self._file_info(current)) != self._root_identity:
                raise OSError("Promotion root path changed after adapter construction")
        finally:
            self._kernel.CloseHandle(current)

    def close(self) -> None:
        if not getattr(self, "_closed", True):
            self._kernel.CloseHandle(self._root_handle)
            self._closed = True

    def __enter__(self) -> WindowsPromotionFileOps:
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def sha256(self, name: str) -> str | None:
        path = self._path(name)
        self._ensure_open()
        try:
            handle, before = self._open(path, GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING)
        except FileNotFoundError:
            return None
        try:
            fd = self._fd_from_handle(handle, os.O_RDONLY)
        except BaseException:
            self._kernel.CloseHandle(handle)
            raise
        digest = hashlib.sha256()
        try:
            while True:
                block = os.read(fd, 1024 * 1024)
                if not block:
                    break
                digest.update(block)
            after = self._file_info(self._handle_from_fd(fd))
            if self._stability(before) != self._stability(after):
                raise OSError("Promotion file changed while hashing")
            return digest.hexdigest()
        finally:
            os.close(fd)

    def copy_exclusive(self, source: str, destination: str) -> None:
        source_path = self._path(source)
        destination_path = self._path(destination)
        if source_path == destination_path:
            raise ValueError("Copy source and destination must differ")
        self._ensure_open()
        source_handle, source_before = self._open(source_path, GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING)
        source_fd = self._fd_from_handle(source_handle, os.O_RDONLY)
        temporary = self._path(f".lp-{uuid.uuid4().hex}.partial")
        target_handle = None
        target_fd = None
        temporary_created = False
        copied_digest = hashlib.sha256()
        try:
            target_handle, _ = self._open(
                temporary, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ,
                CREATE_NEW,
            )
            temporary_created = True
            target_fd = self._fd_from_handle(target_handle, os.O_RDWR)
            while True:
                block = os.read(source_fd, 1024 * 1024)
                if not block:
                    break
                view = memoryview(block)
                while view:
                    written = os.write(target_fd, view)
                    if written <= 0:
                        raise OSError("Short write while copying promotion file")
                    view = view[written:]
                copied_digest.update(block)
            self._flush_file(self._handle_from_fd(target_fd))
            source_after = self._file_info(self._handle_from_fd(source_fd))
            if self._stability(source_before) != self._stability(source_after):
                raise OSError("Promotion source changed while copying")
            os.close(target_fd)
            target_fd = None
            target_handle = None  # CRT fd closed its owned handle.
            self._move_file(temporary, destination_path, MOVEFILE_WRITE_THROUGH)
            published_digest = self.sha256(destination)
            if published_digest != copied_digest.hexdigest():
                raise OSError("Exclusive copied file failed post-publication hash verification")
        except BaseException:
            if target_fd is not None:
                os.close(target_fd)
                target_fd = None
                target_handle = None
            elif target_handle is not None:
                self._kernel.CloseHandle(target_handle)
                target_handle = None
            # Best-effort cleanup applies only to our random exclusive partial.
            try:
                if temporary_created and os.path.lexists(temporary):
                    self._kernel.DeleteFileW(self._extended(temporary))
            except OSError:
                pass
            raise
        finally:
            os.close(source_fd)

    def atomic_replace(self, source: str, destination: str) -> None:
        source_path = self._path(source)
        destination_path = self._path(destination)
        if source_path == destination_path:
            raise ValueError("Replace source and destination must differ")
        self._ensure_open()
        expected_hash = self.sha256(source)
        if expected_hash is None:
            raise FileNotFoundError(f"Promotion candidate is missing: {source}")
        read_handle, read_info = self._open(
            source_path, GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING,
        )
        try:
            if self.sha256(source) != expected_hash:
                raise OSError("Promotion candidate changed before replacement")
        finally:
            self._kernel.CloseHandle(read_handle)
        source_handle, source_info = self._open(
            source_path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ, OPEN_EXISTING,
        )
        destination_handle = None
        try:
            if self._identity(read_info) != self._identity(source_info):
                raise OSError("Promotion candidate identity changed before replacement")
            destination_handle, destination_info = self._open(
                destination_path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                OPEN_EXISTING,
            )
            source_fd = self._fd_from_handle(source_handle, os.O_RDONLY)
            source_handle = None
            try:
                self._flush_file(self._handle_from_fd(source_fd))
            finally:
                os.close(source_fd)
            # Reopen both names without following reparse points immediately
            # before the path-based rename, and ensure they are still the
            # regular, single-link files whose handles were inspected.
            source_check, source_now = self._open(
                source_path, GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING,
            )
            try:
                if self._identity(source_info) != self._identity(source_now):
                    raise OSError("Promotion candidate changed before replacement")
            finally:
                self._kernel.CloseHandle(source_check)
            destination_check, destination_now = self._open(
                destination_path, GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, OPEN_EXISTING,
            )
            try:
                if self._identity(destination_info) != self._identity(destination_now):
                    raise OSError("Live promotion target changed before replacement")
            finally:
                self._kernel.CloseHandle(destination_check)
            self._kernel.CloseHandle(destination_handle)
            destination_handle = None
            # Same-directory paths prohibit cross-volume copy. WRITE_THROUGH is
            # requested; Windows does not provide a POSIX directory-fsync API.
            self._move_file(
                source_path, destination_path,
                MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
            )
            handle, _ = self._open(
                destination_path, GENERIC_READ | GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, OPEN_EXISTING,
            )
            try:
                self._flush_file(handle)
            finally:
                self._kernel.CloseHandle(handle)
            if self.sha256(destination) != expected_hash:
                raise OSError("Published promotion file failed hash verification")
        finally:
            if source_handle is not None:
                self._kernel.CloseHandle(source_handle)
            if destination_handle is not None:
                self._kernel.CloseHandle(destination_handle)

    def unlink(self, name: str) -> None:
        path = self._path(name)
        self._ensure_open()
        handle, _ = self._open(
            path, FILE_READ_ATTRIBUTES, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            OPEN_EXISTING,
        )
        self._kernel.CloseHandle(handle)
        # Cleanup only; DeleteFileW has no documented parent-directory flush.
        # It is called only after control state says this file is unreferenced.
        if not self._kernel.DeleteFileW(self._extended(path)):
            raise self._raise_last_error("Delete unreferenced promotion file")
