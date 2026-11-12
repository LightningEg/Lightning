"""The phone app's identity never changes once people have their money in it (owner, 2026-11-05).

Android keeps a profile in the app's private storage, and the manifest turns Android backup off. An APK with a
different application ID installs as a second, empty app; one signed by a different key refuses to update, and the
only way past that is an uninstall, which deletes the data. Version 2.0.0 changed the ID from
`org.lightning.app.test` and a user lost their phone book that way. These pins fail before such an APK is built.

Changing a pinned value is never a fix for a failing build. A lost or rotated key needs a signing lineage
(`apksigner rotate`, APK Signature Scheme v3) so installed phones accept the new key, and a recovery path that is
proved first; both are owner decisions.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_ID = "org.lightning.app"
PLAY_APP_ID = "com.lightningeg"
CERTIFICATE = "373d6ae1ccf484f2b3400ada865c54037f2b79059445abd4d9cd9d424636c6fb"


def _phone_build():
    spec = importlib.util.spec_from_file_location("phone_build_pins", ROOT / "packaging" / "phone_build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_build_carries_the_one_application_id():
    gradle = (ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    # The default ID is the one every GitHub APK carries; no build property or suffix may give some APKs another one.
    # Only the Play flavour has its own, com.lightningeg: the Play Console app was registered under it and Play fixes a
    # package name for good (owner, 2026-11-12). A Play install and a GitHub APK are therefore different apps to Android.
    assert re.findall(r"applicationId\s*=\s*(.+)", gradle) == [f'"{APP_ID}"', f'"{PLAY_APP_ID}"']
    assert "applicationIdSuffix" not in gradle
    flavours = gradle[gradle.index("productFlavors"):gradle.index("buildTypes")]
    assert re.findall(r"applicationId\s*=\s*(.+)", flavours) == [f'"{PLAY_APP_ID}"']
    assert not re.search(r"versionCode|versionNameSuffix", flavours)
    assert _phone_build().APP_ID == APP_ID and _phone_build().PLAY_APP_ID == PLAY_APP_ID


def test_every_build_is_checked_against_the_one_signing_certificate():
    pinned = (ROOT / "packaging" / "android-test-certificate.sha256").read_text(encoding="ascii").strip().lower()
    assert pinned == CERTIFICATE
    workflow = (ROOT / ".github" / "workflows" / "android-app.yml").read_text(encoding="utf-8")
    assert "--certificate packaging/android-test-certificate.sha256" in workflow


def test_a_wrong_signer_is_never_answered_by_pinning_a_new_key():
    source = (ROOT / "packaging" / "phone_build.py").read_text(encoding="utf-8")
    assert "commit its fingerprint" not in source
    assert "deletes" in source and "lineage" in source
