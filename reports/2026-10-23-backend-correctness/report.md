# Audit 4: backend correctness and failure boundaries

2026-10-23 · Codex · Lightning 1.4.2 · main `a19c844cad963ccd45e75baacd3c97cf774ecc83`.

## Assessment

The ledger/plan/report split is useful, and the ordinary financial arithmetic reconciles. The largest risk is inconsistent enforcement of financial rules across create, edit, void, restore, conversion and ownership changes. These paths share a database but do not share one complete invariant check. Ten reproducible defect groups and one architecture improvement are filed below, including the button-workflow extension requested after the backend pass. No production fixes are included.

All reproductions use temporary dummy databases, offline prices and a fixed date of 2026-10-23. [Run the probes](evidence/reproduce.py) with `python reports/2026-10-23-backend-correctness/evidence/reproduce.py`; [captured output](evidence/results.txt). HTTP probes use an in-process ASGI client; no network listener or real profiles are involved. GitHub's connected API confirmed that remote main matches the audited commit after shell Git could not reach its proxy.

## Findings, ordered by risk

| Item | Severity | Confirmed behavior | Expected behavior |
|---|---|---|---|
| [2M](../../issues/2-safe-for-real-money/2M-stale-edit-form-overwrites.md) | High | A stale popup saved for notes overwrites a newer amount, 20 → 10. | Refuse stale revisions or merge only explicitly changed fields. |
| [2N](#fix-progress) | High | Save reports HTTP 400 for missing bill FX after posting the expense. | Make failure/success accurately describe whether money committed. |
| **2G · fixed** | High | Delete funding income, restore a spent expense or buy, reduce an opening balance, or convert unfunded cash: balances go negative. | Apply the cash/funding policy to every state transition; refuse an invalid resulting ledger. |
| **2H · fixed** | High | Moving an income strands its old account at −50; reassigning a purchase strands its old owner at −1 shares. | Validate both the old and proposed account/asset/owner sets. |
| [2I](../../issues/2-safe-for-real-money/2I-posting-currency-contract.md) | Medium | Public `post()` accepts USD cash in an EGP account and a non-1 base-currency rate. Reports disagree. | Resolve assets/accounts in the posting boundary and enforce their currency/type relationship. |
| [2J](../../issues/2-safe-for-real-money/2J-register-submit-idempotency.md) | Medium | Two identical register POSTs return 303 twice and create two expenses. | A retry of one submitted action returns its original result. |
| [2L](../../issues/2-safe-for-real-money/2L-instalment-input-precision.md) | Medium | A price of 100.001 over two instalments produces 50.01 and 49.991; the last payment cannot post. | Refuse sub-cent price/fee inputs before saving a loan. |
| [2K](#fix-progress) | Low | A rejected currency-converting buy leaves a new empty currency pocket. | Route selection, pocket creation, conversion and purchase roll back together. |
| [2O](#fix-progress) | Medium | Phone bulk Delete voids selected rows without a confirmation question. | Confirm the selected scope and preserve the button’s delete action. |
| [3AE](#fix-progress) | Medium | A refused PC bulk edit loses both selection and typed changes. | Keep the correction and selection available after a rejected save. |
| [1G](../../issues/1-easy-to-contribute/1G-complete-backend-architecture-contracts.md) | Tech | Major financial modules and `sync` are outside the layered import contract. | Give every production module an explicit dependency policy. |

### 2G: the cash rule depends on which operation was used

Separate clean ledgers reproduce each case:

- Bank starts at 100, receives 100, spends 150. Deleting the income succeeds and leaves −50.
- Bank starts at 100, spends 80, voids that expense, spends 70, then restores the first expense. Restore succeeds and leaves −50.
- Brokerage starts at 100, buys for 80, voids that buy, buys for 70, then restores the first buy. It owns two units with −50 cash, bypassing the purchase-funding rule.
- Bank starts at 100, spends 80, then edits its opening balance to 10. The edit succeeds and leaves −70.
- Empty brokerage converts 500 EGP into 10 USD. It receives the dollars and is left at −500 EGP.

Cause: `transactions/service.py:34` limits the manual cash check to IN/OUT/TRF. `void:724`, `delete_many:745`, `restore:779`, and opening-balance writes do not all run it. Restore checks aggregate non-cash holdings but does not force the brokerage-cash validation that BUY creation uses. Imports are intentionally exempt; these examples do not depend on importing or a pre-existing negative balance.

Fix first: one resulting-state validator inside the same write transaction, using explicit policy for manual/import/system actions. Exercise create/edit/void/delete/restore/opening changes and conversions against the same scenario matrix. Preserve intentional imported history and harmless edits to pre-existing deficits.

### 2H: edits validate what receives the posting, but can miss what loses it

Bank A starts at 100, receives another 100, spends 150. Move that income to empty Bank B: A becomes −50; B becomes 100. `_refuse_cash_below_zero` constructs its keys from the proposed lines only (`transactions/service.py:480`).

In a shared brokerage, fund both owners, buy one share for each, and sell the other owner's share. Edit that owner's original buy to be yours. The pooled holding remains positive, so `_check_holdings` passes; the other owner's holding is now −1, yours is 2. `_validate_owner_balances:418` selects proposed ownership keys, and `_update:1010` does not supply all removed keys. This is separate from 2G: even invoking today's validators is insufficient when their affected-key set is incomplete.

Fix: compute the union of old/new `(account, asset, owner)` keys and check their full dated history inside the transaction. Include accounts/assets removed by an edit, owner reassignment, and transfers changed into income/spending.

### 2I: the public posting boundary trusts callers too much

`post(DocType.IN, ..., [PostingLine.cash(egp_bank, usd_asset, 10, INFLOW, salary, fx_rate=50)])` succeeds. `account_balance()` reports 110 native EGP including the account's 100 opening balance, while `account_value()` remains 100 without a saved USD price. The line itself claims 500 base units. A second probe posts 0.01 EGP at FX 0.5 and stores a zero base amount.

`transactions/service.py:390` validates usable accounts, deposit placement, arithmetic and ownership, but does not generally match the asset's currency to its account or require base-currency cash to use rate 1. `core/ledger.py:126` has no master-data context. Cash quantity aggregation (`reporting/queries.py:128`) assumes the currency invariant already holds.

This is a service-level integrity gap, not evidence of an unauthenticated HTTP exploit. Ordinary trade builders usually enforce currencies. Make the shared writer derive cash identity/type from master data, check account/asset currency, and require rate 1 for base cash; allow valid conversion rates for foreign lines.

### 2J: browser retry is not the journal's at-most-once guarantee

Two identical `POST /accounts/{id}/register` requests with date 2026-09-02, amount −10, the food category and identical notes both return 303. The bank moves 100 → 80 and two OUT documents exist. This was reproduced through the actual ASGI route, beyond calling the service twice.

`ui/routes/register.py:634` creates a new transaction on every request. Distinct legitimate expenses can share all their fields, so content-based deduplication would be wrong. Use a per-submission operation ID, persist its payload hash and result atomically with the posting, and reuse it for retries. Map that ID to the journal origin rather than generating a fresh logical command on every HTTP retry. The journal can deduplicate one command identity without recognizing two separately minted commands as one button action.

### 2L: instalment precision is checked too late

`planning.create_purchase(price='100.001', fee='0', months=2)` stores principal 100.001 and generates amounts 50.01 and 49.991. After assigning a payment category, `record_payment` of the final amount raises `Use at most 2 decimal places.`

`planning/loan_actions.py:45` checks sign and count but not the price/fee currency precision. Monthly rounding hides the invalid principal until the final instalment. Check both monetary inputs at entry using the relevant currency's minor units, and verify every resulting instalment can be posted and the total equals the accepted purchase total. This is a different path from the planned-amount fixes already recorded in 2E.

### 2K: an outer transaction starts after a write

`InvestmentService.buy_converting` calls `route()` at `investments/service.py:219`, before its transaction. Routing can create a brokerage currency pocket. Ask an empty EGP brokerage to buy a USD asset with quantity zero: the buy is refused, but the account count grows from three to four. The invalid purchase posts no cash movement; this is a partial metadata write.

Move routing and pocket creation inside the transaction, as `_trade()` already does. Inject failures at conversion and purchase as well as invalid quantities and ensure both account rows and financial rows are unchanged.

## Button workflows: actual route and browser audit

The owner asked to audit how buttons act, including changing ownership and mass editing. This extension exercises the actual POST routes with ASGI and real Chromium at 1280 × 900 and 390 × 844. It uses fresh temporary ledgers and invented people, not real profiles. The production source remains at the audited main commit; the report branch already contains the initial audit.

[Workflow probes](evidence/workflow_probes.py) contain passing controls and strict expected failures against the desired behavior. Run `pytest -q -rx -o addopts='' reports/2026-10-23-backend-correctness/evidence/workflow_probes.py` with the development dependencies installed. [Results](evidence/workflow-results.txt) record the run. A known defect becoming an unexpected pass requires reviewing its marker; a setup exception does not count as reproducing the defect.

### What each tested button does

| Button / sequence | State that should change | Verified outcome |
|---|---|---|
| PC Change ownership → Save | One ADJ posting; ownership shifts, gross cash stays fixed | Pass for a valid assignment; the real type-and-pick and Save create one document. |
| Change ownership → edit amount | Update the same ADJ; gross stays fixed | Pass for a simple amount correction. |
| Ownership → Escape → Keep editing / Discard | Preserve fields / close without posting | Pass in Chromium; neither path posts money. |
| Someone paid an expense for you → Save | One expense and equal custody credit; gross unchanged | Pass: expense 70, held cash 70, gross 1,000. |
| Invalid ownership Save | Error with no financial mutation | Pass for zero, negative, sub-cent, NaN, letters, insufficient balance, future/bad date, missing/unknown/same owners and unknown mode. |
| Edit ownership after old owner spent its cash | Refuse an impossible old-owner balance | **Fails, 2H:** changing Alice to Bob leaves Alice at −90. |
| Bulk Held for on funding receipt | Reassign only if both owners’ histories remain valid | **Fails, 2H:** a receipt moved to Bob leaves Alice at −50 after her withdrawal. |
| Select range / all / clear / filter | Select explicit transactions; do not post or leak selection into another scope | Existing Chromium checks pass, including duplicate-leg synchronization and filtered-view isolation. |
| Edit selected → Cancel / Escape | Keep selection and entered values; no write | Existing Chromium checks pass. |
| Edit selected → Only this row | Save only that row | Existing Chromium check passes; unselected edit also leaves selected rows alone. |
| Edit selected with amount/account change | Do not silently apply or discard a single-row-only change | Existing Chromium check passes: the bulk option is not offered for the incompatible change. |
| Bulk notes / category with mixed row types | Change supported selected rows; report skipped rows; keep amounts/dates | Pass: notes update two expenses and skip a transfer; category updates two expenses and skips income, transfer and split. |
| Bulk save with bad or checked later row | Roll back all earlier updates in that batch | Pass: the ledger is unchanged after either refusal. |
| Refused bulk save → retry correction | Keep the selected scope and entered correction | **Fails, 3AE:** the ledger rolls back, but the editor and selection disappear. |
| Duplicate IDs / empty bulk selection | Apply once per document / no write | Pass for bulk edit/category/delete. |
| PC Delete selected → Cancel / Delete | No write on Cancel; soft-delete precisely the selection on confirmation | Pass in Chromium; Undo restores the deleted rows. |
| Phone Change category | Update only selected eligible rows; preserve cash | Pass in Chromium; two rows change, bank remains 980. |
| Phone Delete selected | Ask before posting the delete | **Fails, 2O:** both selected rows are already VOID before any answer. |
| Repeat bulk delete / repeat Restore | Harmless second request | Pass: second delete changes zero documents; repeated restore leaves the ledger alone. |
| Ownership / bulk notes → Undo → Redo | Reverse/reapply the complete grouped action | Pass, including gross-cash conservation. |
| Stale Undo ID after another action | Refuse the outdated action without partial replay | Pass: history reports that it changed. |
| Duplicate Merge → preview / confirm / retry / Undo | Preview is read-only; stale preview refuses; one merge; retry harmless | Pass through actual routes; Undo restores the duplicate. |
| Split expense → invalid sum / valid sum / Undo | Refuse invalid totals; keep total cash; reverse the entire split | Pass through actual routes. |
| Record a bill payment → retry → Undo | One expense plus paid link; no duplicate; Undo removes both | Pass: repeated payment is refused as already settled. |
| Older transaction form → change notes → Save | Preserve a newer amount or report a conflict | **Fails, 2M:** the old amount is silently posted again. |
| Expense Save with unrelated missing bill FX | Distinguish committed save from failed reporting | **Fails, 2N:** HTTP 400, but an expense exists and cash has fallen. |

### 2M: an older form silently reverses a newer amount

Open an expense edit popup when its amount is 10. Another save changes it to 20. In the older form, change only its note and press Save. `POST /transactions/{id}/edit-popup` returns 303 and puts the amount back to 10. This is one document being overwritten, not a duplicate.

`ui/routes/transactions.py:52` accepts all the original fields without a revision token; `TransactionService.update_in_account` rebuilds the current posting from those stale fields. Single-row register edits have the same general missing-precondition risk. The demonstrated failure is the popup route; journal form timing and every other edit screen were not independently tested.

Fix: render a revision/hash with the form and compare it inside the transaction, or explicitly merge only changed fields against their base values. Return a reviewable conflict, preserve the user’s inputs, and never quietly replace an intervening financial change. Merge and Undo already have their own tested preconditions; this item covers edit forms.

### 2N: Save can report failure after posting the expense

Create an empty USD account, then a recurring USD bill for 10 with no saved USD/EGP rate. Separately, save a 10 EGP expense in a funded EGP bank through `POST /accounts/{id}/transaction/new`. The response is HTTP 400 mentioning an exchange rate. Nevertheless, an OUT document exists and the bank is 990 instead of 1,000. The error page retains the expense form, inviting another Save; submitting it again posts another expense before returning 400 again.

No injected fault is needed. `ui/routes/accounts.py:332` commits `record_outflow`, then calls `_budget_feedback` (`ui/routes/register.py:143`). The budget reads the unrelated foreign bill, raises a missing-FX ValidationError, and the route catches it as though the write failed. `RequestCache` groups Undo records but does not put the whole request in one database transaction.

Fix: give the financial workflow one clear commit boundary and success result. Compute required validations before committing; treat optional post-save feedback failures as a successful save with a warning, or roll back the whole action if feedback is required. Keep the per-submission idempotency fix in 2J as a separate safeguard. Test both the first response and a retry with a missing FX rate.

### 2O: the phone’s Delete button does not ask

At 390 px, select two ordinary expenses in the account register and press Delete. The browser navigates immediately, displays “Deleted 2 transaction(s)”, and both rows are VOID. No confirmation dialog is opened or answered. [Screenshot after that click](evidence/phone-delete-without-confirmation.png).

`ui/templates/phone/register.html:109` sets `data-confirm-delete` on the **button**. The submit listener (`ui/static/app.js:738`) checks that attribute on the **form**, so it never asks for this flow. The phone selection bar also prints only “selected”, without the selected count; the scope is not made explicit there. PC bulk Delete uses a separate handler and its confirmation works.

Fix: handle the actual submitter, name the selected count, and retain its `formaction=/transactions/bulk-delete` when resubmitting after confirmation. Cancel must leave all rows selected and unchanged. Do not accidentally send a confirmed Delete to the form’s default category-change route. The action remains recoverable through history; this is not permanent data deletion.

### 3AE: a rejected bulk edit loses the work needed to retry

Select two expenses; one falls in checked bank history. Choose Edit selected, change notes to “keep this unsaved correction”, and choose All 2 rows. The server safely refuses the batch and leaves the ledger unchanged, but returns to the register with no selection and no editor. The typed correction is gone. [Screenshot of the refusal](evidence/bulk-save-refused.png).

The “all” branch clears `sessionStorage` selection before the server answers (`ui/static/app.js:886`); `ui/routes/transactions.py:476` redirects on a LightningError instead of retaining the submitted correction and selection. The atomic rollback itself passes.

Fix: retain a pending editor state until the server confirms success; on refusal, restore the selected IDs and changed fields, show which rows blocked the action and let the person adjust the scope or unlock history. Preserve the distinction between All selected and Only this row.

### Workflow validation

The existing focused set (`test_register_bulk_edit`, `test_bulk_category`, `test_ownership_rules`, `test_workflow_history`, `test_workflow_financial_history`) passes all 32 cases, including six real-browser cases. The added probes cover 36 scenarios: 30 pass and six strict expected failures reproduce 2H twice, 2M, 2N, 2O and 3AE. The new browser controls cover ownership picker/Save, Escape/discard, PC delete/Undo and phone category change; the two browser failures have screenshots above. No JavaScript page errors occurred in the passing controls that collect them.

The full existing suite now runs in an isolated environment: **2,349 passed, 9 skipped**, with no failures. It includes the pre-existing edit-journal tests, but this workflow extension does not independently establish native multi-device timing or delivery guarantees. All four import contracts pass. New probe failures are deliberately outside the normal `tests/` discovery and are not silently counted as existing-suite passes.

## Architecture and operational points of failure

**Keep the modular monolith and SQLite.** The reproduced problems do not justify microservices or a database rewrite. Centralize financial state validation and put complete business actions behind transaction-owning workflows. Routes and the journal should invoke those same workflows. Avoid exposing private service methods as an implicit cross-module API (`InvestmentService._rate` currently calls `TransactionService._fx`).

**Complete the enforced dependency map (1G).** `pyproject.toml` has useful contracts, but the layer list omits `bank_imports`, `counterparties`, `fx`, `integrity`, `money_from_others`, `ownership_migration`, `physical_items`, `reconciliation`, `reevaluations`, `reimbursements`, `reserves`, `saved_views`, `sms_imports`, `sync`, `undo`, and `zakat`, plus demo/sample modules. Some are constrained by other rules; they are not covered by the layered ordering. Add a coverage test that fails when a production module has neither a layer nor an explicit exemption. Split sync's protocol, financial adapter and runtime boundaries into separate contracts rather than putting the whole package into an arbitrary layer.

**Make wiring dependencies explicit.** `bootstrap.py` constructs services, then injects callbacks and optional collaborators into budgets, the forecaster and investments. This works through the composition root, but leaves hidden initialization requirements. Prefer constructor-required protocols or one explicit wiring/validation phase. Keep defaults that are genuinely optional; distinguish them from services that must exist for correct money calculations. This suggestion is included in 1G, not a reproduced runtime failure.

**The database disk is a failure domain.** Profile databases and default backups are under Documents/Lightning. Same-disk copies help with bad edits and some corruption, but not disk loss or loss of the whole directory. Recommend an independently stored encrypted backup and a tested restore; verify the backup includes the recovery material required for its format. Windows crash/reboot evidence remains explicitly open in [2A](../../issues/2-safe-for-real-money/2A-restore-safety.md), [2B](../../issues/2-safe-for-real-money/2B-promotion-durability.md) and [2C](../../issues/2-safe-for-real-money/2C-ordinary-pc-acceptance.md). This audit does not claim a power-loss defect or prove Windows durability.

**The journal home is the confirmation authority.** Its unavailability delays final confirmation even if a device durably queues an edit; that is a deliberate consistency choice. Show pending/confirmed/rejected state clearly and rehearse the existing home-move/recovery procedures. Cloud delivery is still a configured placeholder, and native PC/Android acceptance remains open in [4A](../../issues/4-edit-journal-and-devices/4A-edit-journal.md). The prior [journal audit](../2026-10-21-edit-journal/report.md) has its own scope and fixes; none of its passed encryption or replay claims were revalidated here.

## Validation and limits

| Check | Expected | Found | Result |
|---|---|---|---|
| Demo report reconciliations, as of 2026-10-23 | Zero differences | All nine IntegrityService checks PASS; 64 posted documents | Pass |
| Internal lines, demo ledger | Sum to zero per document | No unbalanced documents | Pass |
| SQLite / foreign keys, demo ledger | `ok` / no violations | `ok` / zero | Pass |
| Transfer between own accounts | Total cash conserved | 100 before and after | Pass |
| Ordinary expense, void, restore | Cash 80 → 70 → 80 → 70 | Exact match | Pass |
| Failure inside nested workflow | Roll back the expense | Balance unchanged | Pass |
| Invalid manual expense inputs | Refuse zero, negative, sub-cent, unaffordable, NaN and excessive amount | All six refused, no cash change | Pass |
| Lifecycle, removed-owner/account, posting currency, retry, loan precision, pocket rollback | Refuse invalid final state / avoid duplicate or partial save | Reproductions above | Fail |

No production fix was attempted. These probes cover selected high-risk backend paths, not every form or every combination of currencies and owners. The initial backend pass could not run the full suite because its dependencies were missing and the proxy was unreachable. During this workflow extension, development dependencies were installed in an isolated temporary environment (including cryptography 50.0.2 and SQLCipher 0.6.2); the full-suite and import-contract results above supersede that limitation. Native Windows/Android acceptance, real power loss, live Cloudflare delivery, exhaustive screen/Arabic/layout checks and load/concurrency behavior remain outside this audit. Existing automated encrypted-profile tests ran; this is not a native recovery acceptance run.

Recommended sequence: fix 2G/2H behind one invariant boundary, and close the stale-save and false-error paths in 2M/2N; then 2I/2J and the phone confirmation in 2O; then 2L/2K and retry-state preservation in 3AE. Add regression tests for every reproduced failure, then complete 1G and rerun the full suite and native recovery acceptance before relying on these changes for real money.

## Fix progress

**2G/2H fixed (2026-10-23).** The shared cash guard now compares each affected day across create/edit, conversion, opening changes, void/bulk delete, restore and Undo/Redo. Edits/removals validate removed owners and non-cash holdings as well as the proposed owners. Batch deletion validates its final state; imported deficits retain harmless edits and improvements. `tests/test_cash_invariants.py` supplies 19 regression cases (15 fail against the audited source); the two 2H workflow probes now run as normal passing checks. Original captured audit results and screenshots above describe the audited commit, not the repaired behavior.

Validation for 2G/2H: full suite **2,368 passed, 9 skipped**; all four import contracts kept. The journal conversion fixture correction was explicitly approved by the owner because that test file belongs to Claude’s claim; it adds genuine funding before spending. No journal implementation changed.

**2N fixed; 2M partly implemented (2026-10-23).** Optional budget feedback failures no longer turn a saved expense into an HTTP failure; financial validation failures still refuse the posting. Popup (PC/phone), inline register and split forms send a revision covering the header and all lines. Save compares it within the write transaction and retains the submitted token and inputs after a conflict. A replica Save keeps its pending proposal durable. Legacy callers without a revision keep their prior contract. Ownership, conversion and investment edit routes have the same guard, but their three hidden template fields await owner approval under Claude’s template claim; [the exact patch](evidence/form-revision-fields.patch) is ready. 2M remains open until those fields and workflow checks land.

**2O/3AE fixed (2026-10-23).** Phone Delete checks the actual submit button and asks about the unique selected count; Cancel keeps the ledger and selection, Confirm preserves Delete’s destination, and Undo restores the batch. Failed mass edits now return a structured refusal to the open editor; input and selection remain until a confirmed success, and a row-specific refusal names the blocking transaction. Seven new regressions cover phone Cancel/Confirm/Undo, category changes, retry after unlocking history, atomic rollback and legacy redirect compatibility, Arabic counts and translated row-specific refusals. The original screenshots describe the audited commit.

The repaired workflow probes now pass all **36** cases, and the combined new regression set passes **47**. Arabic checks pass **16** existing cases; new phone count/confirmation and row-refusal regressions pass in Arabic. PC (1280 px) and phone (390 px) visual checks show no horizontal overflow; popup conflicts now render one alert. Native Arabic voice review remains outside this automated check.

Combined full-suite validation: **2,395 passed, 10 skipped**; all four import contracts kept. The additional skip is the sibling-website guideline comparison in the temporary worktree; it passes separately from `/workspace/Lightning`, where the website is present. A final targeted run passes **21** Save/revision cases after deduplicating popup alerts; a phone smoke check confirms one alert and the newer amount retained.
