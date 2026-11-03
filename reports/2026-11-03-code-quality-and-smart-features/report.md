# Code audit: refactoring, loose ends and smart features

Date: 2026-11-03 · Author/reviewer: Codex
Repository: app · Reviewed commit: 89848dc0e4ce35bb18f72e861c7c620d8052fae4
Pillar: build · Related pillars: protect, capture, plan, own, everywhere

## Assessment

Lightning has a substantial foundation worth keeping: exact ledger amounts, explicit transactions, encrypted profiles, bounded authenticated loopback requests, and useful planning and import services. The next investment should be reliability at workflow boundaries and completing existing intelligence before adding another large subsystem.

This review reproduced two defects in isolated execution of current code, demonstrated one numerical limitation, and identified concrete refactoring and validation work. Several important gaps already have owners and plan items; they are linked below rather than presented as new discoveries. This is a targeted source audit, not a certification that every feature or device works.

**Recommended order:** resolve success-before-settlement and the search race; finish restore/device acceptance and the legacy entrypoint decision; make service dependencies explicit and move remaining route calculations/writes into services; ship the existing smart inbox; then add scenario planning and bill-change detection.

## Scope and method

The reviewed main snapshot declares version **1.5.4**. The complete repository tree contains **285 Python files under `lightning/`** and **287 `tests/test_*.py` files**. These counts describe the inventory, not executed coverage.

Inspected selected code in money/ledger handling, database transactions and backups, transaction submission and edits, bank/SMS import, planning and forecasting, investment returns, profile/session/restore handling, local HTTP security, pairing transport, AI exports, phone navigation/search, architecture tests and PR checks. Read the plan and selected existing findings to separate unfinished work from new observations. The website, full Android native implementation and live cloud relay were outside this audit.

Source was fetched through the GitHub connector at the pinned commit because Git cloning failed with an unreachable environment proxy. The local directory is a **partial source snapshot**, not a complete Git checkout. Python 3.12.14 and Node 24.22.1 were available; pytest was not installed. Evidence scripts use dummy values and standard libraries only. No application behavior was changed.

## New findings

