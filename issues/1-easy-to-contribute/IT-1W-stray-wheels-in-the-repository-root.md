---
title: Four wheel files (49 MB) sit in the repository root by accident - remove them and stop the next one
type: tech
pillar: build
size: S
model: sonnet
github: 487
status: ready
created: 2026-11-09
by: Claude
app_version: 2.1.2
commit: 24e3cf8
---

## Report
Found by [r33](r33-code-review-and-loose-ends/report.md) F8. `git ls-files '*.whl'` lists four files in the root, added by accident in #375: `playwright-1.64.1-py3-none-manylinux1_x86_64.whl` (48 MB), `greenlet-3.5.6-...whl`, `pyee-14.0.0-py3-none-any.whl`, `typing_extensions-4.16.0-py3-none-any.whl`. `grep -rn "playwright-1.64.1\|pyee-14\|greenlet-3.5.6\|typing_extensions-4.16" --include=*.py --include=*.yml --include=*.toml --include=*.txt --include=*.md .` finds no reader. The fifth wheel, `packaging/third-party/rapidfuzz-3.14.3-py3-none-any.whl`, is deliberate (its README says why): keep it.

## Fix
1. `git rm` the four root wheels.
2. `.gitignore`: add `/*.whl` (root only, so the vendored wheel stays tracked).
3. Add one test to `tests/test_docs_structure.py` (or a new `tests/test_repo_hygiene.py`): `git ls-files` holds no `*.whl` outside `packaging/third-party/`, and no tracked file is larger than 5 MB except paths in a short allow-list you fill from what the test finds today (list each with a reason in a comment). Skip the test when `git` is not available.

Test: `python -m pytest tests/test_repo_hygiene.py -q`.

## Done when
The four files are gone from `main`, the test passes and fails if a wheel is added to the root. Release-note: none.

Not in this item: removing the files from Git history (a force-push to `main`; only the owner can decide that, and 49 MB in a 126 MB history does not need it).
