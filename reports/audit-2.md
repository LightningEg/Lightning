# Audit 2: backend efficiency and loose ends

2026-10-21 · Codex · Lightning 1.3.0 · reviewed `e88a1b2`.

## Fix follow-up

The owner requested fixes and a merge to main. Before implementation, the GitHub connector showed main at `a06e716`: 2E points 1–5 had already been fixed in another session. Those fixes were preserved, and this audit's split, overspend and physical-account examples now have passing regression coverage.

- **9G completed:** ordinary conversion create/edit/void/bulk-delete/restore calls refresh only affected old/new date/pair keys. A query selects the highest posted transaction id for each key, then reads just that winner. Posting and rate updates share a transaction. The full rebuild remains an atomic repair operation.
- **9H completed:** removed all eight helpers listed below after checking the latest source definitions, repository references, exports and dynamic command names. Legacy migration and restore implementations were preserved.
- **Measured before/after:** at conversion 1/10/50, full rebuilding needed 2/11/51 transaction reads; affected-key refresh needs 2/2/2. The median of the last ten writes in a 50-conversion temporary fixture fell from 4.26 ms to 0.85 ms on this host. These are local SQLite measurements, not a Windows benchmark.
- **Verification:** all eight tests in `tests/test_backend_engine_audit.py` pass with `LIGHTNING_PRICES_OFFLINE=1 /workspace/.venv/bin/python -m unittest discover -s tests -p test_backend_engine_audit.py -v`. Tests compare incremental rates to the full rebuild through edits, same-day conflicts, void/restore, bulk delete and reverse/foreign conversions; assert unrelated rates retain their rows; bound read counts; inject rate-save failure to prove create/edit rollback; and verify the existing 2E refusals. Issue-index validation and whitespace checks also run locally. Full pytest and import-linter validation must run in PR CI because optional local dependencies could not be installed.

The original findings and measurement limits below are retained as audit evidence. Restore/reboot acceptance and unfinished journal features are separate existing work, not completed by this fix.

The reporting paths measured here are inexpensive at a few thousand transactions. Write validation and history-wide rebuilding deserve attention before adding infrastructure or stored reporting totals. This is a targeted backend audit, not a certification of every financial path.

## Findings, in priority order

1. **High: expense splits can disagree with the ledger's base value.** `transactions/service.py::update_expense_split` parses each allocation without the asset's decimal-place check. Reproduced in a fresh temporary database: split a 1,000 expense into 333.334 / 333.333 / 333.333. Quantities sum to −1,000; rounded base amounts sum to −999.99. After a 2,000 opening, balance units are 1,000 while base value is 1,000.01. Existing [2E](../issues/2-safe-for-real-money/2E-engine-input-checks.md), point 1; fix that item rather than duplicating it.
2. **Medium: ordinary cash can go negative.** The same fixture accepted another 5,000 expense and ended at −4,000. `_check_holdings` explicitly skips cash; normal cash writes lack the refusal used for some investment/custody paths. Existing [2E](../issues/2-safe-for-real-money/2E-engine-input-checks.md), points 2–3, also covers physical accounts accepting cash. Decide the intended overdraft policy and enforce it consistently in services.
3. **Medium: conversion writes rebuild all historical trade rates.** `transactions/conversion.py::rebuild_trade_rates` deletes every TRADE rate, loads every posted conversion, and reads each transaction before saving rates again. An instrumented run made 2 transaction reads on conversion 1, 6 on conversion 5, and 11 on conversion 10 (one read is the new posting). Each additional conversion is linear in history; importing N conversions entails quadratic rebuilding work. Track the affected old/new date and currency pair; preserve full rebuilding as a repair path. Filed as 9G (completed; see Fix follow-up).
4. **Low: eight unreferenced helpers are cleanup candidates.** A Python AST definition scan followed by `rg` across `lightning`, `tests`, `tools`, and `android` found only their definitions: `cash_owners_for_account`, `AssetService.root_of`, `cash_currencies`, `parent_path`, `class_targets`, `first_holding_date`, `last_payment_date`, `question_of`. No deletion was made: dynamic access and external consumers need checking first. Filed as 9H (completed; see Fix follow-up).

## Measurements

Temporary plaintext SQLite databases only; no personal profile opened. `load_mohab_2026` produced 357 transactions on the host date. Added 3,000 balanced transfers using `_add_synthetic_transfers` from `tests/test_reporting_performance.py`. Each read ran in a fresh `request_cache` scope; SQL statement counts came from SQLite's trace callback. Timings are single local observations, not ordinary-Windows/SQLCipher benchmarks.

| Service call | Transactions | Milliseconds | SQL statements |
|---|---:|---:|---:|
| `reporting.net_worth('2026-10-21')` | 357 | 2.78 | 40 |
| Same | 3,357 | 6.65 | 40 |
| `reporting.monthly_trend('2026-10', 10)` | 357 | 2.48 | 2 |
| Same | 3,357 | 2.71 | 2 |

These figures support keeping live SQL reporting for now. They do not establish whole-page latency, import throughput, or scaling with thousands of distinct assets/accounts. The added transfers test row growth with fixed account/asset cardinality.

## Structure and existing loose ends

- Keep the ledger/plan/report separation, integer money storage, explicit transactions/savepoints, and request-only memoization. The memo disables itself in transactions and invalidates on writes; these are useful foundations.
- `ReevaluationService._source_hash` reads and hashes cumulative activity, prices, and FX for each checkpoint. This is a scaling review target, not a newly measured defect. Existing [2E](../issues/2-safe-for-real-money/2E-engine-input-checks.md), point 8, tracks revaluation history churn. Avoid changing it without testing unchanged checkpoints, backdated edits, sales, voids and restores.
- Investment event branching already has a consolidation proposal, [5A](../issues/5-investments/5A-one-table-of-investment-events.md). Use that when adding event types; there is no evidence here that a broad rewrite is needed now.
- Restore/reboot acceptance remains unfinished: [2A](../issues/2-safe-for-real-money/2A-restore-safety.md), [2B](../issues/2-safe-for-real-money/2B-promotion-durability.md), [2C](../issues/2-safe-for-real-money/2C-ordinary-pc-acceptance.md). The stale checker flags two old claims about this work; age alone does not prove abandonment, and their authors' claims were preserved.
- Journal coverage and large imports remain unfinished under [4A](../issues/4-edit-journal-and-devices/4A-edit-journal.md). Claimed journal/restore implementation files were left untouched.

## Verification limits

`tools/stale_check.py` ran and reported two old claims. A fresh upstream fetch was blocked by sandbox networking; this review covers the available checkout. The default Python lacked pytest/Jinja; the workspace virtualenv could run the backend service probes. Dependency installation did not complete. The virtualenv page performance check reached its table header but returned no page measurements within a 30-second timeout, even with price fetching disabled. Do not interpret this as measured production page slowness. The pytest suite and import-linter were not run. No application behavior was changed.
