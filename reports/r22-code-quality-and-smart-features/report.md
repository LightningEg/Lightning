# Code audit: refactoring, loose ends and smart features

Code: r22 · Historical ID: code-quality-smart-features

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
| F1 | P1 / medium bug | Payment matching happens after the HTTP success response has completed. A settlement error cannot be reported correctly to the saving user. | [ui/web.py:545–571](https://github.com/LightningEg/Lightning/blob/89848dc0e4ce35bb18f72e861c7c620d8052fae4/lightning/ui/web.py#L545); isolated fault probe; [BT-2AE](https://github.com/LightningEg/Lightning/blob/3d36077d19370fa7f732549419eee7c0457b020c/issues/2-safe-for-real-money/2AE-settlement-before-success.md) |
| F2 | P2 / medium bug | Phone live search can replace newer results and the URL with an older response body. | [ui/static/phone-capture.js:142–159](https://github.com/LightningEg/Lightning/blob/89848dc0e4ce35bb18f72e861c7c620d8052fae4/lightning/ui/static/phone-capture.js#L142); controlled asynchronous reproduction; BT-3AP, finished 2026-11-04: `lightning/ui/static/phone-capture.js`, `tests/test_phone_live_search_browser.py` |
| F3 | P3 / numerical design limitation | XIRR does not distinguish an ambiguous multi-root return from an unavailable return. Its coarse scan can miss two roots within one interval. | [investments/xirr.py:36–54](https://github.com/LightningEg/Lightning/blob/89848dc0e4ce35bb18f72e861c7c620d8052fae4/lightning/investments/xirr.py#L36); independently checked example; IT-5M (closed; [snapshot](https://github.com/LightningEg/Lightning/blob/d9d5c8e4c2aed9e8476a1b1ab51b2706445ad90c/issues/5-investments/5M-xirr-ambiguous-results.md); [regressions](../../tests/test_xirr_results.py)) |
| F4 | P2 / validation improvement | Main PR tests use Python 3.13 although the package supports Python 3.11+. Selected phone-search tests verify generated HTML rather than response-order behavior. | [.github/workflows/pr-checks.yml:24–30](https://github.com/LightningEg/Lightning/blob/89848dc0e4ce35bb18f72e861c7c620d8052fae4/.github/workflows/pr-checks.yml#L24), `pyproject.toml`, `tests/test_phone_search.py`; IT-1P (closed; [snapshot](https://github.com/LightningEg/Lightning/blob/3dc54ae303746041b9d02e6c63309d9590d1afa5/issues/1-easy-to-contribute/1P-supported-runtime-contract-checks.md); [minimum-runtime contracts](../../tests/runtime_contracts/test_finance.py)), BT-3AP |

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
| 2 | Hidden dependency direction | [bootstrap.py:232–244](https://github.com/LightningEg/Lightning/blob/89848dc0e4ce35bb18f72e861c7c620d8052fae4/lightning/bootstrap.py#L232) assigns planning/forecast callbacks onto budget/forecaster instances after construction. | Pass typed inputs or narrow protocols explicitly; fail construction when required collaborators are missing. Import checks alone cannot see runtime callback direction. | IT-1G (finished 2026-11-04: `pyproject.toml` sync contracts, `tests/test_architecture.py`), IT-9K |
| 3 | Route/service boundary | [ui/routes/accounts.py:338](https://github.com/LightningEg/Lightning/blob/89848dc0e4ce35bb18f72e861c7c620d8052fae4/lightning/ui/routes/accounts.py#L338) still writes through `c.reporting.other_asset_values.save`. | Move mutation to the account service, enforce it with a behavior/architecture test; preserve valuation and undo behavior. The old plan points at line 251, now stale. | IT-9J (closed; [snapshot](https://github.com/LightningEg/Lightning/blob/3dc54ae303746041b9d02e6c63309d9590d1afa5/issues/9-later/9J-routes-compute-figures.md); [investment read model](../../lightning/planning/investment_figures.py)) |
| 4 | Transaction responsibilities | `transactions/service.py` has 1,381 lines covering posting, custody, edits, search, idempotency and revision checks. | Keep one public facade; extract cohesive validation, search and submission collaborators. Preserve transaction scopes and single ownership of ledger writes. | IT-9K (audit extension) |
| 5 | Import workflow | `bank_imports.py` has 962 lines; `_post_import_row` 119, `confirm` 101, `preview` 98. | Separate parsing/normalization, proposal generation and posting orchestration. Use explicit review DTOs rather than increasingly large dictionaries. Preserve all-or-nothing confirmation, duplicate handling and fee splits. | IT-9K (audit extension) |
| 6 | Financial read models | `reporting/service.py` has 1,037 lines; `register.page` remains 144 after its recent extraction. | Continue moving reusable figures to services and give pages small typed view models. Avoid changing money rules during structural work. | IT-9J, IT-9K |
| 7 | Shared policies | Existing plan records three balance-floor implementations and a remaining duplicate pairing client. | Consolidate policies behind contract tests after active restore/journal work clears. Keep caller-specific validation messages. | IT-9K, IT-4K (finished 2026-11-02: `lightning/runtime/journal_pairing_driver.py`, `tests/test_one_pairing_driver.py`) |

Do these as narrow extractions with invariant tests, not a rewrite. There is no evidence here that microservices, a new database or moving financial calculations into JavaScript would improve Lightning. Retain the Python services, integer storage and local-first model. Performance changes should follow measured query/time budgets; [IT-9A](../../issues/9-later/9A-stored-month-end-figures.md) already gates caching on actual scale/latency evidence.

## Known loose ends that still matter

These are **existing tracked risks or acceptance gaps**, not failures newly reproduced in this session.

| Priority | Gap | Why it matters / closure evidence | Follow-up |
| --- | --- | --- | --- |
| P1 | Restore crash consistency and ordinary-device recovery | Backups need a demonstrated recovery path across interrupted promotion, reboot and native file selection. Preserve the active ownership of this work. | [IT-2A](../../issues/2-safe-for-real-money/2A-restore-safety.md), [IT-2C](../../issues/2-safe-for-real-money/2C-ordinary-pc-acceptance.md) |
| P1 | Legacy launch remains plaintext | [main.py](https://github.com/LightningEg/Lightning/blob/89848dc0e4ce35bb18f72e861c7c620d8052fae4/lightning/main.py#L80) sends bare `python -m lightning` through `build(args.db)`; protected profiles require `--profiles`. Make the supported default explicit and provide a deliberate legacy/migration path. This does not mean the packaged protected app falls back to plaintext. | OW-2AB (finished: [launcher and thread-ownership regressions](../../tests/test_legacy_launcher.py)); legacy import remains IT-2C |
| P1 | Device-sync cutover and recovery acceptance | Protocol tests alone cannot establish ordinary PC/phone behavior under loss, offline edits, rejoin and authority changes. Require the existing end-to-end evidence before cutover. | [NF-4A](../../issues/4-edit-journal-and-devices/4A-edit-journal.md), [NF-4B](../../issues/4-edit-journal-and-devices/4B-multiple-devices.md) |
| P2 | Native dependencies and packaging need coordinated refresh | Main app checks do not substitute for matching native wheels and lockfiles on Windows/Android. No specific dependency vulnerability was independently established here. | [IT-1H](../../issues/1-easy-to-contribute/1H-coordinate-packaged-dependency-refresh.md) |
| P2 | Phone import/export acceptance and market publication | Existing plan still holds phone file acceptance and missing/stale shared-price publication. Recheck actual artifacts and freshness; source review cannot establish current download/service status. | BT-2F (finished 2026-11-04: `lightning/runtime/phone_files.py`, `tests/test_phone_downloads.py`, `tests/test_android_shell.py`) | BT-6C, finished 2026-11-04 (commit `d1cd104` and the close-out PR #295): the exchange-rate pack published again on 2026-11-04 |
| P2 | Investment event and lot model unfinished | Finish event wrappers and form contracts before adding lot-dependent return/corporate-action features. | NF-5A (built: `lightning/investments/events.py`, `tests/test_investment_events_table.py`, `tests/test_return_of_capital.py`), NF-5B (built 2026-11-04: `lightning/investments/lots.py`, `tests/test_lots.py`, `tests/test_cost_method.py`) |

## Smart features worth adding

The best first features can run locally and explain their suggestions. The app already has rules, recurring detection, a review inbox, forecasts, salary-related suggestions, and AI context exports. Those should not be marketed as wholly new capabilities.

| Rank | Feature | Current foundation and proposed increment | Effort / measurable acceptance | Follow-up |
| --- | --- | --- | --- | --- |
| 1 | One actionable smart inbox | Complete the existing Needs you plan: surface recurring candidates, rule offers, reserve refills and related payments in one place. Show why each item appears; offer confirm, dismiss and snooze. | M–L across existing steps. A user accepts a useful suggestion from Home without hunting through tabs; dismissed suggestions stay dismissed. | [NF-7L](https://github.com/LightningEg/Lightning/blob/6a88ed6c8079747595a91f5918741a0807de5b84/issues/7-planning-import-and-search/7L-needs-you-as-the-smart-inbox.md) |
| 2 | Read-only “what if?” scenarios | Extend the existing cash forecast with salary delayed 7 days, a large purchase, or a bill increase. Compare baseline and scenario lowest balance, shortfall date and safe-to-spend with visible assumptions. | L. Same inputs reproduce the same result; preview performs zero ledger/plan writes; thin history is labelled. | [NF-7X](../../tests/test_scenarios_and_bill_alerts.py), steps 7X1–7X3 |
| 3 | Bill-change and duplicate-charge alerts | Extend recurring history and import duplicate checks with explainable bill drift or repeated-charge candidates. Start with robust local thresholds and merchant/account/currency identity. | L. Known legitimate repeats and variable utilities are tested; no automatic deletion or financial posting; false-positive rate measured on labelled dummy fixtures. | NF-7X, steps 7X4–7X5 |
| 4 | Explainable financial-data freshness | Expand existing price/source metadata and explanations into “what this number depends on”: stale prices/FX, last reconciliation, pending device edits, and unconfirmed receipts, with links to resolve each. | M. Every warning has a dated source and action; no unsupported numeric confidence score; no duplicate headline metric on another page. | [NF-7Y](../../tests/test_freshness.py) |
| 5 | Salary-day allocation preview | Complete the existing salary cascade: suggest bills, reserves and flexible spending from actual funds and obligations; let the user compare and confirm. | Existing L steps. Allocations cannot exceed available funds, reserve-to-bill links avoid double counting, and plans never move money. | [NF-7T](../../tests/test_salary_day_review.py) |
| 6 | Statement onboarding that learns mappings | Build the already-planned PDF/Excel input and app-migration presets on the reviewed import pipeline. Reuse merchant rules and remembered column mappings; present uncertain fields for confirmation. | Existing L steps. No formula/macro execution, bounded parsing, repeated imports remain harmless, and preview totals reconcile. | [NF-7B](../../tests/test_mohab_statements.py), [NF-7C](../../issues/7-planning-import-and-search/7C-move-in-from-other-apps.md) |

The feature proposals are options for prioritization, not approval to implement them. Scenario and anomaly logic should stay in Python services. If AI is added later, let it explain verified figures and propose reviewable actions; retain explicit consent before exporting financial context or changing records. The current `workflows/ask_ai.py` already excludes notes/memos and supports hiding names, which is a good starting point.

## Validation, strengths and limits

Executed:

- `python reports/r22-code-quality-and-smart-features/evidence/reproduce.py`: reproduced F1's response order; verified F3's two roots; directly executed all five existing XIRR test functions successfully.
- `node reports/r22-code-quality-and-smart-features/evidence/search-race.cjs`: reproduced F2 using the actual live-search initializer and deterministic delayed bodies.
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

## Follow-up · 2026-11-03: first fixes

The response boundary now runs required payment matching before forwarding success headers, within the same undo action. A settlement exception therefore cannot follow an acknowledged success. The primary route write is still committed independently: this change does not promise rollback of an already saved transaction, and BT-2AE remains open for integrated fault/retry/undo validation and the broader workflow decision.

Phone search now reads response bodies before checking the generation, invalidates outstanding generations immediately on input, and rejects updates to detached forms. BT-3AP's response-order defect is fixed; further real-browser acceptance remains useful. Regression coverage is in `tests/test_save_response_boundary.py` and `tests/phone-search-race.test.cjs`. Four test functions passed by direct execution locally; full application validation is delegated to the PR checks because this workspace still lacks pytest and a full checkout.

## Follow-up · 2026-11-03: atomic entry writes

Transaction entry and edit workflows now commit their form retry markers and automatic payment matching together through `workflows/save.settled_write`. Matching failure rolls that scope back; a resend can safely retry the same form. A request-local completion flag prevents response middleware from matching again after commit. No database transaction spans request parsing or another await. Journal commands retain their own settlement behavior. Remaining write routes keep the earlier response-boundary fallback and remain in BT-2AE's scope.

## Follow-up · 2026-11-03: recurring detection (NF-7L3)

Fixed monthly subscriptions can now be suggested across spending categories, variable utilities use observed matching tolerances, Track starts after the latest recorded payment, and dismissed suggestions can be restored on PC and phone. The detector excludes frequent/irregular purchases, already tracked counterparties and investment income, keeps foreign amounts in their account currency, and never posts money. Regression coverage: [recurring detection tests](../../tests/test_recurring_detection.py).


## Follow-up · 2026-11-03: reimbursement pairing and same-category repayments

Needs you and Reimbursements suggest receipt pairs in the original expense category. New pairs prefill a claim; existing claims can confirm partial receipts, with ambiguity and changed suggestions kept for review. A shortcut records actual money back in the same category, so spending falls without inflating income; linking never reposts cash. [Regression tests](../../tests/test_reimbursement_pairing.py) cover cash/report invariants, replay, duplicates, undo, ownership, currency and PC/phone confirmation. NF-7L4's import settlement feedback and certificate return navigation remain open.

Dummy-data number check, 2026-09-01 through 2026-10-06:

| Invariant | Expected | Found | Result |
| --- | --- | --- | --- |
| Record 600 back against a 1,200 expense in its original category | Money in 0; net spending 600 | Money in 0; net spending 600 | Pass |
| Confirm the existing receipt link | Cash and ledger rows unchanged | Cash and ledger rows unchanged | Pass |
| Partial reimbursement claim | Received 600; outstanding 600 | Received 600; outstanding 600 | Pass |
| Duplicate receipt entry or pair confirmation | One cash receipt and one link | One cash receipt and one link | Pass |

Exercised Money in entry, suggested-pair claim creation, receipt confirmation, unlink/undo, stale receipt edits and two-device command replay. The same-category flow tests also cover Arabic and PC/phone templates. Native packaging was not exercised.

## Follow-up · 2026-11-04: import settlement feedback and certificate navigation

NF-7L4 is complete. Import confirmation now matches payments inside its atomic save before rendering success and names the bills paid by its posted or linked entries. Ambiguous matches are omitted; unrelated matches are not attributed to the import. Settlement failure rolls back the batch and ledger writes, allowing a safe retry. Certificate Match all defaults back to Needs you and preserves an explicit inbox return path. [Import regressions](../../tests/test_import_settlement_feedback.py) cover English/Arabic PC/phone feedback, existing-entry links, ambiguity, injected validation/storage failures, retry and undo; [certificate navigation](../../tests/test_cd_interest_match.py) is checked over HTTP. The remaining financial-health bands in NF-7L2 and the other write routes in BT-2AE remain open.

## Follow-up · 2026-11-04: complete financial-health inbox alerts

NF-7L2 and the smart inbox (NF-7L) are complete. Needs you now uses the same alert bands as Health for debt, fixed costs, loan payments and savings, reusing existing savings/plan reminders instead of duplicating them. Unknown and Watch figures stay quiet. Alerts link to their Health row and support the existing review, snooze and restore controls without posting money. Current comparisons are shared separately from the six-month charts. [Health inbox regressions](../../tests/test_health_inbox_alerts.py) cover numerical ratios, read-only behavior, cache invalidation, stable review identities, savings deduplication and English/Arabic PC/phone navigation.

## Follow-up · 2026-11-04: complete atomic write routes

BT-2AE is complete. Remaining transaction, plan, import, investment and supporting settings writes now commit required matching within explicit synchronous scopes, preserving retry tokens, revision checks, Undo labels and journal authority. Related register/popup follow-up reads and metadata finish before commit; failed profile-currency changes restore both stored and live service values. The response middleware no longer starts matching after a route has finished, so error redirects cannot retry a failed settlement and read-only POSTs do not start unrelated financial work. Network fetches finish before price-save scopes. Dedicated file/recovery flows and visibility-only actions retain their existing completion boundaries. [Route-boundary contracts](../../tests/test_atomic_write_routes.py), [integrated failures](../../tests/test_atomic_write_failures.py) and [response-order regressions](../../tests/test_save_response_boundary.py) cover no-await scopes, real settlement rollback, retry/duplicate markers, currency state and home/replica command behavior. The 160 targeted financial and journal checks passed; final full-suite validation is recorded in the PR.

## Follow-up · 2026-11-04: explicit annualized-return uncertainty

IT-5M is complete. A unique rate is shown only after an independent Decimal NPV residual check (relative tolerance 1e-10 of gross discounted flows). Non-conventional histories with multiple roots are explicitly ambiguous; absent roots, missing valuations, numerical instability and calculation limits have separate unavailable reasons. The solver partitions the log-rate NPV at derivative roots instead of relying on a coarse scan. Its work is bounded and a near-stationary root remains unavailable. The legacy `xirr` API returns a number only for a unique verified result. Under 365 days the existing plain-return policy is unchanged. PC and phone explain both ambiguous and unavailable results in English and Arabic.

Dummy-data number audit (ACT/365; holding at 2025-12-31, bought 2024-01-01, sold 2024-12-31, repurchased 2025-12-31):

| Invariant | Expected | Found | Result |
| --- | --- | --- | --- |
| Yearly flows −100, +230, −132.16 | Roots 12% and 18%; no selected rate | Both independent NPV residuals below 1e-50; ambiguous, no rate | Pass |
| Yearly flows −100, +50, −100 | No real rate | Unavailable, no_root | Pass |
| Non-conventional unique root; amount scales 1e-6, 1, 1e12 | 25%, residual within 1e-10 of gross flows | Same rate within tolerance; independent Decimal check passes | Pass |
| Leap-year two-flow return | ACT/365 over 366 days | Decimal power agrees | Pass |
| Repurchase cash | 1,000 − 100 + 230 − 232.16 = 897.84 EGP | 897.84 EGP | Pass |
| Holding value / cost / realized / unrealized | 100 / 232.16 / 130 / −132.16 EGP | Exact agreement | Pass |
| Return reads | No ledger changes | Full ledger snapshot unchanged | Pass |
| Less than a year | Actual gain / all purchases | Existing plain-return tests unchanged | Pass |

Evidence: [solver numerical regressions](../../tests/test_xirr_results.py), [real-ledger and PC/phone status checks](../../tests/test_return_uncertainty.py), [display policy](../../tests/test_display_returns.py). Paths exercised: buy, complete sale, repurchase and dated price; return calculation and portfolio/holding reads. This slice does not change financial write rules. Other write paths are covered by the separate atomic-save work, not this return audit. Arabic automated rendering checks cover the new explanations; a human Arabic reader should check their voice.

Validation: 253 affected investment, number-audit, Mohab and Arabic checks passed. Arabic portfolio and holding pages were inspected at 1280 and 390 pixels: the new reasons fit, RTL text is readable and neither page has horizontal overflow. Eleven explanatory strings were added; examples cover multiple roots, no roots, insufficient dated flows, instability and missing prices or FX. A human Arabic reader should review the voice.

## Follow-up · 2026-11-04: minimum supported Python

IT-1P is complete. PR checks now compile application and tool syntax and run dependency-free money, date, CSV, schedule and annualized-return contracts on Python 3.11; the full integration suite remains on Python 3.13. The small job uses only the standard library, so it needs no incompatible native wheels or dependency-lock changes. Local Python 3.11.17 passed the contracts and syntax compile. A dummy Python 3.12-only type alias was correctly rejected by the same compile gate. [Contributor checks](../../CONTRIBUTING.md#checks-before-merging) name the manual Windows/native, Android and recovery checks required by affected paths, and distinguish merge evidence from owner-controlled release actions. Existing deterministic delayed-response search tests remain part of the full suite; BT-3AP's separate input/clear/navigation browser acceptance remains open.

## Follow-up · 2026-11-04: investment class figures in a read model

IT-9J's remaining lifetime class-gain calculation is complete. `PositionService.investment_breakdown` returns a typed read model for class values, costs, lifetime gains, investment bases, weights, horizons and balance-only holdings. The investment route draws those rows instead of recomputing them. Foreign native costs and owned price/FX splits use the same arithmetic in that model. Grouping totals, currency breakdown and USD-lens calculations now live in `investments/views.py`; the route selects the view and supplies links. The newly merged per-purchase return-table arithmetic is also in that read-model module. The existing Holdings value denominator and owed gam'eya treatment are preserved; the period report's different value is not substituted.

The existing investment-view, demo and reporting checks cover all five regroupings, custody, FX, balance-only assets, cached/uncached HTML and query budgets. Additional dummy Mohab comparisons against the pre-extraction renderer cover English/Arabic PC/phone, all-time/month views and the USD currency view. No financial write rules or visible layout changed. Runtime, transaction and import-module splits remain under IT-9K.


Refactor number audit (dummy Mohab, 2026-10-02; baseline commit 3dc54ae3):

| Invariant | Expected | Found | Result |
| --- | --- | --- | --- |
| Class values, costs, gains and invested bases | Baseline renderer's unrounded Decimal values | Exact equality in all 12 comparisons | Pass |
| Holdings total and horizons | Baseline Position-based totals | Exact equality | Pass |
| Visible numbers and layout | Baseline HTML, ignoring per-render security tokens | Identical English/Arabic PC/phone pages | Pass |
| Page cache and query budget | Same cached/uncached HTML, existing SELECT limits | Existing performance contracts pass | Pass |

The 68 investment-view, demo and reporting checks and 128 Mohab/number-audit checks passed. Read paths checked: `/investments` all-time/month and USD-currency views. Fixture writes come from the existing dummy household; this extraction changes no write path. Broader runtime/import/transaction refactors are separate work.
## Follow-up · 2026-11-04: transaction responsibilities and shared balance checks

The IT-9K transaction slice is complete: the facade delegates balance/certificate validation, read-only search/capture suggestions and submission/revision handling to cohesive collaborators. Public entry points, canonical JSON hashes, tokens, audit behavior, save scopes, journal ownership and refusal messages retain their existing contracts. Owner/cash and historical holding checks now share an exact integer running-balance helper; each caller retains its former same-day order. The holdings repository streams rows and closes its cursor rather than buffering history.

Dummy-data number audit:

| Invariant | Expected | Found | Result |
| --- | --- | --- | --- |
| Historical floor, 100,000 integer-quantity rows | Old SQL window: −21,429,000,000 millionths on 2026-01-03 | Exact same quantity and date | Pass |
| Daily versus intraday policies | Net-daily lowest 3; row-order lowest −2 on the same fixture | Both preserved | Pass |
| Empty/positive floor, equal minima, voids, other accounts/assets | Former SQL result, including earliest equal minimum | Independent SQL-oracle fixtures agree | Pass |
| Existing deficit edits and owned/cash checks | Existing refusal and improvement rules | Transaction, cash and ownership regressions pass | Pass |
| Revisions, duplicate delivery, rollback/retry and journal commands | Existing snapshots, tokens and authority | Existing integration regressions pass | Pass |

The 192 affected transaction/ownership/cash/investment/search checks passed, plus 28 revision/entry/atomic checks and the journal/Mohab and resent-form/circle integrations. A seeded 500-row oracle and the 100,000-row probe check exactness. The latter sampled 540 ms wall/356 ms CPU for SQL versus 607 ms wall/407 ms CPU for the shared stream under concurrent validation, with 1,778 bytes peak Python allocations (SQLite excluded). No speed improvement is claimed. Evidence: [shared balance contracts](../../tests/test_balance_walk.py) and existing transaction, ownership, cash, revision and journal tests. Write paths exercised by those dummy fixtures include new entries, edits, ownership, investments, double submission, rollback/retry and journal saves; this slice introduces no new write path. Runtime and import-module separation remain open under IT-9K.

### Follow-up 2026-11-04: BT-3AP finished
Live search now stops the request in flight when the field changes, a search is submitted or the page is left, and ignores a body that still arrives (the serial, the form and the results box must all still be attached). `tests/test_phone_live_search_browser.py` runs the real initializer in Chromium with the network answer held back: a late body never overwrites newer results or the address, clearing the field lands on the empty search, and an answer for a page already left is dropped. Removing the serial check makes the first test fail.

## Follow-up · 2026-11-04

OW-2AB uses the explicit launch modes approved in #303: `--profiles` opens protected profiles, `--demo`/`--sample` stay isolated, and bare launch and every `--db` argument stop before opening data. Source launchers also install the declared encrypted extras (`tests/test_plain_install.py`). The later approved mode requirement supersedes this branch’s initial default-profile proposal.

## OW-2AB follow-up · 2026-11-04

Owner approved restricting the legacy browser runner to explicit demo/sample data. Bare launch and every `--db` argument now stop before database or network work; `--profiles` retains encrypted-profile startup, and existing plaintext files are untouched. Plaintext tests may opt into encrypted-profile thread/close checks through `strict_thread=True` and the `strict_c` fixture. Evidence: [tests/test_legacy_launcher.py](../../tests/test_legacy_launcher.py) and [encrypted database regression tests](../../tests/test_encrypted_database.py). This closes OW-2AB; explicit legacy import remains separate IT-2C work.

**Import follow-up:** parsing, review proposals and row posting are separated with existing confirmation and rollback contracts.

Section 7 follow-up, 2026-11-04: statement readers, explicit cross-currency legs, rule labels/category edits, FIFO cash age/calendar, scheduled-cash scenarios, bill warnings and figure freshness are implemented with fictional fixtures. The owner excluded NF-7C app migration and retained the Android action-policy hold. Scenario comparisons explicitly cover scheduled cash; the separate variable-budget Safe to spend formula is not reused as a daily forecast. Source acceptance is in the linked tests; native first-device pairing remains the existing cutover gate.
