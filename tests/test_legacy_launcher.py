"""OW-2AB: the old entry point cannot open real plaintext data."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from lightning.database.connection import Database
from lightning.main import main


@pytest.mark.parametrize("mode,explicit_db", [(None, False), (None, True), ("--demo", True),
                                            ("--sample", True), ("--profiles", True)])
def test_unsafe_launches_stop_before_database_or_network_work(tmp_path, monkeypatch, mode, explicit_db):
    import lightning.bootstrap as bootstrap
    import lightning.main as launcher

    data = tmp_path / "data"
    data.mkdir()
    real = data / "lightning.db"
    real.write_bytes(b"existing legacy data must survive")
    monkeypatch.setattr(bootstrap, "DEFAULT_DATA_DIR", data)

    def unexpected(*args, **kwargs):
        pytest.fail("an invalid launch must not open a database or contact a server")

    monkeypatch.setattr(bootstrap, "build", unexpected)
    monkeypatch.setattr(launcher, "urlopen", unexpected)
    args = [mode] if mode else []
    if explicit_db:
        # Even explicitly passing the former default must not bypass the guard.
        args += ["--db", str(real)]
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
    assert list(data.iterdir()) == [real]
    assert real.read_bytes() == b"existing legacy data must survive"


def test_profile_launcher_keeps_the_encrypted_profile_path(tmp_path, monkeypatch):
    from lightning.runtime import launcher

    calls = []
    monkeypatch.setattr(launcher, "run_browser", lambda *args, **kwargs: calls.append((args, kwargs)))
    main(["--profiles", "--profile-root", str(tmp_path), "--no-browser"])
    assert calls == [((str(tmp_path),), {"open_browser": False})]


@pytest.mark.parametrize("mode,port", [("demo", 8766), ("sample", 8767)])
def test_samples_still_load_in_their_own_database(tmp_path, monkeypatch, mode, port):
    import lightning.bootstrap as bootstrap
    import lightning.main as launcher
    import uvicorn

    data = tmp_path / "data"
    data.mkdir()
    real = data / "lightning.db"
    real.write_bytes(b"untouched legacy database")
    monkeypatch.setattr(bootstrap, "DEFAULT_DATA_DIR", data)

    def unavailable(*args, **kwargs):
        raise OSError("no existing listener")

    monkeypatch.setattr(launcher, "urlopen", unavailable)
    monkeypatch.setattr(launcher.socket, "create_connection", unavailable)
    opened = []
    build = bootstrap.build

    def tracked_build(*args, **kwargs):
        container = build(*args, **kwargs)
        opened.append(container)
        return container

    monkeypatch.setattr(bootstrap, "build", tracked_build)
    served = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: served.append(kwargs))
    try:
        main([f"--{mode}", "--no-browser"])
        assert served == [{"host": "127.0.0.1", "port": port, "log_level": "warning"}]
        assert opened[0].db.path == str(data / f"{mode}.db")
        assert opened[0].accounts.list()
        assert real.read_bytes() == b"untouched legacy database"
    finally:
        for container in opened:
            container.db.close()


def test_plaintext_fixture_can_enforce_profile_thread_and_close_rules(strict_c):
    assert not strict_c.db.encrypted
    strict_c.settings.set("locale", "ar")
    with ThreadPoolExecutor(max_workers=1) as worker:
        for operation in (lambda: strict_c.settings.get("locale"), strict_c.db.close):
            with pytest.raises(RuntimeError, match="owning thread"):
                worker.submit(operation).result()
    assert strict_c.settings.get("locale") == "ar"
    strict_c.db.close()
    strict_c.db.close()  # session shutdown remains idempotent
    with pytest.raises(RuntimeError, match="closed"):
        strict_c.settings.get("locale")


def test_ordinary_plaintext_databases_keep_per_thread_connections(tmp_path):
    db = Database(tmp_path / "threaded.db")
    db.execute("CREATE TABLE example(value TEXT)")
    db.execute("INSERT INTO example VALUES('same data')")

    def read_and_close():
        try:
            return db.scalar("SELECT value FROM example")
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=1) as worker:
            assert worker.submit(read_and_close).result() == "same data"
        assert db.scalar("SELECT value FROM example") == "same data"
    finally:
        db.close()
