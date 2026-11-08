---
name: dependency-change
description: Add, update or remove a third-party package or GitHub Action (Python, npm or Actions; Dependabot's grouped pull requests included) safely: whether it is needed, who maintains it, its licence, Windows and Android wheels, hashed locks regenerated together, pinned actions, and the evidence each kind of change needs. Use when a pull request changes pyproject.toml, requirements/, a package.json or a workflow's uses line, or before adding any new library.
---

# Change a dependency

Tool-neutral. A dependency is outside code that runs with the profile's data and the release keys: review it as skill `review-outside-code` says, plus the steps below. Lightning ships on Windows (desktop locks) and Android (native wheels built by `android-native-wheels.yml`); a version that works on Linux CI can still break both.

## Steps

1. **Is it needed?** The standard library or a package already in `pyproject.toml` comes first. A new package for one function is a reject; a new JavaScript or CSS framework is a reject (the UI is vanilla, guideline tokens only).
2. **Vet a new package.** Maintained (a release this year, more than one maintainer or a known one), no recent change of owner, the name spelled as on its home page (typosquats), a licence from the allowed list in skill `review-outside-code` with its notice added to `packaging/notices/` when it ships, pure Python or with wheels for Windows x64 and the Android targets. A native package needs a wheel built through `android-native-wheels.yml` first: that is item IT-1H's path, owner-run.
3. **Pick versions at least two weeks old**, and read the changelog between the old and new version for breaking changes and security notes.
4. **Change the inputs, then regenerate every lock that holds the package, together.** Never edit a `.lock` by hand.
   - Desktop, browser, build tools, probes: the exact `uv pip compile ... --generate-hashes` command written at the top of each `requirements/*.lock`.
   - Android: `python tools/android_lock.py` from `requirements/android.in` and the published wheel checksums.
   - `cloudflare/journal`: `npm install` there, then `npm ci --ignore-scripts && npm test && npm audit --audit-level=high` as CI does.
   - `sqlcipher3`, `cffi`, `pydantic-core` and `cryptography` move only as IT-1H describes (`issues/1-easy-to-contribute/IT-1H-coordinate-packaged-dependency-refresh.md`).
5. **Actions.** `uses:` pinned to a full commit SHA with a `# vX.Y.Z` comment; the SHA is the tag's commit on the action's own repository. Check the new version asks for no wider `permissions:` and still runs on the Node version GitHub supports.
6. **Test.** `python -m pytest -q -n auto --dist loadfile`, `ruff check lightning tools`, `lint-imports`; `tests/test_phone_build.py` for any lock change. The `dependency-review` check must pass (no high-severity advisory).
7. **Native evidence, only when needed.** A change to a package inside the Windows ZIP or the APK needs the matching manual workflow (`desktop-probe.yml`, `android-app.yml`) before merge; run it by hand once, because Windows minutes cost double (AGENTS.md section 2). Pure test or lint tools need none.
8. **Commit** with `Release-note: none` unless people notice the change, and a `Detail:` naming the packages and versions.

## Dependabot's pull requests

Grouped weekly per ecosystem (`.github/dependabot.yml`). Merge a group only when every lock it should touch is regenerated and green; if it moves a native package or leaves the Android or desktop locks behind, do not merge it: close it with one comment pointing at IT-1H, or take the safe packages onto your own branch and regenerate the locks there.
