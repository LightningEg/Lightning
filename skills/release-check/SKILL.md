---
name: release-check
description: Get Lightning ready to tag a release and publish it safely: version agreement, clean main, full tests, no secrets or private data, changelog, price files, then the tag. Use before any release or beta, or when asked "are we ready to ship".
---

# Release check

Tool-neutral. Follow the steps in order and stop at the first failure; fix it (own branch, test, changelog line) and start that step again.
**Pushing a tag publishes to the public downloads repository and cannot be undone** (releases are never replaced). Do steps 1–7 yourself;
**ask the owner before step 8**, and say what the tag will publish.

Background you may need: `docs/ARCHITECTURE.md` › *Desktop app and encrypted profiles* › *Build and release*, `.github/workflows/desktop-probe.yml`
(PC and phone app), `packaging/ci_scope.py` (what each push, daily, manual and tag run does), `packaging/publish_release.sh` (the publishing step).
CI minutes cost money (Windows counts double): do not start a manual workflow run unless the release needs that evidence now.

## Token rules

Read only the sections named here. Run scripts and print findings, not files. Run the full test suite once, near the end, not after every fix.

## Steps

1. **Fresh main.** `git checkout main && git pull`. Work on a branch `claude/release-<version>` for any fix (AGENTS.md §6).
2. **Stale and private check.** Run `python tools/stale_check.py` (skill `stale-check`) and `python tools/release_check.py`. The second prints the version, the tag it implies
   (`1.1.0b1` becomes `v1.1.0-beta.1`) and every problem it finds: versions that disagree in `pyproject.toml`, `lightning/__init__.py` and the README; an unclean tree or
   a branch other than `main`; missing `LICENSE` or `CONTRIBUTING.md`; an empty *Unreleased* changelog; tracked files that look like secrets or private data;
   TODO/FIXME markers in `lightning/`. Fix every finding. On a fix branch the "not on main" finding is expected until you merge.
3. **Tests.**
   - `python -m pytest -q -n auto --dist loadfile` (full suite), then `lint-imports` (architecture contracts).
   - `python -m pytest -q tests/test_mohab_year.py` is part of the suite; read its docstring only. A `known_gap` that now passes must be removed (and the Overview's *Today* column in `docs/PROJECT_OVERVIEW.md` updated).
   - Failures from a missing module (for example `sqlcipher3`) mean the environment cannot run the encrypted-profile tests: list them once, and do not release until a machine that can run them is green (the CI workflow does).
4. **Bug sweep.** Run the `bug-hunt` skill's steps 1–4 (crawl, reconcile figures, forms) and, for money code changed since the last tag, the `number-audit` skill. A wrong figure blocks the release.
5. **Look and language.** Run `guideline-audit` (PC and phone) and, if the release has Arabic, `arabic-check`. Fix anything that fails.
6. **Speed.** `python tools/perf_check.py`. A page over its limit that was not slow in the last release blocks it (skill `perf-check`).
7. **Prepare the release commit** on the fix branch:
   - Version: set the new number in `pyproject.toml` (`version = "1.1.0b2"`), `lightning/__init__.py` (`__version__`) and the README line "The source version is **v1.1.0-beta.2**". Run `python tools/release_check.py` again.
   - Changelog: rename `## [Unreleased]` to `## [1.1.0b2] · yyyy-mm-dd` (date from the `date` command) and add a new empty `## [Unreleased]` above it. Keep it three lines per entry.
   - Price files: `python -m tools.market release --required` must succeed (a tagged release needs `lightning/market/market.zip`; it is generated, never committed).
   - Commit, push the branch, `git pull --rebase origin main`, merge into `main`, push `main`. Wait for the Linux CI run on that commit to pass (use the GitHub tools to read the run; do not poll in a loop).
8. **Tag (owner approves first).** The tag must be the version, sit on `main`, and match: `python packaging/ci_scope.py --check-release-tag` after `git tag v1.1.0-beta.2`.
   `git push origin v1.1.0-beta.2` starts the tag run: tests, the Windows ZIP, the signed APK, and publishing to `elfekimuhammed/Lightning-downloads` after the
   `production-release` environment approval. Required repository secrets (names only, never print values): `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`,
   `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`, `LIGHTNING_DOWNLOADS_TOKEN`. If one is missing the run says so; tell the owner, do not work around it.
9. **After publishing.** Update the website repo (skill `website-sync`): Downloads page, Version Archive and checksums, English and Arabic, and the `Current app release` line in its README.

## Never

- Never move, delete or re-push a published tag. A bad release gets a new version.
- Never commit signing keys, tokens, real databases or profile data. The repo is public.
- Never skip a failing test, or mark it as expected, to reach green.

## Report

**Where findings go.** Read `issues/README.md` once. Fix a small finding now (branch, test, changelog line) and file **no** item. File anything bigger as one item in
the milestone it belongs to, `issues/<n>-<name>/<code>-<what>.md` (code from `python tools/issues.py next <n>`; this skill's name in `skills`, your model in `by`, `app_version`
from `pyproject.toml`, `commit` from `git rev-parse --short HEAD`), then run `python tools/issues.py`. Finishing an item means deleting its file in the same commit and adding its code to the milestone's `done:`. Never leave a finding only in chat.

Version and tag; each step passed or failed; what blocked; the one decision you need from the owner (usually: "tag now?").
