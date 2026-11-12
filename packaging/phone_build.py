"""The phone half of the matched PC and phone builds (ai/ARCHITECTURE.md › Build and release). Standard library only.

    python packaging/phone_build.py identity                       # GitHub outputs: version code and name, APK name
    python packaging/phone_build.py check APK --build-tools DIR --code N --name TEXT [--certificate FILE] --info OUT
    python packaging/phone_build.py signer APK --build-tools DIR   # prints the signing certificate's SHA-256
    python packaging/phone_build.py aab AAB --bundletool JAR --code N --name TEXT   # the Play bundle (NF-11B1)
    python packaging/phone_build.py bundle --windows DIR --apk APK --info JSON --out DIR [--reused-from RUN]

`check` fails unless the APK is exactly what the workflow meant to build: the app ID and version, arm64 only,
the permissions in packaging/android-permissions.txt, the files the phone needs and no private data, exactly
the Python packages of requirements/android.lock, targeting TARGET_SDK, not debuggable (a release build; the
review builds of journal-local-build.yml pass --debug), and, with --certificate, signed by that certificate alone.
`aab` fails unless `bundletool validate` accepts the Play bundle and its manifest has the same ID, version and
target, and is not debuggable.
`bundle` writes the two downloads (PC and Phone) from one commit only after the Windows ZIP is proven to be the
tested one of the same commit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements" / "android.lock"
PERMISSIONS = ROOT / "packaging" / "android-permissions.txt"
PLAY_PERMISSIONS = {"com.android.vending.BILLING"}  # the play flavour only (NF-11B3); the GitHub APK never asks for it
APP_ID = "org.lightning.app"
PLAY_APP_ID = "com.lightningeg"  # the Play bundle only: the Play Console app was registered under this name
ABI = "arm64-v8a"
# Play takes new apps and updates only at this target (since 2026-08-31); android/app/build.gradle.kts matches it.
TARGET_SDK = "36"
# What the phone runs: the app's own Python, the shared package, the dummy round-trip fixture and the pages.
REQUIRED = ("probe.py", "lightning_android.py", "lightning/runtime/devices.py", "lightning/sync/transport.py",
            "lightning/runtime/roundtrip.py", "lightning/database/migrations/", "roundtrip_fixture/profile.db",
            "roundtrip_fixture/expected.json", "lightning/ui/static/app.js", "lightning/ui/templates/")
# Never in an APK: a database, key, certificate store, backup or log. The one exception is the committed
# dummy fixture (tests/fixtures/roundtrip: a dummy profile and its dummy key) the round-trip check opens.
PRIVATE = re.compile(r"(\.(db|sqlite3?|db-wal|db-shm|key|keystore|jks|p12|pfx|log|bak)$|(^|/)keys\.json$|(^|/)backups?/)",
                     re.IGNORECASE)
ALLOWED_PRIVATE = {"roundtrip_fixture/profile.db", "roundtrip_fixture/keys.json"}


class BuildError(Exception):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def display_version() -> str:
    text = (ROOT / "lightning" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'^DISPLAY_VERSION = "([^"]+)"', text, re.MULTILINE)[1]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


# ---------------------------------------------------------------- identity
def identity(commit: str, count: int, version: str) -> dict[str, str]:
    """The APK's version code (commits on main, so it never falls), version name and file name."""
    if count < 1 or count > 2_100_000_000:
        raise BuildError(f"version code {count} is out of Android's range")
    short = commit[:8]
    return {"version_code": str(count), "version_name": f"{version}-{count}+{short}",
            "apk": f"Lightning-{version}-{count}-{short}.apk", "stamp": f"{version}-{count}-{short}"}


