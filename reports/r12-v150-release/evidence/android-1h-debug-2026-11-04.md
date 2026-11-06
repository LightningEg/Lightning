# Local Android debug build · 2026-11-04

- Source: `30e608bb2bac7b6a72bc70ea647b9e818fc09068`; `requirements/android.lock` names `android-wheels-r41803831558`.
- Toolchain: Temurin JDK 17.0.16, Gradle 8.11.1, Android platform 35/build-tools 35.0.0, Python 3.13; clean workspace SDK and Gradle cache. The build used the configured network proxy and system CA trust.
- `:app:assembleDebug -PtestVersionCode=983 -PtestVersionName=1.5.4-test.983+30e608bb` succeeded. The Android plugin signed the APK with an automatically generated development debug key despite an attempted unsigned override; no release or test signing key was used. It was not uploaded or published.
- `python packaging/phone_build.py check` passed: `org.lightning.app.test`, code 983, correct version, debuggable, `arm64-v8a`, permissions, required files and all 22 packages matching the lock. `apksigner verify --verbose` reported one signer, v2 verified. `zipalign -c -P 16 4` passed.
- APK SHA-256: `c6fa581c83b2a4c483d7708fa3bf3da93362d6f84cc77dd472eb38d39daa920e` (36,803,751 bytes).

This checks the built artifact and lock, not execution on a phone. Windows packaging and physical Android installation/runtime remain separate acceptance checks. The repository check's “not yet signed with the test key” means no release test certificate was supplied; it is not a claim that this APK is unsigned.
