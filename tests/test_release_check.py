"""A prepared release has its notes in ai/changelog/<version>.md, with nothing left waiting in UNRELEASED.md."""
from tools import release_check


def test_prepared_release_notes_must_match_source_version(tmp_path, monkeypatch):
    monkeypatch.setattr(release_check, "ROOT", tmp_path)
    for name in ("LICENSE", "CONTRIBUTING.md"):
        (tmp_path / name).write_text("present")
    (tmp_path / "pyproject.toml").write_text('version = "1.5.0"\n')
    folder = tmp_path / "ai" / "changelog"
    folder.mkdir(parents=True)
    notes = folder / "1.5.0.md"
    notes.write_text("# 1.5.0 · 2026-10-26\n\n## Notes\n\n- feel: Prepared release.\n\n## Detail\n\n- x\n")
    assert release_check.files() == []
    notes.rename(folder / "1.4.4.md")
    assert release_check.files(), "Notes for an older release must not validate this release"
    (folder / "1.4.4.md").rename(notes)
    notes.write_text("# 1.5.0 · 2026-10-26\n\n## Notes\n\n## Detail\n\n- x\n")
    assert release_check.files(), "A version file without notes is insufficient"
    notes.write_text("# 1.5.0 · 2026-10-26\n\n## Notes\n\n- feel: Prepared release.\n\n## Detail\n\n- x\n")
    (folder / "UNRELEASED.md").write_text("waiting")
    assert release_check.files(), "Entries left in UNRELEASED.md must be cut into the release first"


def _zip(path, files):
    import io
    import zipfile
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            if isinstance(data, dict):
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w") as inner:
                    for inner_name, inner_data in data.items():
                        inner.writestr(inner_name, inner_data)
                data = buffer.getvalue()
            archive.writestr(name, data)
    return path


def _manifest(*permissions):
    return "".join(f"\x00{name}" for name in permissions).encode("utf-16-le")


def test_published_archives_hold_nothing_private(tmp_path):
    from pathlib import Path
    wanted = [line.split()[0] for line in (Path(release_check.ROOT) / "packaging" / "android-permissions.txt")
              .read_text(encoding="utf-8").splitlines() if line.startswith("android.permission.")]
    clean = {"Lightning/_internal/lightning/security/update_keys.json": "{}", "Lightning/README.txt":
             "Profiles stay under Documents/Lightning.", "certifi/cacert.pem": "-----BEGIN CERTIFICATE-----"}
    assert release_check.artifact(_zip(tmp_path / "ok.zip", clean)) == []
    app = {"roundtrip_fixture/profile.db": "dummy", "roundtrip_fixture/keys.json": "{}",
           "roundtrip_fixture/recovery.txt": "dummy", "probe.py": 'b"BEGIN ENCRYPTED PRIVATE KEY" in key'}
    apk = {"AndroidManifest.xml": _manifest(*wanted, "android.permission.BIND_JOB_SERVICE"), "assets/chaquopy/app.imy": app}
    assert release_check.artifact(_zip(tmp_path / "ok.apk", apk)) == []

    for name, data in {"Lightning/.git/config": "x", "Lightning/tests/test_x.py": "x", "Lightning/me.sqlite": "x",
                       "Lightning/recovery.txt": "x", "Lightning/.env": "x", "Lightning/signing.jks": "x",
                       "Lightning/server.pem": "x", "Documents/Lightning/profiles/a.db": "x",
                       "Lightning/notes.txt": "token ghp_" + "a" * 36,
                       "Lightning/k.txt": "-----BEGIN PRIVATE KEY-----\n" + "A" * 64}.items():
        assert release_check.artifact(_zip(tmp_path / "bad.zip", {name: data})), name
    hidden = {"AndroidManifest.xml": _manifest(*wanted), "assets/chaquopy/app.imy": {"lightning/profile.db": "x"}}
    assert release_check.artifact(_zip(tmp_path / "bad.apk", hidden)), "an .imy archive inside the APK is inspected"
    extra = {"AndroidManifest.xml": _manifest(*wanted, "android.permission.READ_CONTACTS")}
    assert any("READ_CONTACTS" in line for line in release_check.artifact(_zip(tmp_path / "extra.apk", extra)))
    fewer = {"AndroidManifest.xml": _manifest(*wanted[1:])}
    assert any("lacks" in line for line in release_check.artifact(_zip(tmp_path / "fewer.apk", fewer)))