| ID | Priority / classification | Finding | Evidence and follow-up |
| --- | --- | --- | --- |
| F1 | P1 / medium bug | Payment matching happens after the HTTP success response has completed. A settlement error cannot be reported correctly to the saving user. | [ui/web.py:545–571](https://github.com/LightningEg/Lightning/blob/89848dc0e4ce35bb18f72e861c7c620d8052fae4/lightning/ui/web.py#L545); isolated fault probe; [BT-2AE](../../issues/2-safe-for-real-money/2AE-settlement-before-success.md) |
| F2 | P2 / medium bug | Phone live search can replace newer results and the URL with an older response body. | [ui/static/phone-capture.js:142–159](https://github.com/LightningEg/Lightning/blob/89848dc0e4ce35bb18f72e861c7c620d8052fae4/lightning/ui/static/phone-capture.js#L142); controlled asynchronous reproduction; [BT-3AP](../../issues/3-polish-and-arabic/3AP-live-search-response-race.md) |
| F3 | P3 / numerical design limitation | XIRR does not distinguish an ambiguous multi-root return from an unavailable return. Its coarse scan can miss two roots within one interval. | [investments/xirr.py:36–54](https://github.com/LightningEg/Lightning/blob/89848dc0e4ce35bb18f72e861c7c620d8052fae4/lightning/investments/xirr.py#L36); independently checked example; [IT-5M](../../issues/5-investments/5M-xirr-ambiguous-results.md) |
| F4 | P2 / validation improvement | Main PR tests use Python 3.13 although the package supports Python 3.11+. Selected phone-search tests verify generated HTML rather than response-order behavior. | [.github/workflows/pr-checks.yml:24–30](https://github.com/LightningEg/Lightning/blob/89848dc0e4ce35bb18f72e861c7c620d8052fae4/.github/workflows/pr-checks.yml#L24), `pyproject.toml`, `tests/test_phone_search.py`; [IT-1P](../../issues/1-easy-to-contribute/1P-supported-runtime-contract-checks.md), BT-3AP |

### F1 — success is sent before settlement finishes

`RequestCache.__call__` forwards response-start and body messages immediately, awaits the route, and only then calls `current.planning.match_payments(today())`. Matching can write settlement links in its own database transaction ([planning/service.py:249–283](https://github.com/LightningEg/Lightning/blob/89848dc0e4ce35bb18f72e861c7c620d8052fae4/lightning/planning/service.py#L249)). A shared undo label is not an atomic database transaction across those operations.

The probe executes the real middleware class with a fake route and an injected settlement failure. Observed order:

```
primary write committed (simulated)
http.response.start 303
http.response.body complete
settlement attempted
simulated storage failure
```

**Impact:** under a matching/storage failure, a saved transaction may be acknowledged while its bill link remains unfinished. Planning may continue treating the bill as unpaid until matching succeeds. The probe proves response ordering; it does not demonstrate real-disk data loss or quantify how often the fault occurs.

**Recommendation:** put the primary write and required matching in an explicit workflow boundary. Where atomic completion is required, commit them together before success. Where matching is intentionally deferred, record durable pending work and communicate that status. Simply catching and hiding the exception would preserve the misleading success. Add an integrated route test with an injected settlement failure, plus retry, undo and journal-mode cases.

### F2 — live search checks freshness too early

The serial comparison runs after `fetch()` returns headers but **before** `await response.text()`. If the old body is delayed, a newer search can finish first; the old continuation then overwrites both results and `history.replaceState`. The probe executes the actual live-search initializer with controlled fetch promises:

```
field=new; results=OLD RESULTS; URL=/search?q=old
```

**Recommendation:** read the body first, then verify the request generation and current mounted form before changing DOM or history. Invalidate pending work immediately on input and when navigation replaces the page; optionally abort previous requests. Test reversed header/body timing, clearing the input and leaving the search page. The existing server-rendered search tests are useful but do not exercise this race.

### F3 — make annualized-return uncertainty explicit

For yearly cash flows **−100, +230, −132.16**, NPV is zero at both **12% and 18%**. The solver returns `None`: the two roots are inside the same 10%–30% scan interval, whose endpoints have the same sign. This is consistent with its documented bracketing implementation, so it is a limitation rather than a newly established accounting error.

**Recommendation:** define the product policy for non-conventional flows and return a result with a reason such as unavailable, ambiguous, or converged. Do not silently pick one root. Add known-root, no-root and multiple-root fixtures and require a residual tolerance for reported results. Keep numerical approximation isolated from exact ledger arithmetic. The five existing XIRR test functions passed when invoked directly; this was not a pytest run.

## Refactoring priorities

Line counts below were measured from the snapshot. Size alone is not a bug; these candidates combine size with mixed responsibilities or boundaries the current contracts cannot express.

| Order | Area | Concrete change | Benefit / acceptance | Existing follow-up |
| --- | --- | --- | --- | --- |
| 1 | Runtime composition | `runtime/app.py` has 1,021 lines; `profile_app` spans 829. Extract profile, recovery/restore and device route registration around one explicit session interface. | Easier lifecycle review; same authentication, lock, borrowed-profile and restore behavior. Coordinate with active claims. | [IT-9K](../../issues/9-later/9K-layers-and-copies.md) |
| 2 | Hidden dependency direction | [bootstrap.py:232–244](https://github.com/LightningEg/Lightning/blob/89848dc0e4ce35bb18f72e861c7c620d8052fae4/lightning/bootstrap.py#L232) assigns planning/forecast callbacks onto budget/forecaster instances after construction. | Pass typed inputs or narrow protocols explicitly; fail construction when required collaborators are missing. Import checks alone cannot see runtime callback direction. | [IT-1G](../../issues/1-easy-to-contribute/1G-complete-backend-architecture-contracts.md), IT-9K |
| 3 | Route/service boundary | [ui/routes/accounts.py:338](https://github.com/LightningEg/Lightning/blob/89848dc0e4ce35bb18f72e861c7c620d8052fae4/lightning/ui/routes/accounts.py#L338) still writes through `c.reporting.other_asset_values.save`. | Move mutation to the account service, enforce it with a behavior/architecture test; preserve valuation and undo behavior. The old plan points at line 251, now stale. | [IT-9J](../../issues/9-later/9J-routes-compute-figures.md) |
| 4 | Transaction responsibilities | `transactions/service.py` has 1,381 lines covering posting, custody, edits, search, idempotency and revision checks. | Keep one public facade; extract cohesive validation, search and submission collaborators. Preserve transaction scopes and single ownership of ledger writes. | IT-9K (audit extension) |
| 5 | Import workflow | `bank_imports.py` has 962 lines; `_post_import_row` 119, `confirm` 101, `preview` 98. | Separate parsing/normalization, proposal generation and posting orchestration. Use explicit review DTOs rather than increasingly large dictionaries. Preserve all-or-nothing confirmation, duplicate handling and fee splits. | IT-9K (audit extension) |
| 6 | Financial read models | `reporting/service.py` has 1,037 lines; `register.page` remains 144 after its recent extraction. | Continue moving reusable figures to services and give pages small typed view models. Avoid changing money rules during structural work. | IT-9J, IT-9K |
| 7 | Shared policies | Existing plan records three balance-floor implementations and a remaining duplicate pairing client. | Consolidate policies behind contract tests after active restore/journal work clears. Keep caller-specific validation messages. | IT-9K, [IT-4K](../../issues/4-edit-journal-and-devices/4K-journal-code-tidy.md) |

Do these as narrow extractions with invariant tests, not a rewrite. There is no evidence here that microservices, a new database or moving financial calculations into JavaScript would improve Lightning. Retain the Python services, integer storage and local-first model. Performance changes should follow measured query/time budgets; [IT-9A](../../issues/9-later/9A-stored-month-end-figures.md) already gates caching on actual scale/latency evidence.

## Known loose ends that still matter

These are **existing tracked risks or acceptance gaps**, not failures newly reproduced in this session.

| Priority | Gap | Why it matters / closure evidence | Follow-up |
| --- | --- | --- | --- |
| P1 | Restore crash consistency and ordinary-device recovery | Backups need a demonstrated recovery path across interrupted promotion, reboot and native file selection. Preserve the active ownership of this work. | [IT-2A](../../issues/2-safe-for-real-money/2A-restore-safety.md), [IT-2C](../../issues/2-safe-for-real-money/2C-ordinary-pc-acceptance.md) |
| P1 | Legacy launch remains plaintext | [main.py](https://github.com/LightningEg/Lightning/blob/89848dc0e4ce35bb18f72e861c7c620d8052fae4/lightning/main.py#L80) sends bare `python -m lightning` through `build(args.db)`; protected profiles require `--profiles`. Make the supported default explicit and provide a deliberate legacy/migration path. This does not mean the packaged protected app falls back to plaintext. | [OW-2AB](../../issues/2-safe-for-real-money/2AB-stale-code.md) |
| P1 | Device-sync cutover and recovery acceptance | Protocol tests alone cannot establish ordinary PC/phone behavior under loss, offline edits, rejoin and authority changes. Require the existing end-to-end evidence before cutover. | [NF-4A](../../issues/4-edit-journal-and-devices/4A-edit-journal.md), [NF-4B](../../issues/4-edit-journal-and-devices/4B-multiple-devices.md) |
| P2 | Native dependencies and packaging need coordinated refresh | Main app checks do not substitute for matching native wheels and lockfiles on Windows/Android. No specific dependency vulnerability was independently established here. | [IT-1H](../../issues/1-easy-to-contribute/1H-coordinate-packaged-dependency-refresh.md) |
| P2 | Phone import/export acceptance and market publication | Existing plan still holds phone file acceptance and missing/stale shared-price publication. Recheck actual artifacts and freshness; source review cannot establish current download/service status. | [BT-2F](../../issues/2-safe-for-real-money/2F-android-downloads-files-links.md), [BT-6C](../../issues/6-market-data/6C-shared-prices-not-published.md) |
| P2 | Investment event and lot model unfinished | Finish event wrappers and form contracts before adding lot-dependent return/corporate-action features. | [NF-5A](../../issues/5-investments/5A-one-table-of-investment-events.md), [NF-5B](../../issues/5-investments/5B-cost-per-purchase-lots.md) |

## Smart features worth adding

The best first features can run locally and explain their suggestions. The app already has rules, recurring detection, a review inbox, forecasts, salary-related suggestions, and AI context exports. Those should not be marketed as wholly new capabilities.

| Rank | Feature | Current foundation and proposed increment | Effort / measurable acceptance | Follow-up |
| --- | --- | --- | --- | --- |
| 1 | One actionable smart inbox | Complete the existing Needs you plan: surface recurring candidates, rule offers, reserve refills and related payments in one place. Show why each item appears; offer confirm, dismiss and snooze. | M–L across existing steps. A user accepts a useful suggestion from Home without hunting through tabs; dismissed suggestions stay dismissed. | [NF-7L](../../issues/7-planning-import-and-search/7L-needs-you-as-the-smart-inbox.md) |
| 2 | Read-only “what if?” scenarios | Extend the existing cash forecast with salary delayed 7 days, a large purchase, or a bill increase. Compare baseline and scenario lowest balance, shortfall date and safe-to-spend with visible assumptions. | L. Same inputs reproduce the same result; preview performs zero ledger/plan writes; thin history is labelled. | [NF-7X](../../issues/7-planning-import-and-search/7X-scenario-and-bill-intelligence.md), steps 7X1–7X3 |
| 3 | Bill-change and duplicate-charge alerts | Extend recurring history and import duplicate checks with explainable bill drift or repeated-charge candidates. Start with robust local thresholds and merchant/account/currency identity. | L. Known legitimate repeats and variable utilities are tested; no automatic deletion or financial posting; false-positive rate measured on labelled dummy fixtures. | NF-7X, steps 7X4–7X5 |
| 4 | Explainable financial-data freshness | Expand existing price/source metadata and explanations into “what this number depends on”: stale prices/FX, last reconciliation, pending device edits, and unconfirmed receipts, with links to resolve each. | M. Every warning has a dated source and action; no unsupported numeric confidence score; no duplicate headline metric on another page. | [NF-7Y](../../issues/7-planning-import-and-search/7Y-financial-data-freshness.md) |
| 5 | Salary-day allocation preview | Complete the existing salary cascade: suggest bills, reserves and flexible spending from actual funds and obligations; let the user compare and confirm. | Existing L steps. Allocations cannot exceed available funds, reserve-to-bill links avoid double counting, and plans never move money. | [NF-7T](../../issues/7-planning-import-and-search/7T-link-the-sections.md) |
| 6 | Statement onboarding that learns mappings | Build the already-planned PDF/Excel input and app-migration presets on the reviewed import pipeline. Reuse merchant rules and remembered column mappings; present uncertain fields for confirmation. | Existing L steps. No formula/macro execution, bounded parsing, repeated imports remain harmless, and preview totals reconcile. | [NF-7B](../../issues/7-planning-import-and-search/7B-pdf-and-excel-statements.md), [NF-7C](../../issues/7-planning-import-and-search/7C-move-in-from-other-apps.md) |

The feature proposals are options for prioritization, not approval to implement them. Scenario and anomaly logic should stay in Python services. If AI is added later, let it explain verified figures and propose reviewable actions; retain explicit consent before exporting financial context or changing records. The current `workflows/ask_ai.py` already excludes notes/memos and supports hiding names, which is a good starting point.

## Validation, strengths and limits

Executed:

- `python reports/2026-11-03-code-quality-and-smart-features/evidence/reproduce.py`: reproduced F1's response order; verified F3's two roots; directly executed all five existing XIRR test functions successfully.
- `node reports/2026-11-03-code-quality-and-smart-features/evidence/search-race.cjs`: reproduced F2 using the actual live-search initializer and deterministic delayed bodies.
- `python tools/issues.py --check` and `python tools/status.py --check`: passed (the issue tool reported existing claim warnings). Source/AST measurements for the refactoring candidates. [Captured probe results](evidence/results.txt) and [source manifest](evidence/source-manifest.json) make the limited scope explicit.

Safeguards observed in source, without claiming a full runtime security test:

- Money parsing rejects floats and non-finite values; stored ledger amounts use scaled integers.
- Database writes support nested savepoints; failed import rows roll back the whole confirmation.
- Transaction forms have submission hashes and revision checks. Keep these protections through refactoring.
- Protected profile HTTP uses a one-use launch code, random cookie name/token, exact host/origin checks, CSP and bounded bodies. The database raises when SQLCipher is unavailable instead of falling back to plaintext.
- Key wrapping uses Argon2id and authenticated AES-GCM with metadata validation. No cryptographic certification or penetration test was performed.
- PR checks include pinned actions, hash-locked dependencies, import contracts, linting and dependency review. Their presence is not evidence that a particular run passed.

**Not run:** full pytest suite, application crawl, real database fault injection, browser layout/accessibility checks, packaged Windows/WebView2 or Android tests, physical reboot/recovery drills, live price/cloud checks, dependency vulnerability scan, or performance benchmarks. The search and middleware probes use controlled doubles, not full-device reproductions. No claim of complete coverage, absence of security vulnerabilities, or measured speedup is made.

## Suggested delivery sequence

1. **Reliability:** BT-2AE and BT-3AP; add the targeted regression tests. Keep the active restore and journal owners' work intact.
2. **Close acceptance gaps:** IT-2A/IT-2C, NF-4A/NF-4B, the legacy entrypoint decision and native dependency refresh.
3. **Reduce coupling:** explicit collaborators, the account valuation write boundary, then one runtime/import/transaction extraction at a time. Add minimum-supported-runtime checks.
4. **Deliver intelligence:** finish NF-7L first, then choose the scenario or bill-change slice of NF-7X; add NF-7Y where stale inputs can mislead decisions.

Use each item's acceptance criteria to size implementation after design review; these are relative effort estimates, not delivery-date promises.
