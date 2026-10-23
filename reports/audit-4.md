# Audit 4: backend correctness and failure boundaries

2026-10-23 · Codex · Lightning 1.4.2 · main `a19c844cad963ccd45e75baacd3c97cf774ecc83`.

## Assessment

The ledger/plan/report split is useful, and the ordinary financial arithmetic reconciles. The largest risk is inconsistent enforcement of financial rules across create, edit, void, restore, conversion and ownership changes. These paths share a database but do not share one complete invariant check. Six reproducible defect groups and one architecture improvement are filed below. No production fixes are included.

All reproductions use temporary dummy databases, offline prices and a fixed date of 2026-10-23. [Run the probes](audit-4/reproduce.py) with `python reports/audit-4/reproduce.py`; [captured output](audit-4/results.txt). HTTP probes use an in-process ASGI client; no network listener or real profiles are involved. GitHub's connected API confirmed that remote main matches the audited commit after shell Git could not reach its proxy.

## Findings, ordered by risk

| Item | Severity | Confirmed behavior | Expected behavior |
|---|---|---|---|
| [2G](../issues/2-safe-for-real-money/2G-cash-rules-across-lifecycle.md) | High | Delete funding income, restore a spent expense or buy, reduce an opening balance, or convert unfunded cash: balances go negative. | Apply the cash/funding policy to every state transition; refuse an invalid resulting ledger. |
| [2H](../issues/2-safe-for-real-money/2H-validate-old-account-and-owner.md) | High | Moving an income strands its old account at −50; reassigning a purchase strands its old owner at −1 shares. | Validate both the old and proposed account/asset/owner sets. |
| [2I](../issues/2-safe-for-real-money/2I-posting-currency-contract.md) | Medium | Public `post()` accepts USD cash in an EGP account and a non-1 base-currency rate. Reports disagree. | Resolve assets/accounts in the posting boundary and enforce their currency/type relationship. |
| [2J](../issues/2-safe-for-real-money/2J-register-submit-idempotency.md) | Medium | Two identical register POSTs return 303 twice and create two expenses. | A retry of one submitted action returns its original result. |
| [2L](../issues/2-safe-for-real-money/2L-instalment-input-precision.md) | Medium | A price of 100.001 over two instalments produces 50.01 and 49.991; the last payment cannot post. | Refuse sub-cent price/fee inputs before saving a loan. |
| [2K](../issues/2-safe-for-real-money/2K-converting-buy-atomicity.md) | Low | A rejected currency-converting buy leaves a new empty currency pocket. | Route selection, pocket creation, conversion and purchase roll back together. |
| [1G](../issues/1-easy-to-contribute/1G-complete-backend-architecture-contracts.md) | Tech | Major financial modules and `sync` are outside the layered import contract. | Give every production module an explicit dependency policy. |

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

## Architecture and operational points of failure

**Keep the modular monolith and SQLite.** The reproduced problems do not justify microservices or a database rewrite. Centralize financial state validation and put complete business actions behind transaction-owning workflows. Routes and the journal should invoke those same workflows. Avoid exposing private service methods as an implicit cross-module API (`InvestmentService._rate` currently calls `TransactionService._fx`).

**Complete the enforced dependency map (1G).** `pyproject.toml` has useful contracts, but the layer list omits `bank_imports`, `counterparties`, `fx`, `integrity`, `money_from_others`, `ownership_migration`, `physical_items`, `reconciliation`, `reevaluations`, `reimbursements`, `reserves`, `saved_views`, `sms_imports`, `sync`, `undo`, and `zakat`, plus demo/sample modules. Some are constrained by other rules; they are not covered by the layered ordering. Add a coverage test that fails when a production module has neither a layer nor an explicit exemption. Split sync's protocol, financial adapter and runtime boundaries into separate contracts rather than putting the whole package into an arbitrary layer.

**Make wiring dependencies explicit.** `bootstrap.py` constructs services, then injects callbacks and optional collaborators into budgets, the forecaster and investments. This works through the composition root, but leaves hidden initialization requirements. Prefer constructor-required protocols or one explicit wiring/validation phase. Keep defaults that are genuinely optional; distinguish them from services that must exist for correct money calculations. This suggestion is included in 1G, not a reproduced runtime failure.

**The database disk is a failure domain.** Profile databases and default backups are under Documents/Lightning. Same-disk copies help with bad edits and some corruption, but not disk loss or loss of the whole directory. Recommend an independently stored encrypted backup and a tested restore; verify the backup includes the recovery material required for its format. Windows crash/reboot evidence remains explicitly open in [2A](../issues/2-safe-for-real-money/2A-restore-safety.md), [2B](../issues/2-safe-for-real-money/2B-promotion-durability.md) and [2C](../issues/2-safe-for-real-money/2C-ordinary-pc-acceptance.md). This audit does not claim a power-loss defect or prove Windows durability.

**The journal home is the confirmation authority.** Its unavailability delays final confirmation even if a device durably queues an edit; that is a deliberate consistency choice. Show pending/confirmed/rejected state clearly and rehearse the existing home-move/recovery procedures. Cloud delivery is still a configured placeholder, and native PC/Android acceptance remains open in [4A](../issues/4-edit-journal-and-devices/4A-edit-journal.md). The prior [journal audit](audit-3.md) has its own scope and fixes; none of its passed encryption or replay claims were revalidated here.

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

No production fix was attempted. These probes cover selected high-risk backend paths, not every form or every combination of currencies and owners. The full pytest suite and import-linter could not run: pytest, pytest-xdist, import-linter, SQLCipher and the required newer cryptography were missing; installation could not reach the environment proxy. The existing cryptography is 43.0.0, whereas the app requires 50.0.2 for encrypted mode. Visual screens, native Windows/Android, real power loss, live Cloudflare, encrypted profile recovery and load/concurrency behavior were not tested.

Recommended sequence: fix 2G/2H together behind one invariant boundary; then 2I and 2J; then 2L/2K. Add regression tests for every reproduced failure, then complete 1G and rerun the full suite and native recovery acceptance before relying on these changes for real money.
