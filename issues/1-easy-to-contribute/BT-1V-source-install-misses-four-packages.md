---
title: The documented install misses four packages - a fresh clone, Codespaces and run.sh all stop at "No module named rapidfuzz"
type: bug
look: technical
severity: medium
pillar: build
size: S
model: sonnet
status: ready
created: 2026-11-09
by: Claude
app_version: 2.1.2
commit: 24e3cf8
---

## Report
Found by [r31](r31-code-review-and-loose-ends/report.md) F1. `pyproject.toml` `[project].dependencies` names eight packages. `requirements.txt` names four of them: `pypdf`, `openpyxl`, `defusedxml` and `rapidfuzz` are missing. Everything a person uses to install reads `requirements.txt`:

- README › Run from source and CONTRIBUTING: `pip install -r requirements-dev.txt` (its first line is `-r requirements.txt`);
- Codespaces: `.devcontainer/devcontainer.json` `postCreateCommand` runs the same command;
- `run.sh`, `run.bat`: they call `tools/install_source.py`, which installs `requirements.txt` plus the `encrypted` extras.

Reproduce in a clean virtual environment: `pip install -r requirements-dev.txt && python -m lightning --demo` ends with `ModuleNotFoundError: No module named 'rapidfuzz'` (from `lightning/core/matching.py:9`). CI never sees it because it installs from `requirements/*.lock`.

## Fix
One list, not two. Read only `requirements.txt`, `requirements-dev.txt`, `tools/install_source.py`, `tests/test_legacy_entry.py` (the test that pins the install command) and the `[project]` table of `pyproject.toml`.

1. Make `requirements.txt` carry exactly the eight entries of `[project].dependencies`, same spelling and pins, one per line, with a first comment line: `# Generated from pyproject.toml [project].dependencies; tests/test_source_install.py keeps them equal.`
2. Add `tests/test_source_install.py` with two tests: (a) the non-comment lines of `requirements.txt` equal `tomllib` `[project].dependencies` as sets; (b) every package named in `[project.optional-dependencies].dev` appears in `requirements-dev.txt` (compare the name before the first of `>=<=~!`).
3. Do not change `pyproject.toml`, the lock files or `tools/install_source.py`.

Test: `python -m pytest tests/test_source_install.py tests/test_legacy_entry.py -q`. Then prove it by hand once: `python -m venv /tmp/v && /tmp/v/bin/pip install -q -r requirements-dev.txt && /tmp/v/bin/python -c "import lightning.bootstrap"` prints nothing.

## Done when
A clean virtual environment built with the README's command imports `lightning.bootstrap`, and the new test fails if either list loses a package. Release-note: `build: the documented install now brings every package the app needs.`

Not in this item: making `pip install -e .` work (it needs a package list in `pyproject.toml`; nobody is told to use it).
