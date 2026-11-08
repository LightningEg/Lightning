---
name: fix-ci
description: Turn a red check green the right way: read the failing job's log, reproduce it locally, find whether the change, the test or the environment is wrong, fix it on the branch without skipping or weakening a test, and spend Windows and Android minutes only when the fix needs that evidence. Use when a pull request or main has a failing check, or a check is flaky.
---

# Fix CI

Tool-neutral. CI minutes cost money (2,000 a month, Windows counts double; AGENTS.md section 2). A pull request runs Linux only (`.github/workflows/pr-checks.yml`); Windows and Android run by hand or on tags (`packaging/ci_scope.py` decides).

## Never

Skip, delete, `xfail` or loosen a test to go green; add `continue-on-error`; re-run a red job hoping it passes; push an empty commit or close and reopen to restart CI; change a workflow's permissions to fix a failure. A `known_gap` in Mohab's test stays strict.

## Steps

1. **Which job, which head.** Read the failing job's log for the current head only (an older head's failure is history). Note the first error, not the last.
2. **Reproduce locally** with the job's own command:
   - `tests`: `python -m pytest -o addopts= -q -n auto --dist loadfile`, then the one failing test alone with `-x -q`; `lint-imports`; `ruff check lightning tools`.
   - `minimum-python`: `python3.11 -m compileall -q lightning tools tests/runtime_contracts` (no syntax newer than 3.11 there).
   - `release-notes`: `python tools/release_notes.py check-pr origin/main` (skill `write-release-notes`).
   - `protected-paths`: a warning, not a failure; explain the files in the pull request.
   - `dependency-review`, `journal-security`: skill `dependency-change`.
3. **Decide what is wrong.**
   - The change broke behaviour: fix the code.
   - The test pinned something the owner changed on purpose: update the test's expectation, keep its business assertion, and say so in the commit.
   - Passes alone, fails in the full run: shared state between tests (a module cache, a monkeypatch left behind, a fixed port or file name). Fix the isolation.
   - Passes locally, fails on CI: a missing lock package, the clock (CI runs in UTC; use the test's fixed dates), file order, or Linux paths. Fix the cause.
   - Flaky: run it 20 times in a shell loop. A real race is a bug: fix it or file it (skill `add-plan-item`) and tell the owner; never retry until green.
4. **Fix on the branch**, smallest change the failure needs; the changed area's tests, then the full suite once; push. Wait on the pull request's events; do not poll.
5. **Windows or Android only** (`desktop-probe.yml`, `android-app.yml`, `android-native-wheels.yml`): run by hand once, after the Linux suite is green and only when the fix touches packaging, native wheels, the desktop window or the phone frame. Read `packaging/ci_scope.py` to see whether an earlier run on this commit can be reused.
6. **Main is red.** That blocks everyone: fix it first, on its own branch and pull request, before other work.

A failure you cannot fix in this session: leave the pull request open with one comment saying what fails, what you tried and the next step, and file an item.
