# Technical Design (as built)

## Stack

| Concern | Choice | Where |
|---|---|---|
| Language | Python ≥ 3.11 (CI uses 3.13) | `pyproject.toml` |
| Web | FastAPI, Uvicorn, Jinja2, python-multipart | core dependencies |
| DB | SQLite; SQLCipher via `sqlcipher3==0.6.2` (extra `encrypted`) | `lightning/database/connection.py` |
| Crypto | `cryptography==50.0.2`, Argon2id, AES-256-GCM | `lightning/security/keys.py` |
| Desktop | pywebview 6.2.1 + pythonnet (Windows only) | extra `desktop` |
| Frontend | Server-rendered HTML, vanilla JS/CSS, no build step | `lightning/ui/static`, `templates` |
| Tests | pytest, pytest-xdist, httpx, import-linter | extra `dev` |
| Lint | ruff (F401, F811, F841 only) | `pyproject.toml` |

## Repository map

`lightning/` app · `tests/` (271 files, ≈2,170 test functions) · `docs/` · `guideline/` brand (mirrored to the website repo) · `issues/` the plan · `reports/` audits · `feedback/` · `skills/` repeatable procedures · `android/`, `packaging/`, `cloudflare/journal/` delivery · `tools/` maintenance scripts · `theme-kit/` themes · `NOW.md` hand-off.

## Patterns

- **Composition root:** `bootstrap.py` builds a `Container` of services; routes get it from `app.state`.
- **Unit of work:** `with db.transaction():` (nested = savepoints) so workflows span services atomically.
- **Single writer:** `TransactionService._create/_update` validates every ledger line against master data inside the write.
- **Pure engines:** `rules/engine.py`, `core/ledger.py::validate_posting`, FX `rate_for` (one lookup).
- **Append-only migrations:** `database/migrations/NNNN_*.sql`; each script commits with its version row.
- **Submission tokens:** add-forms carry a one-time token recorded in `audit_log` so a double-submit saves once.

## Money and precision

Quantities/amounts/prices are `INTEGER` micro-units (`_e6`). Two roundings on purpose: posted base amount rounds half-to-even (`core/ledger._round2`), displayed/typed amounts half-up (`core/money.quantize`). Changing either changes stored or shown money.

## State and caching

No client state framework. Per-request memo (`core/memo.py`) avoids repeated figure computation; SQLite indexes on ledger account/date, asset/date, category/date. No cross-request cache found.

## Authentication and authorization

Profile password only (no per-user authorization). Writes require the current session token (`SessionGate`, `lightning/runtime/app.py`). Device authorization uses signed v2 proposals and membership checks (`sync/journal/membership.py`, `authority.py`).

## Background processing

None in the server sense. Work happens at startup and unlock (backup, due valuation checkpoints, price packs). Price collection runs in CI (`market-data.yml`). Reminders are computed on read (`workflows/reminders.py`, `/reminders/due.json`).

## Testing architecture

| Kind | Examples |
|---|---|
| Acceptance | `tests/test_mohab_year.py` (a year through the screens; `known_gap` marks wrong screens) |
| Architecture | `tests/test_architecture.py`, `tests/test_docs_structure.py` |
| Figures | `tests/test_figures.py` (registry vs Glossary) |
| Devices/journal | `tests/test_two_devices.py`, `tests/test_journal_*.py`, `tests/test_edit_journal.py` |
| Safety | restore/promotion, backups, profile sessions |
| Language | `tests/test_arabic_*.py` |

Run changed areas with `pytest -q <files>`; full suite once before pushing: `pytest -n auto --dist loadfile` (AGENTS.md §2).

## Build and release

Windows: `packaging/package_app.py` + `desktop-app.spec`. Android: `packaging/phone_build.py`, `android/`. Release procedure: `skills/release-check`. Version lives in `lightning/__init__.py` and `pyproject.toml` (both 1.5.2) and must agree (`release-check`).
