"""The Windows and Android pair publishes only after every file reads back unchanged."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "packaging"), str(ROOT / "tools")]
from store_keygen import make_key  # noqa: E402
from update_manifest import _unb64, sign  # noqa: E402
SCRIPT = ROOT / "packaging" / "publish_release.sh"
TAG = "v2.0.0"
ZIP = f"Lightning-{TAG}-Windows-x64.zip"
APK = "Lightning-2.0.0-123-abc123.apk"

pytestmark = pytest.mark.skipif(not all(shutil.which(tool) for tool in ("bash", "jq", "sha256sum", "cmp")),
                                reason="needs bash, jq, sha256sum and cmp (present on Linux CI)")


def publish(tmp_path: Path, state: dict, skip_manifest: bool = False, **env) -> tuple[subprocess.CompletedProcess, dict]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "gh"
    fake.write_text(f"#!/bin/sh\nexec {sys.executable} {ROOT / 'tests' / 'fake_gh.py'} \"$@\"\n", encoding="utf-8")
    fake.chmod(0o755)
    release = tmp_path / "release"
    release.mkdir()
    payload = os.urandom(50_000)
    phone = os.urandom(20_000)
    (release / ZIP).write_bytes(payload)
    (release / APK).write_bytes(phone)
    (release / "SHA256SUMS").write_text(f"{hashlib.sha256(payload).hexdigest()}  {ZIP}\n"
                                          f"{hashlib.sha256(phone).hexdigest()}  {APK}\n", encoding="utf-8")
    (release / "BUILD.json").write_text(json.dumps({"commit": "abc123", "windows": {"file": ZIP},
        "android": {"file": APK, "application_id": "org.lightning.app", "debuggable": True,
                    "certificate_sha256": "a" * 64}}), encoding="utf-8")
    (release / "BUILD_INFO.txt").write_text(f"Lightning 2.0.0 for Windows x64\nBuild: release {TAG}\n"
                                            "Commit: abc123\nRun: workflow run 22, attempt 1\n", encoding="utf-8")
    keys = tmp_path / "keys.json"
    jwk, public = make_key("test-key")
    keys.write_text(json.dumps({"keys": {"test-key": public}}), encoding="utf-8")
    if not skip_manifest:
        sign(release, TAG, ZIP, json.dumps(jwk), keys={"test-key": _unb64(public)}, source_version="2.0.0")
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    environment = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "MOCK_STATE": str(state_file),
                   "DOWNLOADS_REPO": "owner/Lightning-downloads", "TAG": TAG, "ZIP": ZIP, "APK": APK,
                   "GH_TOKEN": "token", "PYTHON": sys.executable, "UPDATE_KEYS": str(keys),
                   "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"), **env}
    result = subprocess.run(["bash", str(SCRIPT)], cwd=release, env=environment, capture_output=True, text=True)
    return result, json.loads(state_file.read_text(encoding="utf-8"))


def published(state: dict) -> list[dict]:
    return [r for r in state["releases"] if not r["draft"]]


def test_a_tested_pair_is_published_with_both_apps_and_checksums(tmp_path):
    result, state = publish(tmp_path, {"releases": [], "tags": ["v1.5.4"]})
    assert result.returncode == 0, result.stdout + result.stderr
    [release] = published(state)
    assert release["tag_name"] == TAG and not release["prerelease"] and release["target_commitish"] == "main"
    assert release["name"] == "Lightning 2.0.0 for Windows and Android"
    assert [a["name"] for a in release["assets"]] == [ZIP, APK, "SHA256SUMS", "BUILD.json", "UPDATE.json", "UPDATE.json.sig"]
    assert hashlib.sha256((tmp_path / "release" / ZIP).read_bytes()).hexdigest() in release["body"]
    assert hashlib.sha256((tmp_path / "release" / APK).read_bytes()).hexdigest() in release["body"]
    assert "does not make releases immutable" in result.stdout  # a reminder until the setting is on


@pytest.mark.parametrize("state, env, message", [
    ({"releases": [], "tags": []}, {"GH_TOKEN": ""}, "LIGHTNING_DOWNLOADS_TOKEN secret is not set"),
    ({"releases": [], "tags": [], "auth_fail": True}, {}, "token cannot read"),
    ({"releases": [{"id": 7, "tag_name": TAG, "draft": False, "assets": []}], "tags": [TAG]}, {},
     "already has a release"),
    ({"releases": [], "tags": [TAG]}, {}, "already has a tag"),
    ({"releases": [], "tags": []}, {"ZIP": "Lightning-v2.0.0-dev-r21-abcdef12-Windows-x64.zip"},
     "development build cannot be published"),
    ({"releases": [], "tags": [], "server_error": True}, {}, "Could not check whether"),
    # A published release whose tag was deleted turns back into a draft that keeps its real name.
    ({"releases": [{"id": 8, "tag_name": TAG, "draft": True, "name": "Lightning 2.0.0 for Windows and Android",
                    "assets": []}], "tags": []}, {}, "this job did not leave behind"),
])
def test_nothing_is_published_or_replaced_when_a_release_cannot_be_trusted(tmp_path, state, env, message):
    before = json.loads(json.dumps(state))
    result, after = publish(tmp_path, state, **env)
    assert result.returncode != 0 and message in result.stdout, result.stdout + result.stderr
    assert published(after) == published(before)
    assert [r["id"] for r in after["releases"]] == [r["id"] for r in before["releases"]]  # nothing deleted


def test_an_upload_that_changed_in_transit_is_never_published(tmp_path):
    result, state = publish(tmp_path, {"releases": [], "tags": [], "corrupt_upload": True})
    assert result.returncode != 0 and "differs from the tested file" in result.stdout
    assert not published(state) and state["releases"][0]["draft"]


def test_a_changed_phone_apk_is_never_published(tmp_path):
    result, state = publish(tmp_path, {"releases": [], "tags": [], "corrupt_upload": "apk"})
    assert result.returncode != 0 and "differs from the tested file" in result.stdout
    assert not published(state) and state["releases"][0]["draft"]


def test_a_draft_left_by_a_failed_attempt_is_replaced_by_the_new_attempt(tmp_path):
    state = {"releases": [{"id": 9, "tag_name": TAG, "draft": True, "assets": [],
                           "name": "Lightning 2.0.0 for Windows and Android (unpublished draft)"}], "tags": [], "immutable": True}
    result, after = publish(tmp_path, state)
    assert result.returncode == 0, result.stdout + result.stderr
    assert [r["id"] for r in after["releases"]] != [9] and len(published(after)) == 1
    assert "immutable" not in result.stdout  # no reminder once the downloads repository locks releases


def test_a_release_without_a_signed_update_manifest_is_never_published(tmp_path):
    result, state = publish(tmp_path, {"releases": [], "tags": []}, skip_manifest=True)
    assert result.returncode != 0 and "has no UPDATE.json" in result.stdout
    assert not state["releases"]


def test_a_manifest_for_another_zip_is_never_published(tmp_path):
    result, state = publish(tmp_path, {"releases": [], "tags": []}, ZIP="Lightning-v2.0.0-Windows-x64.zip", TAG="v2.0.1")
    assert result.returncode != 0 and not state["releases"]
