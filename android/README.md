# Lightning Android app

This directory builds the Lightning phone app (`org.lightning.app`): a WebView over the same Python 3.13 server
the PC runs, with the phone frame and screens (guideline Part C), fingerprint unlock, bank SMS reading, app-icon
shortcuts and a Quick Settings tile for Add. It began as the task 04a dependency probe; that history is below.
To see how fast the phone's pages are on a representative profile, run `python tools/perf_check.py --phone`.

**Building (2026-10-07).** Run the **Phone app** workflow by hand to check a change, or **PC and phone app**
on `main` for the matched test builds the owner installs; both are described in
docs/ARCHITECTURE.md › Build and release. Locally, `gradle --no-daemon :app:assembleDebug` from this
directory (JDK 17, Gradle 8.11.1, Android SDK platform/build-tools 35, Python 3.13) builds
`org.lightning.app` from `requirements/android.lock`. The notes below are the history of tasks 04a–04c.

GitHub Actions [run 37235081432](https://github.com/elfekimuhammed/Lightning/actions/runs/37235081432)
resolved each native dependency separately. The full build found no Android
distribution for `sqlcipher3==0.6.2`; the crypto-only build found only 42.0.8,
not pinned `cryptography==50.0.2`. No APK was produced or run on a phone.

Published-wheel check (2026-10-05): Chaquopy 17 supports Python 3.13
and arm64, but its [Android cryptography wheel index](https://chaquo.com/pypi-13.1/cryptography/)
lists 42.0.8 at most. Lightning pins 50.0.2, and its password slots use
`Argon2id`, [introduced in cryptography 44](https://cryptography.io/en/45.0.7/hazmat/primitives/key-derivation-functions/).
The [Chaquopy package guidance](https://chaquo.com/chaquopy/doc/current/faq.html)
says missing native packages need Android wheels built separately. Both pinned
native packages are unavailable to Chaquopy's resolver. Do not swap in
cryptography 42 or plaintext SQLite to make the probe pass.

The next step is a reproducible arm64 build of the two pinned Android wheels,
including their OpenSSL/SQLCipher link dependencies and 16 KB page support, then
an APK install and import check on a real device. If that fails, evaluate the
proposal's narrow native SQLCipher adapter without duplicating financial rules.

Source-wheel experiment [run 37235463323](https://github.com/elfekimuhammed/Lightning/actions/runs/37235463323)
also failed. `cryptography==50.0.2` reached Android Rust/C compilation but could
not find `Python.h` in the cross-build include paths. `sqlcipher3==0.6.2`
reached its Conan OpenSSL dependency graph and stopped because the Android
`settings.os.api_level` was undefined. These are build-configuration failures,
not evidence that compatible wheels are impossible. Fix and rerun both build
configurations before deciding whether the native adapter is necessary.

The next manual source-wheel run tests those two configuration fixes. The
cryptography job asks cibuildwheel to locate the target Python header and add
its directory to `CFLAGS`. The SQLCipher job patches only the downloaded
0.6.2 `setup.py` in its disposable build directory to pass
`os.api_level=24` to Conan. Its exact expected source line is checked before
patching. This is a feasibility probe, not a patched package for release;
produced wheels still need dependency/link, 16 KB page and on-device import
checks. [cibuildwheel environment syntax](https://cibuildwheel.pypa.io/en/stable/options/#environment)
and [Conan Android API setting](https://docs.conan.io/2.14/examples/cross_build/android/ndk.html)
are the build references.

The first configuration rerun, [run 37240415999](https://github.com/elfekimuhammed/Lightning/actions/runs/37240415999),
stopped before either compiler: cibuildwheel evaluates `CIBW_ENVIRONMENT_ANDROID`
without shell glob expansion, so the inline `find /tmp/cibw-run-*/...` received
the `*` literally. A small Python locator replaced that glob and requires
exactly one target `Python.h`. These were configuration errors, not wheel results.

The locator rerun, [run 37244107860](https://github.com/elfekimuhammed/Lightning/actions/runs/37244107860),
passed that earlier failure. Cryptography still fails when its Rust/C build
cannot include `Python.h`; cibuildwheel's Android environment subsequently
rewrites `CFLAGS`, so the compiler's actual include path must be inspected at
the build hook. SQLCipher passes `os.api_level=24` to Conan, then OpenSSL's
dependency graph rejects the incomplete profile because `settings.compiler`
is undefined. Neither job produced a wheel. The next probe must supply an
explicit Android Clang Conan profile and a target-header path that survives
the build environment setup. These remain configuration findings; they do not
establish Android runtime or 16 KB page compatibility.

**APK built (2026-10-06, Claude).** [Wheel run 37432876490](https://github.com/elfekimuhammed/Lightning/actions/runs/37432876490)
builds all four native wheels for Python 3.13 arm64 from their pinned sources: `cryptography==50.0.2` (static
OpenSSL 3.5.4, target flags in `CFLAGS_aarch64_linux_android`, which cibuildwheel does not rewrite),
`sqlcipher3==0.6.2` (explicit Conan Android host and Linux build profiles, linked to `liblog`), `cffi==2.0.0`
(static libffi 3.5.2) and `pydantic_core==2.46.5`; native libraries link with 16 KB pages. The
[probe run 37434558665](https://github.com/elfekimuhammed/Lightning/actions/runs/37434558665) installs them
(`-PwheelDir`) and builds the APK. 04a passes only when that APK, launched on a real arm64 phone, shows the
SQLCipher version (an owner step). Still unverified: loading on a device and 16 KB page alignment of
the packaged libraries.

**04a passed (2026-10-06).** On the owner's arm64 phone the probe from
[run 37451039074](https://github.com/elfekimuhammed/Lightning/actions/runs/37451039074) (wheels from
[run 37449625570](https://github.com/elfekimuhammed/Lightning/actions/runs/37449625570)) reported every check OK:
cffi 2.0.0, cryptography 50.0.2 (Argon2id and AES-GCM work), pydantic-core 2.46.5, fastapi 0.141.1, jinja2
3.1.6, uvicorn 0.54.0 and SQLCipher 4.12.0 community. Lesson: on Android a native module must declare its
libpython dependency (`-lpython3.13`); the wheel job now refuses one that does not. Open for Google Play:
16 KB page alignment of the Rust modules (linked with it from `24cfb0d`; the job reports any that is not).

**04b: encrypted round-trip (2026-10-06, Claude).** The probe now also runs `lightning/runtime/roundtrip.py` on the
committed dummy profile `tests/fixtures/roundtrip` (the build copies Lightning's package and the fixture in): unlock
with the password, read figures, write one expense, close, check that plain SQLite and a wrong key are refused,
open with the recovery key, set a new password, reopen, and list integrity, figures and row counts per table.
`tests/test_device_roundtrip.py` checks the same lines on Linux and Windows CI against `expected.json`; the phone's
`04b encrypted round-trip` line says OK only when every line is equal, and otherwise lists the lines that differ.
It also prints each step's seconds (input for 04d). Linux and Windows gave the expected lines in
[run 37460524735](https://github.com/elfekimuhammed/Lightning/actions/runs/37460524735); the first APK failed on the phone with no detail; the current one, from
[run 37467660638](https://github.com/elfekimuhammed/Lightning/actions/runs/37467660638), shows the whole error and CI checks it carries the probe, the round-trip and the fixture. 04b passes when that line is OK on the owner's phone.

**04b passed (2026-10-06).** On the owner's arm64 phone the probe from run 37467660638 reported the same lines as
Linux and Windows (fingerprint `a00fc4f576edb7c9`). Phone timings: unlock with password 0.54 s, open 0.06 s,
write 0.06 s, unlock with recovery key 1.79 s, reopen 0.65 s. Lesson: name every Chaquopy source folder; CI now
checks the APK carries the probe, the round-trip and the fixture. Since migration 0044 the rebuilt fixture's
fingerprint is `5c89115a01678f85` (only its schema lines changed). Migration 0049 adds the
currency registry; its refreshed fixture fingerprint is `15bc54a5bd7bae12`; after 0050–0052 it is `508597be08ffe695`; after 0053 (gam'eya) it is `e40a5763e15fdea7`; after 0054 (zakat) it is `210db71bb3aa6b6a`.

**04c: one shared page (2026-10-06, Claude).** At launch the probe also renders every finance page of the dummy
profile on the owning thread, with no server (`runtime/selfcheck.finance_page_checks`). **Open Lightning (04c)**
then runs the same loopback runtime as Windows (`Host`, `profile_app`) on a fresh copy of the profile in app-private
storage and opens it in a WebView: no file or content access, no remote debugging, no extra windows, plain HTTP
only to 127.0.0.1 (`res/xml/network_security_config.xml`), and every navigation or request off that origin
blocked. From the Overview it tries to leave three ways (https, file, intent) and to fetch the internet; all
must fail. Before the WebView opens, Python checks that the server refuses a missing cookie, a foreign Host or
Origin and a wrong launch code. Back stops the server, and the profile must close on its own thread and release
its lock. Last, it lists the app's loaded native libraries and fails any not aligned for 16 KB pages, and reports
the phone's page size. A 4 KB-page phone shows alignment only; loading on a 16 KB-page device is still unverified.
`tests/test_android_probe.py` runs the Python side on Linux. APK: [run 37469368422](https://github.com/elfekimuhammed/Lightning/actions/runs/37469368422).

**Milestone 1: the Lightning app (2026-10-06, Claude).** The launcher now opens Lightning itself (`org.lightning.app`,
`MainActivity`): the same profile app as Windows, served on 127.0.0.1 to the locked-down WebView of 04c, with
profiles in app-private storage that Google backup and phone-to-phone transfer exclude
(`res/xml/data_extraction_rules.xml`). Python's side is `src/main/python/lightning_android.py`. The phone listens for
its paired PC on port 47513; while the ledger is lent or a pairing is open and the app is in the background,
`SyncService` keeps it listening with a notification (Android limits this to about six hours a day). The 04a–04c
checks remain as `ProbeActivity`, off the home screen. The layout is still the PC's (milestone 2 brings Part C).
