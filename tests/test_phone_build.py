"""The matched PC and phone test builds (docs/ARCHITECTURE.md › Build and release): the scripts that pin, check,
sign and bundle the phone app. The workflow runs them on real builds; these tests run them on fakes."""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(relative: str):
    spec = importlib.util.spec_from_file_location(Path(relative).stem + "_under_test", ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load("packaging/phone_build.py")
lock = _load("tools/android_lock.py")


def _archive(names: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as inner:
        for name in names:
            inner.writestr(name, b"" if name.endswith("/") else b"x")
    return buffer.getvalue()


def _locked() -> dict[str, str]:
    return build.locked_packages((ROOT / "requirements" / "android.lock").read_text(encoding="utf-8"))


def _app_entries() -> list[str]:
    return [entry if entry.endswith("/") or "." in entry.rsplit("/", 1)[-1] else entry + "/x.py"
            for entry in build.REQUIRED]


def _apk(path: Path, *, extra_app: tuple[str, ...] = (), abis: tuple[str, ...] = ("arm64-v8a",),
         packages: dict[str, str] | None = None, app: list[str] | None = None) -> Path:
    packages = _locked() if packages is None else packages
    app = (_app_entries() if app is None else app) + list(extra_app)
    requirements = [f"{name.replace('-', '_')}-{version}.dist-info/METADATA" for name, version in packages.items()]
    with zipfile.ZipFile(path, "w") as apk:
        apk.writestr("AndroidManifest.xml", b"")
        for abi in abis:
            apk.writestr(f"lib/{abi}/libpython3.13.so", b"")
        apk.writestr("assets/chaquopy/app.imy", _archive(app))
        apk.writestr("assets/chaquopy/requirements-common.imy", _archive(requirements))
        apk.writestr("META-INF/MANIFEST.MF", b"")
    return path


def test_the_lock_pins_every_package_as_one_file_from_the_published_wheels():
    text = (ROOT / "requirements" / "android.lock").read_text(encoding="utf-8")
    tag = build.wheels_tag(text)
    entries = [line for line in text.splitlines() if " @ " in line]
    assert len(entries) == len(_locked()) and len(entries) == text.count("--hash=sha256:")
    for name in lock.NATIVE:
        assert f"https://github.com/{lock.REPOSITORY}/releases/download/{tag}/" in next(
            line for line in entries if line.startswith(name + " @ "))
    for line in entries:
        assert line.split(" @ ")[1].startswith(("https://files.pythonhosted.org/", "https://github.com/"))
    wanted = lock.pinned((ROOT / "requirements" / "android.in").read_text(encoding="utf-8"))
    assert all(_locked()[name] == version for name, version in wanted.items())  # the lock follows android.in
    gradle = (ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    assert 'options("--no-index")' in gradle and "requirements/android.lock" in gradle and "wheelDir" not in gradle


def test_wheels_are_chosen_for_cpython_313_on_arm64_android():
    assert lock.rank("markupsafe-3.0.4-cp313-cp313-android_24_arm64_v8a.whl") > lock.rank("x-1-py3-none-any.whl")
    assert lock.rank("cryptography-50.0.2-cp313-abi3-android_24_arm64_v8a.whl") == (1, 2)
    assert lock.rank("tzdata-2026.2-py2.py3-none-any.whl") == (0, 1)
    for wrong in ("m-1-cp313-cp313-android_24_x86_64.whl", "m-1-cp313-cp313-android_30_arm64_v8a.whl",
                  "m-1-cp314-cp314-android_24_arm64_v8a.whl", "m-1-cp313-cp313-manylinux_2_28_aarch64.whl"):
        assert lock.rank(wrong) is None, wrong
    sums = ("a" * 64 + "  cffi-2.0.0-cp313-cp313-android_24_arm64_v8a.whl\n"
            + "b" * 64 + "  cryptography-50.0.2-cp313-abi3-android_24_arm64_v8a.whl\n"
            + "c" * 64 + "  pydantic_core-2.46.5-cp313-cp313-android_24_arm64_v8a.whl\n")
    wanted = {"cffi": "2.0.0", "cryptography": "50.0.2", "pydantic-core": "2.46.5", "sqlcipher3": "0.6.2"}
    with pytest.raises(SystemExit, match="exactly"):
        lock.native_files("android-wheels-r1", sums, wanted)  # sqlcipher3 missing
    with pytest.raises(SystemExit, match="does not match"):
        lock.native_files("android-wheels-r1", sums.replace("50.0.2", "49.0.0"), wanted)


def test_a_test_build_has_its_own_id_and_a_version_that_never_falls():
    first = build.identity("a" * 40, 70, "0.5.0-beta.1")
    later = build.identity("b" * 40, 71, "0.5.0-beta.1")
    assert first == {"version_code": "70", "version_name": "0.5.0-beta.1-test.70+aaaaaaaa",
                     "apk": "Lightning-Test-0.5.0-beta.1-70-aaaaaaaa.apk", "stamp": "0.5.0-beta.1-70-aaaaaaaa"}
    assert int(later["version_code"]) > int(first["version_code"])
    with pytest.raises(build.BuildError):
        build.identity("a" * 40, 0, "1")
    gradle = (ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    assert '"org.lightning.app.test"' in gradle and '"Lightning Test"' in gradle
    manifest = (ROOT / "android" / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")
    assert 'android:label="${appLabel}"' in manifest
    allowed = {line.split("#")[0].strip() for line in build.PERMISSIONS.read_text().splitlines()} - {""}
    assert allowed == set(__import__("re").findall(r'uses-permission android:name="([^"]+)"', manifest))


def test_the_apk_must_carry_exactly_what_it_should(tmp_path):
    problems, packages = build.contents_problems(_apk(tmp_path / "good.apk"), _locked())
    assert problems == [] and packages == _locked()
    # Chaquopy ships top-level modules compiled; a same-named file elsewhere is not the module.
    compiled = [entry + "c" if entry in ("probe.py", "lightning_android.py") else entry for entry in _app_entries()]
    assert build.contents_problems(_apk(tmp_path / "pyc.apk", app=compiled), _locked())[0] == []
    elsewhere = [("lightning/desktop/" + e) if e == "probe.py" else e for e in _app_entries()]
    assert build.contents_problems(_apk(tmp_path / "far.apk", app=elsewhere), _locked())[0] == [
        "probe.py is not in the APK (found lightning/desktop/probe.py)"]

    private = build.contents_problems(_apk(tmp_path / "p.apk", extra_app=("lightning/profiles/real.db",
                                                                          "lightning/keys.json", "x/app.log")), _locked())[0]
    assert len(private) == 3 and all("private data" in problem for problem in private)
    assert any("x86_64" in p for p in build.contents_problems(_apk(tmp_path / "a.apk", abis=("arm64-v8a", "x86_64")), _locked())[0])
    drifted = dict(_locked(), starlette="0.1")
    assert any("differ from requirements/android.lock" in p for p in
               build.contents_problems(_apk(tmp_path / "d.apk", packages=drifted), _locked())[0])
    fewer = {k: v for k, v in _locked().items() if k != "anyio"}
    assert any("anyio" in p for p in build.contents_problems(_apk(tmp_path / "f.apk", packages=fewer), _locked())[0])


def test_aapt2_and_apksigner_reports_are_read_strictly():
    info = build.badging("package: name='org.lightning.app.test' versionCode='70' versionName='0.5.0-beta.1-test.70+aaaaaaaa' "
                         "platformBuildVersionName='15'\nsdkVersion:'24'\napplication-debuggable\nnative-code: 'arm64-v8a'\n")
    assert info == {"package": "org.lightning.app.test", "version_code": "70",
                    "version_name": "0.5.0-beta.1-test.70+aaaaaaaa", "debuggable": "yes"}
    asked = build.permissions("package: org.lightning.app.test\nuses-permission: name='android.permission.INTERNET'\n"
                              "uses-permission: name='org.lightning.app.test.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION'\n"
                              "permission: org.lightning.app.test.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION\n",
                              "org.lightning.app.test")
    assert asked == {"android.permission.INTERNET"}
    good = ("Verifies\nVerified using v1 scheme (JAR signing): false\n"
            "Verified using v2 scheme (APK Signature Scheme v2): true\nNumber of signers: 1\n"
            f"Signer #1 certificate SHA-256 digest: {'ab' * 32}\n")
    assert build.signers(good) == ["ab" * 32]
    with pytest.raises(build.BuildError, match="v2"):
        build.signers(good.replace(": true", ": false"))
    with pytest.raises(build.BuildError, match="does not verify"):
        build.signers("DOES NOT VERIFY\n")


def _windows(folder: Path, commit: str) -> Path:
    folder.mkdir()
    zip_path = folder / "Lightning-v0.5.0-beta.1-dev-r7-dddddddd-Windows-x64.zip"
    zip_path.write_bytes(b"tested zip")
    (folder / "APP_SHA256SUMS").write_text(f"{build.sha256(zip_path)}  {zip_path.name}\n")
    (folder / "BUILD_INFO.txt").write_text(f"Lightning 0.5.0-beta.1 for Windows x64\nBuild: development (not a release)\n"
                                           f"Commit: {commit}\nRun: workflow run 7, attempt 1\n")
    return zip_path


def test_the_bundle_offers_only_a_pair_from_one_commit(tmp_path):
    commit = "d" * 40
    windows = tmp_path / "windows"
    zip_path = _windows(windows, commit)
    apk = tmp_path / "Lightning-Test-0.5.0-beta.1-70-dddddddd.apk"
    apk.write_bytes(b"checked apk")
    info = {"sha256": build.sha256(apk), "certificate_sha256": "ab" * 32, "commit": commit,
            "version_name": "0.5.0-beta.1-test.70+dddddddd", "version_code": 70}
    names = build.bundle(windows, apk, info, tmp_path / "out", commit, "10", "1", "7")
    assert names == {"pc": "Lightning-Test-0.5.0-beta.1-70-dddddddd-PC", "phone": "Lightning-Test-0.5.0-beta.1-70-dddddddd-Phone"}
    for side, binary in (("PC", zip_path), ("Phone", apk)):
        folder = tmp_path / "out" / side
        assert sorted(p.name for p in folder.iterdir()) == sorted([binary.name, "BUILD.json", "README.txt", "SHA256SUMS"])
        manifest = json.loads((folder / "BUILD.json").read_text())
        assert manifest["commit"] == commit and manifest["windows"]["built_by_run"] == "7"
        assert f"{build.sha256(zip_path)}  {zip_path.name}" in (folder / "SHA256SUMS").read_text()
        assert "sample or real data" in (folder / "README.txt").read_text()

    other = tmp_path / "other"
    _windows(other, "e" * 40)
    with pytest.raises(build.BuildError, match="not d"):
        build.bundle(other, apk, info, tmp_path / "o2", commit, "10", "1", None)  # a ZIP of another commit
    zip_path.write_bytes(b"swapped")
    with pytest.raises(build.BuildError, match="not the ZIP that was tested"):
        build.bundle(windows, apk, info, tmp_path / "o3", commit, "10", "1", None)
    _windows(tmp_path / "w2", commit)
    with pytest.raises(build.BuildError, match="test certificate"):
        build.bundle(tmp_path / "w2", apk, dict(info, certificate_sha256=None), tmp_path / "o4", commit, "10", "1", None)
    apk.write_bytes(b"another apk")
    with pytest.raises(build.BuildError, match="not the one that was checked"):
        build.bundle(tmp_path / "w2", apk, info, tmp_path / "o5", commit, "10", "1", None)


def test_the_test_key_script_makes_a_store_android_can_sign_with(tmp_path):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.serialization import pkcs12

    key_tool = _load("tools/android_test_key.py")
    store, fingerprint = key_tool.make_keystore("pw", rounds=1000)
    loaded = pkcs12.load_pkcs12(store, b"pw")
    assert loaded.cert.friendly_name == b"lightning-test"
    assert loaded.key.key_size == 3072
    assert loaded.cert.certificate.fingerprint(hashes.SHA256()).hex() == fingerprint
    years = (loaded.cert.certificate.not_valid_after_utc - datetime.now(timezone.utc)).days / 365
    assert years > 29

    folder = tmp_path / "key"
    printed = key_tool.write(folder)
    assert sorted(p.name for p in folder.iterdir()) == sorted(key_tool.FILES)
    assert (folder / "certificate-sha256.txt").read_text().strip() == printed
    store = base64.b64decode((folder / "ANDROID_TEST_KEYSTORE.txt").read_text())
    pkcs12.load_pkcs12(store, (folder / "ANDROID_TEST_KEYSTORE_PASSWORD.txt").read_text().strip().encode())
    with pytest.raises(SystemExit, match="not empty"):
        key_tool.write(folder)  # never overwrites a key


def test_the_workflows_offer_a_pair_only_from_one_run_and_never_sign_with_another_key():
    flows = ROOT / ".github" / "workflows"
    app = (flows / "desktop-probe.yml").read_text(encoding="utf-8")
    phone_job = app[app.index("\n  phone:"):app.index("\n  bundle:")]
    bundle_job = app[app.index("\n  bundle:"):app.index("\n  release:")]
    release_job = app[app.index("\n  release:"):]
    assert "uses: ./.github/workflows/android-app.yml" in phone_job
    assert "bundle: ${{ needs.tests.outputs.phone == 'true' }}" in phone_job  # the daily check never bundles
    assert "needs.tests.outputs.phone == 'true' || needs.tests.outputs.phone_daily == 'true'" in phone_job
    assert "needs: [tests, windows, phone]" in bundle_job and "needs.phone.result == 'success'" in bundle_job
    assert "needs.windows.result == 'success' || (needs.windows.result == 'skipped' && needs.tests.outputs.reuse_run != '')" in bundle_job
    assert "phone_build.py bundle" in bundle_job and bundle_job.count("retention-days: 7") == 2
    assert "github.event_name == 'workflow_dispatch'" in bundle_job  # a tag uses the permanent release instead
    assert "needs: [tests, windows, phone]" in release_job.split("steps:")[0]
    assert "name: phone-apk" in release_job and "phone_build.py bundle" in release_job
    assert "publish_release.sh" in release_job and "BUILD.json" in release_job
    assert "format('-{0}', github.run_id)" in app  # a push never cancels the test builds
    android = (flows / "android-app.yml").read_text(encoding="utf-8")
    sign = android[android.index("- name: Sign with the test key"):android.index("- name: Check the signed app")]
    assert 'if [ "$BUNDLE" = "true" ]; then' in sign and "exit 1" in sign  # no key, no APK for the bundle
    for secret in ("ANDROID_KEYSTORE_BASE64", "ANDROID_KEYSTORE_PASSWORD", "ANDROID_KEY_ALIAS", "ANDROID_KEY_PASSWORD"):
        assert f"secrets.{secret}" in sign
        assert f"secrets.{secret}" not in phone_job and f"secrets.{secret}" not in app
    sign_job = android[android.index("\n  sign:"):]
    assert "environment: android-signing" in sign_job.split("steps:")[0]
    assert "github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/v')" in sign_job.split("steps:")[0]
    assert "--ks-pass env:STORE_PASS --key-pass env:KEY_PASS --ks-key-alias \"$KEY_ALIAS\"" in sign
    assert "Public Android signing certificate SHA-256" in sign
    assert "--certificate packaging/android-test-certificate.sha256" in android
    assert "if: inputs.bundle && steps.sign.outputs.signed == 'true'" in android  # only a signed APK is uploaded
    build_job = android[android.index("\n  apk:"):android.index("\n  sign:")]
    assert "secrets." not in build_job and "gradle" in build_job  # the key never meets Gradle
    assert "gradle" not in android[android.index("\n  sign:"):]


# Imports the shipped apps lack, each a strict known gap: the test fails once it is fixed, so the entry is
# removed. None today (cd23258's httpx in the self-check was replaced by a client-free request, 2026-10-07).
KNOWN_UNSHIPPED: set[str] = set()
DESKTOP_ONLY = {"webview", "clr", "System"}  # pywebview and pythonnet, used only under lightning/desktop/


def _third_party_imports() -> dict[str, set[str]]:
    import ast
    import sys
    found: dict[str, set[str]] = {}
    for path in (ROOT / "lightning").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                if top not in sys.stdlib_module_names and top != "lightning":
                    found.setdefault(top, set()).add(path.relative_to(ROOT).as_posix())
    return found


def test_shared_code_imports_only_what_both_apps_ship():
    """A module the code imports but an app does not carry breaks that app only when it runs, after a
    green suite (the developer has it installed). Checked here, on every push, instead."""
    import re
    spec = (ROOT / "packaging" / "desktop-app.spec").read_text(encoding="utf-8")
    excluded = set(re.findall(r'"([\w.]+)"', spec[spec.index("excludes=["):spec.index("]", spec.index("excludes=["))]))
    phone = {name.replace("-", "_") for name in _locked()} | {"multipart"}  # python-multipart's module
    missing = set()
    for module, paths in _third_party_imports().items():
        for path in paths:
            desktop_only = path.startswith("lightning/desktop/")
            if module in DESKTOP_ONLY and desktop_only:
                continue
            if module in excluded or (not desktop_only and module not in phone):
                missing.add(f"{module} <- {path}")
    assert missing == KNOWN_UNSHIPPED


def test_the_pc_and_the_phone_run_the_same_core_libraries():
    """The PC and the phone open the same encrypted ledger and serve the same pages: the libraries that
    touch either must be the same version on both, or a sync can meet a format one side does not know."""
    core = ("sqlcipher3", "cryptography", "fastapi", "starlette", "pydantic", "pydantic-core", "jinja2",
            "uvicorn", "python-multipart", "tzdata")
    phone = _locked()
    for lock in ("desktop-probe-win.lock", "desktop-probe-linux.lock"):
        desktop: dict[str, str] = {}
        for line in (ROOT / "requirements" / lock).read_text(encoding="utf-8").splitlines():
            if "==" in line and not line.startswith((" ", "#")):
                name, version = line.split(" ")[0].split("==")
                desktop[name.lower().replace("_", "-")] = version
        for name in core:
            assert desktop.get(name) == phone.get(name), f"{name}: {lock} has {desktop.get(name)}, the phone {phone.get(name)}"


def test_the_phones_settings_name_the_build_a_screenshot_came_from(tmp_path, monkeypatch):
    """The phone test build writes its name (`<version>-test.<commits>+<commit>`) where Settings shows the
    app version, the check refuses an APK that would show anything else, and a build without it shows the
    source version."""
    from fastapi.testclient import TestClient

    from lightning import DISPLAY_VERSION
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Credentials
    from lightning.ui import web
    from test_profile_app import create

    assert web.build_version(tmp_path / "absent.txt") == DISPLAY_VERSION
    name = "0.5.0-beta.1-test.445+38557359"
    (tmp_path / "build_identity.txt").write_text(name + "\n")
    assert web.build_version(tmp_path / "build_identity.txt") == name
    gradle = (ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    assert 'lightning/build_identity.txt").writeText(it)' in gradle

    monkeypatch.setitem(web.templates.env.globals, "app_version", name)
    cfg = Credentials("http://127.0.0.1:9871")
    app = profile_app(cfg, tmp_path / "docs", devices=Devices(tmp_path / "app", port=0), phone=True)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as phone:
        phone.get("/__launch", params={"code": cfg.launch_code})
        create(phone)
        assert f"v{name}" in phone.get("/settings").text

    apk = _apk(tmp_path / "named.apk", extra_app=("lightning/build_identity.txt",))
    assert build.carried_identity(apk) == "x"  # _archive writes "x" into every file
    assert build.carried_identity(_apk(tmp_path / "unnamed.apk")) is None
