"""Dummy data only: check native dependencies in an arm64 Android process, one line per check, so a
failure names the module and its error instead of stopping at the first one. Then (04b) run the shared
encrypted round-trip on the committed fixture and compare it line by line with what Windows and Linux give.

04c: render the finance pages in-process, then `serve()` runs the shared loopback runtime (`Host` and
`profile_app`, as on Windows) on a fresh copy of the dummy profile for the WebView, and `stop()` shuts it down on
its owning thread and reports what was checked."""

import importlib
import os
import pkgutil
import shutil
import struct
import tempfile
import time
from pathlib import Path

FIXTURE_FILES = ("profile.db", "keys.json", "recovery.txt", "expected.json")
_host = None
_paths = None
_served = []  # lines measured while serving, reported by stop()


def _check(name, test):
    try:
        return f"OK  {name}: {test()}"
    except BaseException as error:  # noqa: BLE001 - every failure is reported, never raised
        return f"FAIL {name}: {type(error).__name__}: {error}"


def _sqlcipher():
    from sqlcipher3 import dbapi2
    conn = dbapi2.connect(":memory:")
    try:
        version = conn.execute("PRAGMA cipher_version").fetchone()
    finally:
        conn.close()
    if not version or not version[0]:
        raise RuntimeError("SQLCipher is unavailable")
    return "SQLCipher " + version[0]


def _argon2():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
    Argon2id(salt=b"0" * 16, length=32, iterations=1, lanes=1, memory_cost=8).derive(b"probe")
    AESGCM(AESGCM.generate_key(bit_length=256))
    return "Argon2id and AES-GCM work"


def _extract(folder):
    for name in FIXTURE_FILES:
        (Path(folder) / name).write_bytes(pkgutil.get_data("roundtrip_fixture", name))


def _pages():
    """Every finance page and the app files they link, rendered on the owning thread with no server."""
    from lightning.bootstrap import build
    from lightning.runtime.roundtrip import AS_OF, PASSWORD
    from lightning.runtime.selfcheck import finance_page_checks
    from lightning.security.keys import unwrap_key
    import json

    with tempfile.TemporaryDirectory(prefix="pages-") as folder:
        _extract(folder)
        key = unwrap_key(json.loads((Path(folder) / "keys.json").read_text(encoding="utf-8")), PASSWORD)
        container = build(Path(folder) / "profile.db", key=key, backup_dir=Path(folder) / "backups")
        try:
            started = time.perf_counter()
            checks = finance_page_checks(container)
            seconds = time.perf_counter() - started
        finally:
            container.db.close()
    failed = sorted(name for name, ok in checks.items() if not ok)
    if failed:
        raise AssertionError("not rendered: " + ", ".join(failed))
    pages = sum(name.startswith("page ") for name in checks)
    return f"{pages} pages and {len(checks) - pages - 1} app files in {seconds:.2f} s (fixture dated {AS_OF})"


def _native_files():
    """Every shared library this process mapped from the app's own files (not the system's)."""
    try:
        with open("/proc/self/maps", encoding="utf-8", errors="replace") as maps:
            mapped = {line.split(None, 5)[5].strip() for line in maps if len(line.split(None, 5)) == 6}
    except OSError:
        mapped = set()
    import sys
    mapped |= {getattr(m, "__file__", "") or "" for m in list(sys.modules.values())}
    system = ("/system/", "/apex/", "/vendor/", "/product/", "/odm/", "/data/dalvik-cache/")
    return sorted(path for path in mapped if ".so" in Path(path).name and not path.startswith(system)
                  and os.path.isfile(path))


def _load_alignment(path):
    """The smallest PT_LOAD alignment of a 64-bit little-endian ELF file."""
    with open(path, "rb") as elf:
        head = elf.read(64)
        if head[:4] != b"\x7fELF" or head[4] != 2:
            return None
        phoff, = struct.unpack_from("<Q", head, 0x20)
        size, count = struct.unpack_from("<HH", head, 0x36)
        elf.seek(phoff)
        table = elf.read(size * count)
    aligns = [struct.unpack_from("<Q", table, i * size + 0x30)[0] for i in range(count)
              if struct.unpack_from("<I", table, i * size)[0] == 1]
    return min(aligns) if aligns else None


def _sixteen_kb():
    """Page size of this phone, and which loaded app libraries could not load on a 16 KB-page phone."""
    files = _native_files()
    short = [Path(f).name for f in files if (_load_alignment(f) or 0) < 16384]
    page = os.sysconf("SC_PAGESIZE")
    summary = f"page size {page // 1024} KB; {len(files)} app libraries loaded, {len(files) - len(short)} 16 KB-aligned"
    if short:
        raise AssertionError(summary + "; not aligned: " + ", ".join(sorted(short)))
    return summary


