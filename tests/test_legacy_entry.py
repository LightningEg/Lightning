"""OW-2AB: starting the CLI never opens a plaintext real-data database."""
import pytest
from concurrent.futures import ThreadPoolExecutor
from lightning.main import main
from lightning.database.connection import Database


def test_default_entry_uses_encrypted_profile_launcher(monkeypatch):
    calls = []
    monkeypatch.setattr("lightning.runtime.launcher.run_browser", lambda root, **kw: calls.append((root, kw)))
    monkeypatch.setattr("lightning.bootstrap.build", lambda *a, **kw: pytest.fail("plaintext database opened"))
    main(["--no-browser"])
    assert calls == [(None, {"open_browser": False})]


def test_explicit_plaintext_real_database_is_refused_before_open(monkeypatch, tmp_path):
    path = tmp_path / "private.db"
    monkeypatch.setattr("lightning.bootstrap.build", lambda *a, **kw: pytest.fail("plaintext database opened"))
    with pytest.raises(SystemExit) as error:
        main(["--db", str(path), "--no-browser"])
    assert error.value.code == 2
    assert not path.exists()


def test_plaintext_fixture_can_enforce_owning_thread(tmp_path):
    db = Database(tmp_path / "fixture.db", strict_thread=True)
    assert db.scalar("SELECT 1") == 1
    with ThreadPoolExecutor(1) as pool:
        with pytest.raises(RuntimeError, match="owning thread"):
            pool.submit(db.scalar, "SELECT 1").result()
    assert db.scalar("SELECT 2") == 2
    db.close()


def test_source_installer_uses_declared_encrypted_extras(monkeypatch):
    import importlib.util
    import tomllib
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("install_source", root / "tools/install_source.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    commands = []
    monkeypatch.setattr(installer.subprocess, "check_call", lambda command: commands.append(command))
    installer.main()
    extras = tomllib.loads((root / "pyproject.toml").read_text())["project"]["optional-dependencies"]["encrypted"]
    assert commands[0][-len(extras):] == extras
    assert str(root / "requirements.txt") in commands[0]