# ---------------------------------------------------------------- lock
def locked_packages(text: str) -> dict[str, str]:
    """name -> version of every `name @ URL` line of requirements/android.lock (the version is the wheel's)."""
    found = {}
    for line in text.splitlines():
        if match := re.match(r"([A-Za-z0-9_.-]+) @ (\S+)", line):
            parts = match[2].rsplit("/", 1)[-1].split("-")
            found[normalize(match[1])] = parts[1]
    if not found:
        raise BuildError("requirements/android.lock lists no packages")
    return found


def wheels_tag(text: str) -> str:
    match = re.search(r"^# android-wheels: (android-wheels-r\d+)$", text, re.MULTILINE)
    if not match:
        raise BuildError("requirements/android.lock names no android-wheels release")
    return match[1]


# ---------------------------------------------------------------- APK contents
def imy_names(apk: zipfile.ZipFile, name: str) -> list[str]:
    """The file names inside one of Chaquopy's asset archives (.imy files are ZIPs)."""
    import io
    with zipfile.ZipFile(io.BytesIO(apk.read(name))) as inner:
        return inner.namelist()


def contents_problems(apk_path: Path, locked: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    """Problems with what the APK carries, and the packages it carries (name -> version)."""
    problems = []
    with zipfile.ZipFile(apk_path) as apk:
        names = apk.namelist()
        abis = {n.split("/")[1] for n in names if n.startswith("lib/") and n.count("/") >= 2}
        if abis != {ABI}:
            problems.append(f"native libraries for {sorted(abis) or 'no ABI'}, not {ABI} alone")
        assets = [n for n in names if n.startswith("assets/chaquopy/") and n.endswith(".imy")]
        other_abis = [n for n in assets if re.search(r"-(armeabi-v7a|x86|x86_64)\.imy$", n)]
        if other_abis:
            problems.append(f"Python files for other ABIs: {', '.join(other_abis)}")
        app = [n for n in assets if Path(n).name.startswith("app")]
        if not app:
            problems.append("no app Python archive (assets/chaquopy/app*.imy)")
        carried = [entry for name in app for entry in imy_names(apk, name)]
        for wanted in REQUIRED:  # exactly that file (Chaquopy may ship a module compiled: .pyc), or inside that folder
            if not any(entry in (wanted, wanted + "c") or (wanted.endswith("/") and entry.startswith(wanted))
                       for entry in carried):
                base = wanted.rstrip("/").rsplit("/", 1)[-1]
                near = [entry for entry in carried if entry.rstrip("/").rsplit("/", 1)[-1].startswith(base)][:3]
                problems.append(f"{wanted} is not in the APK" + (f" (found {', '.join(near)})" if near else ""))
        packages: dict[str, str] = {}
        requirement_files = []
        for name in assets:
            if Path(name).name.startswith("requirements"):
                entries = imy_names(apk, name)
                requirement_files += entries
                for entry in entries:
                    if match := re.match(r"([^/]+)-([^-/]+)\.dist-info/$", entry.split("/", 1)[0] + "/"):
                        packages[normalize(match[1])] = match[2]
        for entry in [n for n in names if not n.startswith("META-INF/")] + carried + requirement_files:
            if PRIVATE.search(entry) and entry not in ALLOWED_PRIVATE:
                problems.append(f"{entry} looks like private data (database, key, backup or log)")
    if packages != locked:
        extra = {k: v for k, v in packages.items() if locked.get(k) != v}
        missing = {k: v for k, v in locked.items() if packages.get(k) != v}
        problems.append(f"Python packages differ from requirements/android.lock: APK has {extra or 'nothing extra'}, "
                        f"lock wants {missing or 'nothing more'}")
    return problems, packages


def carried_identity(apk_path: Path) -> str | None:
    """The build name the APK's Python carries for Settings (lightning/build_identity.txt), or None."""
    import io
    with zipfile.ZipFile(apk_path) as apk:
        for name in apk.namelist():
            if name.startswith("assets/chaquopy/app") and name.endswith(".imy"):
                with zipfile.ZipFile(io.BytesIO(apk.read(name))) as inner:
                    if "lightning/build_identity.txt" in inner.namelist():
                        return inner.read("lightning/build_identity.txt").decode("utf-8").strip()
    return None


# ---------------------------------------------------------------- aapt2 and apksigner
def badging(text: str) -> dict[str, str]:
    """Package name, version code and name, target SDK and whether it is debuggable, from `aapt2 dump badging`."""
    found = {}
    if match := re.search(r"^package: name='([^']*)' versionCode='([^']*)' versionName='([^']*)'", text, re.MULTILINE):
        found = {"package": match[1], "version_code": match[2], "version_name": match[3]}
    if match := re.search(r"^targetSdkVersion:'([^']*)'", text, re.MULTILINE):
        found["target_sdk"] = match[1]
    found["debuggable"] = "yes" if re.search(r"^application-debuggable", text, re.MULTILINE) else "no"
    return found


def permissions(text: str, package: str) -> set[str]:
    """The permissions the APK asks for, from `aapt2 dump permissions`, leaving out the app's own
    (such as the DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION AndroidX declares for itself)."""
    asked = set(re.findall(r"^uses-permission(?:-sdk-23)?: name='([^']+)'", text, re.MULTILINE))
    return {name for name in asked if not name.startswith(package + ".")}


def signers(text: str) -> list[str]:
    """The SHA-256 of each signer's certificate, from `apksigner verify --verbose --print-certs`;
    an error unless it verifies with scheme v2 or later."""
    if not text.lstrip().startswith("Verifies"):
        raise BuildError("apksigner does not verify the APK")
    if not re.search(r"^Verified using v[23](?:\.\d)? scheme[^:]*: true$", text, re.MULTILINE):
        raise BuildError("the APK is not signed with scheme v2 or later")
    return re.findall(r"^Signer #\d+ certificate SHA-256 digest: ([0-9a-f]{64})$", text, re.MULTILINE)


def tool(build_tools: Path, name: str, *args: str) -> str:
    result = subprocess.run([str(build_tools / name), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise BuildError(f"{name} {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout


def certificate(path: Path) -> str:
    if not path.exists():
        raise BuildError(f"{path.relative_to(ROOT)} is missing: commit the fingerprint tools/android_test_key.py printed")
    value = path.read_text(encoding="ascii").strip().lower().replace(":", "")
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise BuildError(f"{path.relative_to(ROOT)} does not hold one SHA-256 fingerprint")
    return value


def check(apk: Path, build_tools: Path, code: str, name: str, cert_file: Path | None, debug: bool = False) -> dict:
    """Every check on the built APK; returns what the bundle records about it."""
    problems = []
    lock_text = LOCK.read_text(encoding="utf-8")
    info = badging(tool(build_tools, "aapt2", "dump", "badging", str(apk)))
    wanted = {"package": APP_ID, "version_code": code, "version_name": name, "target_sdk": TARGET_SDK,
              "debuggable": "yes" if debug else "no"}
    for key, value in wanted.items():
        if info.get(key) != value:
            problems.append(f"{key} is {info.get(key)!r}, not {value!r}")
    asked = permissions(tool(build_tools, "aapt2", "dump", "permissions", str(apk)), APP_ID)
    allowed = {line.split("#")[0].strip() for line in PERMISSIONS.read_text(encoding="utf-8").splitlines()} - {""}
    if asked != allowed:
        problems.append(f"permissions differ from packaging/android-permissions.txt: APK adds {sorted(asked - allowed)}, "
                        f"lacks {sorted(allowed - asked)}")
    content_problems, packages = contents_problems(apk, locked_packages(lock_text))
    problems += content_problems
    shown = carried_identity(apk)
    if shown != name:
        problems.append(f"Settings would show {shown!r} as the version, not {name!r} (lightning/build_identity.txt)")
    fingerprint = None
    if cert_file is not None:
        fingerprint = certificate(cert_file)
        found = signers(tool(build_tools, "apksigner", "verify", "--verbose", "--print-certs", str(apk)))
        if found != [fingerprint]:
            problems.append(f"signed by {found}, not by the signing certificate {fingerprint} alone. The secrets hold "
                            "another key: put the original one back. Never pin a new key: installed phones refuse "
                            "the update, and the uninstall that gets past it deletes the person's data. A key that "
                            "must change needs a signing lineage first (tests/test_phone_identity_frozen.py)")
    if problems:
        raise BuildError("The APK is not the build it should be:\n- " + "\n- ".join(problems))
    return {"file": apk.name, "size": apk.stat().st_size, "sha256": sha256(apk), "application_id": info["package"],
            "version_code": int(code), "version_name": name, "debuggable": info["debuggable"] == "yes",
            "abi": ABI, "certificate_sha256": fingerprint, "android_wheels": wheels_tag(lock_text),
            "python_packages": dict(sorted(packages.items()))}


def manifest_problems(manifest: str, code: str, name: str) -> list[str]:
    """What is wrong with the Play bundle's manifest (`bundletool dump manifest`) for this build."""
    problems = []
    wanted = {"package": PLAY_APP_ID, "android:versionCode": code, "android:versionName": name,
              "android:targetSdkVersion": TARGET_SDK}
    for key, value in wanted.items():
        found = re.search(rf'\b{re.escape(key)}="([^"]*)"', manifest)
        if not found or found[1] != value:
            problems.append(f"{key} is {found[1] if found else None!r}, not {value!r}")
    if re.search(r'android:debuggable="true"', manifest):
        problems.append("the bundle is debuggable; Play refuses it")
    if "ProbeActivity" in manifest:
        problems.append("the bundle carries ProbeActivity, a debug-only screen")
    # The Play build asks for the GitHub APK's permissions plus Play Billing's, nothing else (NF-11B3).
    asked = set(re.findall(r'<uses-permission(?:-sdk-23)?\b[^>]*android:name="([^"]+)"', manifest))
    asked = {p for p in asked if not p.startswith(PLAY_APP_ID + ".")}  # the app's own, as permissions() leaves out
    allowed = {line.split("#")[0].strip() for line in PERMISSIONS.read_text(encoding="utf-8").splitlines()} - {""}
    allowed |= PLAY_PERMISSIONS
    if asked != allowed:
        problems.append(f"permissions differ from packaging/android-permissions.txt plus Play Billing: bundle adds "
                        f"{sorted(asked - allowed)}, lacks {sorted(allowed - asked)}")
    return problems


PAGE = 0x4000  # 16 KB: Play refuses a bundle targeting Android 15 or later whose native libraries need smaller pages


def load_alignments(elf: bytes) -> list[int]:
    """The alignment of each LOAD segment of a native library (ELF, 32 or 64 bit, little endian)."""
    if elf[:4] != b"\x7fELF" or elf[5] != 1:
        raise BuildError("not a little-endian ELF library")
    wide = elf[4] == 2
    phoff, = struct.unpack_from("<Q" if wide else "<I", elf, 32 if wide else 28)
    size, count = struct.unpack_from("<HH", elf, 54 if wide else 42)
    found = []
    for n in range(count):
        at = phoff + n * size
        if struct.unpack_from("<I", elf, at)[0] == 1:  # PT_LOAD
            found.append(struct.unpack_from("<Q" if wide else "<I", elf, at + (48 if wide else 28))[0])
    return found


def page_problems(aab: Path) -> list[str]:
    """Native libraries in the bundle that could not load on a phone with 16 KB memory pages: the ones in lib/, and the
    Python extension modules Chaquopy carries inside its asset archives and loads from there."""
    import io
    problems = []

    def look(label: str, elf: bytes) -> None:
        try:
            short = [a for a in load_alignments(elf) if a < PAGE]
        except (BuildError, struct.error, IndexError) as error:
            problems.append(f"{label}: cannot read its segments ({error})")
            return
        if short:
            problems.append(f"{label}: a LOAD segment is aligned to {min(short):#x}, not 16 KB ({PAGE:#x})")

    with zipfile.ZipFile(aab) as bundle:
        for name in sorted(bundle.namelist()):
            if "/lib/" in name and name.endswith(".so"):
                look(name, bundle.read(name))
            elif name.endswith(".imy"):
                with zipfile.ZipFile(io.BytesIO(bundle.read(name))) as inner:
                    for module in sorted(n for n in inner.namelist() if n.endswith(".so")):
                        look(f"{name}!{module}", inner.read(module))
    return problems


def check_aab(aab: Path, bundletool: Path, code: str, name: str) -> dict:
    def run(*args: str) -> str:
        result = subprocess.run(["java", "-jar", str(bundletool), *args], capture_output=True, text=True)
        if result.returncode != 0:
            raise BuildError(f"bundletool {args[0]} failed: {result.stderr.strip() or result.stdout.strip()}")
        return result.stdout
    run("validate", f"--bundle={aab}")
    problems = manifest_problems(run("dump", "manifest", f"--bundle={aab}"), code, name) + page_problems(aab)
    if problems:
        raise BuildError("The Play bundle is not the build it should be:\n- " + "\n- ".join(problems))
    return {"file": aab.name, "size": aab.stat().st_size, "sha256": sha256(aab), "application_id": PLAY_APP_ID,
            "version_code": int(code), "version_name": name, "target_sdk": int(TARGET_SDK)}


# ---------------------------------------------------------------- bundle
def windows_build(folder: Path, commit: str) -> tuple[Path, dict[str, str]]:
    """The tested Windows ZIP in a downloaded Windows artifact, proven to be of this commit."""
    zips = sorted(folder.glob("Lightning-v*-Windows-x64.zip"))
    if len(zips) != 1:
        raise BuildError(f"expected one Windows ZIP in {folder}, found {[z.name for z in zips]}")
    sums = (folder / "APP_SHA256SUMS").read_text(encoding="utf-8").split()
    if len(sums) < 2 or sums[1].lstrip("*") != zips[0].name or sums[0].lower() != sha256(zips[0]):
        raise BuildError(f"{zips[0].name} does not match APP_SHA256SUMS: it is not the ZIP that was tested")
    fields = dict(line.split(": ", 1) for line in (folder / "BUILD_INFO.txt").read_text(encoding="utf-8").splitlines()
                  if ": " in line)
    if fields.get("Commit") != commit:
        raise BuildError(f"the Windows ZIP is of commit {fields.get('Commit')}, not {commit}")
    return zips[0], fields


README = """Lightning {stamp}

These two files were built and tested from one commit ({commit}). You may use sample or real data; keep an independent backup. Install both from the same run:
a PC and a phone from different runs may not understand each other.

PC (Windows): extract the ZIP to a new folder and run Lightning\\Lightning.exe. If Windows says it
protected your PC, choose More info, then Run anyway (the app is not code-signed). Your
profiles stay in Documents\\Lightning. An older build refuses a profile a newer one has opened.

Phone (Android, arm64): unzip the download in Files, open the APK, and allow Files (or your browser)
to install apps when Android asks.
  - The first time: if the old "Lightning" app has data you want, move its ledger to the PC and
    verify it there before uninstalling. Uninstall erases that phone copy. Then uninstall the old
    app, install Lightning and pair again; both apps listen on the same network port.
  - Later: a newer Lightning APK updates this one and keeps its profile. If Android says
    the app was not installed, the APK is older than the one on the phone, or the signing key changed:
    uninstall Lightning once, then install.

These downloads last seven days; run "PC and phone app" again for fresh ones.
SHA256SUMS lists both files' SHA-256; BUILD.json says what was built, from where, and how it was checked.
"""


def bundle(windows_dir: Path, apk: Path, apk_info: dict, out: Path, commit: str, run: str, attempt: str,
           reused_from: str | None) -> dict[str, str]:
    if apk_info.get("sha256") != sha256(apk):
        raise BuildError("the APK is not the one that was checked")
    if not apk_info.get("certificate_sha256"):
        raise BuildError("the APK was not checked against the signing certificate")
    zip_path, fields = windows_build(windows_dir, commit)
    stamp = apk_info["version_name"].replace("+", "-")
    manifest = {
        "commit": commit, "run": run, "attempt": attempt,
        "built": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "windows": {"file": zip_path.name, "size": zip_path.stat().st_size, "sha256": sha256(zip_path),
                    "build_info": fields, "built_by_run": reused_from or run},
        "android": apk_info,
    }
    sums = f"{manifest['windows']['sha256']}  {zip_path.name}\n{apk_info['sha256']}  {apk.name}\n"
    names = {}
    for side, binary in (("PC", zip_path), ("Phone", apk)):
        folder = out / side
        folder.mkdir(parents=True, exist_ok=True)
        (folder / binary.name).write_bytes(binary.read_bytes())
        (folder / "SHA256SUMS").write_text(sums, encoding="utf-8")
        (folder / "BUILD.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (folder / "README.txt").write_text(README.format(stamp=stamp, commit=commit), encoding="utf-8")
        names[side.lower()] = f"Lightning-{stamp}-{side}"
    return names


# ---------------------------------------------------------------- command line
def outputs(values: dict[str, str]) -> None:
    lines = "".join(f"{key}={value}\n" for key, value in values.items())
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(lines)
    print(lines, end="")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("identity")
    p = sub.add_parser("check")
    p.add_argument("apk", type=Path)
    p.add_argument("--build-tools", type=Path, required=True)
    p.add_argument("--code", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--certificate", type=Path)
    p.add_argument("--info", type=Path, required=True)
    p.add_argument("--debug", action="store_true", help="a review build: debuggable on purpose")
    p = sub.add_parser("aab")
    p.add_argument("aab", type=Path)
    p.add_argument("--bundletool", type=Path, required=True)
    p.add_argument("--code", required=True)
    p.add_argument("--name", required=True)
    p = sub.add_parser("signer")
    p.add_argument("apk", type=Path)
    p.add_argument("--build-tools", type=Path, required=True)
    p = sub.add_parser("bundle")
    p.add_argument("--windows", type=Path, required=True)
    p.add_argument("--apk", type=Path, required=True)
    p.add_argument("--info", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--reused-from")
    args = parser.parse_args(argv)
    try:
        if args.command == "identity":
            outputs(identity(git("rev-parse", "HEAD"), int(git("rev-list", "--count", "HEAD")), display_version()))
        elif args.command == "check":
            info = check(args.apk, args.build_tools, args.code, args.name, args.certificate, args.debug)
            info["commit"] = git("rev-parse", "HEAD")
            args.info.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
            print(f"{args.apk.name}: every check passed" + ("" if args.certificate else " (not yet signed with the signing key)"))
        elif args.command == "aab":
            info = check_aab(args.aab, args.bundletool, args.code, args.name)
            print(f"{args.aab.name}: bundletool validates it; ID, version and target SDK {TARGET_SDK} match, not debuggable")
        elif args.command == "signer":
            print(" ".join(signers(tool(args.build_tools, "apksigner", "verify", "--verbose", "--print-certs", str(args.apk)))))
        else:
            info = json.loads(args.info.read_text(encoding="utf-8"))
            commit = os.environ["GITHUB_SHA"]
            if info.get("commit") != commit:
                raise BuildError(f"the APK is of commit {info.get('commit')}, not {commit}")
            outputs(bundle(args.windows, args.apk, info, args.out, commit, os.environ.get("GITHUB_RUN_ID", ""),
                           os.environ.get("GITHUB_RUN_ATTEMPT", "1"), args.reused_from or None))
    except BuildError as error:
        print(f"::error::{error}".replace("\n", "%0A"))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