def _guards(origin):
    """The loopback server refuses what another app on the phone could send it."""
    import http.client

    def status(method, path, headers):
        connection = http.client.HTTPConnection(origin.removeprefix("http://"), timeout=5)
        try:
            connection.request(method, path, headers=headers)
            return connection.getresponse().status
        finally:
            connection.close()

    host = origin.removeprefix("http://")
    results = {"no session cookie": status("GET", "/", {"Host": host}) == 403,
               "foreign Host header": status("GET", "/", {"Host": "evil.example"}) == 400,
               "foreign Origin": status("POST", "/profiles/unlock", {"Host": host, "Origin": "https://evil.example"}) == 403,
               "wrong launch code": status("GET", "/__launch?code=wrong", {"Host": host}) == 403}
    failed = [name for name, ok in results.items() if not ok]
    if failed:
        raise AssertionError("accepted: " + ", ".join(failed))
    return "refused " + ", ".join(results)


def serve(files_dir):
    """Start the shared runtime on a fresh copy of the dummy profile. Returns the single-use launch URL."""
    global _host, _paths
    from lightning_android import configure_device_credentials
    configure_device_credentials()
    from lightning.runtime.app import profile_app
    from lightning.runtime.http import Host
    from lightning.runtime.paths import create_profile

    stop_quietly()
    root = Path(files_dir) / "probe-profiles"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    paths = create_profile("Dummy", root=root)
    paths.prepare()
    with tempfile.TemporaryDirectory(prefix="fixture-") as folder:
        _extract(folder)
        shutil.copyfile(Path(folder) / "profile.db", paths.db_path)
        shutil.copyfile(Path(folder) / "keys.json", paths.keys_path)
    started = time.perf_counter()
    _host, _paths = Host(lambda credentials: profile_app(credentials, root)).start(), paths
    _served[:] = [f"OK  04c server: started in {time.perf_counter() - started:.2f} s on {_host.origin}"]
    _served.append(_check("04c server guards", lambda: _guards(_host.origin)))
    return _host.launch_url


def stop_quietly():
    global _host
    if _host is not None:
        try:
            _host.stop()
        finally:
            _host = None


def stop():
    """Stop the server; its owning thread closes the profile. Report the shutdown and everything measured."""
    global _host
    from lightning.runtime.instance import InstanceLock

    def shutdown():
        global _host
        if _host is None:
            raise RuntimeError("the server was not running")
        host, session = _host, _host.app.session
        unlocked = any(_paths.backups_dir.iterdir())  # unlocking as home takes a backup first
        started = time.perf_counter()
        host.stop()
        _host = None
        if host.thread.is_alive() or session.container is not None or session.lock is not None:
            raise AssertionError("the profile stayed open after the server stopped")
        InstanceLock(_paths.lock_path).acquire().close()  # released, so another session could open it
        return (f"stopped in {time.perf_counter() - started:.2f} s; profile closed on its own thread, lock released"
                + ("" if unlocked else "; the profile was never unlocked"))

    return "\n".join(_served + [_check("04c shutdown", shutdown), _check("04c 16 KB pages", _sixteen_kb)])


def _roundtrip():
    """The report lines and timings; every line that differs from expected.json is listed."""
    from lightning.runtime.roundtrip import DB_NAME, EXPECTED_NAME, KEYS_NAME, RECOVERY_NAME, fingerprint, run
    import json

    with tempfile.TemporaryDirectory(prefix="fixture-") as folder:
        _extract(folder)
        lines, seconds = run(folder)
        wanted = json.loads((Path(folder) / EXPECTED_NAME).read_text(encoding="utf-8"))
    if lines != wanted["lines"]:
        wrong = [f"  got {got!r}, expected {want!r}" for got, want in zip(lines, wanted["lines"]) if got != want]
        if len(lines) != len(wanted["lines"]):
            wrong.append(f"  {len(lines)} lines, expected {len(wanted['lines'])}")
        raise AssertionError("differs from Windows/Linux:\n" + "\n".join(wrong))
    timings = ", ".join(f"{name} {value:.2f} s" for name, value in seconds.items())
    return f"same figures, inventory and key recovery as Windows/Linux (fingerprint {fingerprint(lines)}); {timings}"


def pairing_credentials():
    """Debug-only dummy credential check, exposed by an internal native activity."""
    import json
    from lightning_android import configure_device_credentials
    if not configure_device_credentials():
        raise RuntimeError("Android credential adapter is unavailable")
    from lightning.runtime.pairing_probe import credential_checks
    return json.dumps(credential_checks(require_native=True), sort_keys=True)


def run():
    try:
        return _run()
    except BaseException:  # noqa: BLE001 - show the whole traceback on the phone, never just its type
        import traceback
        return "Probe stopped:\n" + traceback.format_exc()


def _run():
    lines = [_check(name, lambda name=name: getattr(importlib.import_module(name), "__version__", "loaded"))
             for name in ("_cffi_backend", "cryptography", "pydantic_core", "fastapi", "jinja2", "uvicorn")]
    lines += [_check("encryption", _argon2), _check("sqlcipher3", _sqlcipher)]
    lines += [_check("04b encrypted round-trip", _roundtrip), _check("04c pages render", _pages)]
    return "\n".join(lines)
