# Audit 5: is the backend engine efficient and streamlined?

2026-10-21 · Claude · app 1.3.0, commit `6e1c043` (main). Written as Audit 3; renumbered when the edit-journal audit took that number · temporary databases only (Mohab's 2026 sample, plus synthetic history), prices offline.

The owner asked four things: is the backend efficient, are there loose ends, is any function stale or any structure causing
problems, and is the architecture streamlined. Three reviews ran in parallel: the ledger engine, the read and plan side, and
runtime, workflows and imports. Every finding below was reproduced or traced in the code before filing; the high ones were rerun
a second time. It builds on [Audit 2](audit-2.md) (conversion rates and eight dead helpers, both fixed) and does not repeat it.
Cleanup note (2026-10-23): this older report is Audit 5. Its original 2G–2K and 3AC codes are 2P–2T and 3AF; Audit 4 retains the later cash/Save findings.

Each finding is now an item in [the plan](../issues/INDEX.md); this report is the summary and the evidence.

## Verdict

**The foundation is right; the waste and the risk are in copies.** The layers hold (all four import contracts pass), only
`TransactionService` posts through `validate_posting`, money is stored as integers, every rate goes through `fx.rate_for`,
the request cache is safe, the service graph is built once per profile open, and the full suite passes (about 2,190 tests,
none failing). What is not streamlined:

| Question | Answer | Items |
|---|---|---|
| Efficient? | **No, mainly because of one small bug.** Reading today's position opens an empty write transaction. That empties the request cache, so the main pages run 37–47% more queries than they need. | 3AF, 3X, 7O, 9I |
| Loose ends? | **Yes: two money bugs in held-for-others, and Undo can reverse the wrong action.** | 2P, 2Q, 2R |
| Stale functions? | **About 25 unused or test-only functions, and two settings written but never read.** | 9L |
| Structures that cause problems? | **The same fact kept in two to six places.** One of these copies already shows a wrong figure on screen (7N). Routes still compute figures, and 18 modules are outside the layer contract. | 7N, 2T, 9J, 9K |

## 1 Efficiency

**Page reads.** `SELECT` statements per page on Mohab's sample, with identical HTML in every column:

| Page | Now | Without the empty write transaction (3AF) | Plus one read per date for all accounts (3X prototype) |
|---|---:|---:|---:|
| Overview `/` | 705 | 445 (−37%) | 353 (−50%) |
| Cash planning `/plan` | 480 | 263 (−45%) | 199 (−59%) |
| Investments `/investments` | 290 | 155 (−47%) | — |
| Financial health | 233 | 233 | 176 (−24%) |
| Budget | 128 | 128 | — |

- **The empty write transaction, 3AF.** `PositionService._at` (`planning/position.py:348`) calls `match_payments` on every read of today. It always opens `BEGIN IMMEDIATE` (`planning/service.py:245`), even with nothing to settle. `undo.finish` then runs its `UPDATE`/`DELETE` housekeeping, `total_changes` moves, and `core/memo.py:37` empties the cache. The Overview does this four times, and every page view takes the write lock. The middleware already matches payments after each write (`ui/web.py:429`), so the page-time calls add nothing.
- **Per account, per date, 3X.** The call chain is `visuals.net_worth_trend` (10–12 month ends) → `PositionService._at` → `class_values`/`owned_holdings` → `cash_total_for_account`, at 2 SQL per cash holding. On top of that, `reporting.owned_brokerage_cash` costs 3 SQL per brokerage. The same loop is copied in `dated_cash.py:99`, `funding.py:64`, `foreign_currency_accounts` and `_balance_and_owned`. A bulk read already exists (`MoneyFromOthersService.totals_by_account`).
- **Repeated reads with no cache, 3AF.** Calls per Overview against distinct arguments: `BudgetService.month_view` 19/5, `cash_flow` 28/10, `CategoryService.get_by_code` 41/20, `PlanningService.items` 86/6. `own_liquidation_factors` and `certificate_for_asset` run once per date, though neither depends on it.
- **Arabic page weight, 3AF.** Every Arabic page embeds the whole 2,694-entry browser translation table (`ui/web.py:362`): the Overview is 48 KB in English and 500 KB in Arabic.
- **The test budget is rising, not falling.** The Overview's `PAGE_READ_BUDGET` went 640 → 750 → 900 in three weeks (`tests/test_reporting_performance.py:199`). Each rise was the account-count growth above.

**Writes and imports.**

| Path | Cost | Item |
|---|---|---|
| Bank-import preview, 400 rows | 2.94 s, of which 1.78 s is `usual_categories()`: a full-history window query, run once per row (`bank_imports.py:510`) | 7O |
| Reimbursements page | 7 queries per posted expense in history: 1,846 statements for 265 expenses (`reimbursements.py:116`) | 9I |
| One manual expense on an account with 5,000 earlier lines | 20 ms against 2.7 ms on the sample. `_refuse_cash_below_zero` (`transactions/service.py:472`) walks the account's whole cash history in Python | 9I |
| Adding a counterparty with 5,000 unlinked trades | 32.6 ms against 5.9 ms. `_link_historical` rescans buys and sells that are never linked by design | 9I |
| Unlocking a profile | 0.14 s at 1 MB, 1.2 s at 4.4 MB, 6.2 s at 19 MB (Argon2 not counted). Each unlock takes a full backup and runs the integrity check three times | 2S |

## 2 Loose ends that touch money

- **2P Held-for-others writes ledger lines itself.** `money_from_others.py:20-57` and `ownership_migration.py:60-80` update and insert into `ledger_entries` directly, outside `TransactionService`. Reproduced: marking 33.33 of a 100.01 USD line (rate 50.123457) as Dad's stores base amounts of 3342.234157 and 1670.615843. Undo on that transaction is then refused with "Line 1: amount_base has more than 2 decimal places".
- **2P A voided sale still counts.** The custody check at `money_from_others.py:206` sums `investment_custody_events` without checking that the transaction is still posted. The next check, at line 213, does check. Reproduced: buy 10 for Dad, sell 10, void the sale. The ledger says Dad holds 10, but selling 5 is refused.
- **2Q Undo groups writes by a hand-kept list of URL roots** (`ui/web.py:411`). `POST /money-from-others` and `POST /birdview/settings` are missing from it. Undo after recording money for someone reverses the action before it. Automatic payment matching is also skipped after that write. Six roots on the list have no write route.
- **2R The profile currency is copied into six services.** Both refresh functions (`bootstrap.py:115`, `sync/journal/areas/settings.py:21`) miss `reporting.fx_positions.base`. Reproduced: a new USD profile lists USD as a foreign currency until the app restarts.
- **2T Four Integrity checks can never fail.** Each one rebuilds the figure from the very parts it then compares against (`integrity.py:89-92` and three more). Tests only check that the checks appear.

## 3 Stale code

Each name below was checked by searching `lightning/`, `tests/`, `tools/`, `android/`, the templates and the journal's
command strings (`assets.remove_price`, for example, is live through the journal, so it is not listed).

- **Unused:**
  - `keynotes.lowest_point`, `next_payment`, `largest_part`, `sale_cost`, `cash_share`
  - `visuals.flow_trend`, `spending_bars`, `portfolio_trend`
  - `review.for_page`
  - `MoneyFromOthersService.transaction_owner`
  - `AccountService.get_by_code` and its repository method
  - `budgeting/domain.used_pct`
  - `investments/domain.unrealized_pct` and `variance_per_unit`
  - `core/codes.SEGMENT_RE`
- **Only tests call them:**
  - `ReportingService.monthly_trend`, `bridge_for_month`, `foreign_currency_accounts`
  - `TransactionService.set_transaction_owner`, `counterparty_suggestions`
  - `reserves.allocation_at`, `Position.deposits_after_sale`
  - `dashboard._owned_wealth_rows`, `migrator.pending_migrations`
  - `conversion.rebuild_trade_rates`. Architecture calls it the repair path, but no screen or tool reaches it.
- **Settings and flags:**
  - `budget_carryover_month` is written (`ui/routes/budget.py:540`) and never read.
  - `weekly_review_remaining` is read only by a test.
  - `market_url` is set only by tests.
  - `allow_foreign` is always on, but its message still says other currencies are "not built yet".
- **Dead rows:** nothing writes `money_from_others` rows without a transaction any more. Five reads still look for them.
- **Duplicate indexes:** five indexes repeat another (`ix_ledger_transaction`, `ix_price_asset_date` and three more). Each ledger line written updates seven indexes.

## 4 Structure

- **The same fact in several places, 7N, 2T, 9K.** A copy that drifts gives a wrong figure, and one already does:
  - **Payments before next income, two formulas.** The Cash planning card (`ui/kpis.py:229`, `ui/visuals.py:535`) adds up each bill's full amount in its own currency. Safe to spend (`planning/forecast.py:297`) adds up what is still owed, in EGP. Adding one 20 USD subscription to Mohab gives 18,480 on the card and 19,492 in the breakdown.
  - **Free cash, three formulas:** `Position.free_cash`, `reserves.cash_summary` and a fallback in `forecast.free_cash`.
  - **Four checks that a balance never goes below zero:** `_validate_owner_balances`, `_refuse_cash_below_zero`, `_validate_owner_partition`, `lowest_running_quantity`.
  - **Two kinds of money rounding:** half-even in `core/ledger._round2` and half-up in `core/money.quantize`. 10.01 × 50.5 posts 505.50 but quantizes to 505.51.
  - **Four copies of the id check:** `reserves`, `reimbursements`, `planning/service`, `workflows/activity`.
  - **Custody kept in two places:** the ledger's `owner_id` and `investment_custody_events`.
- **Routes still compute figures, 9J.**
  - The `dashboard` route builds eight figures that no PC or phone template reads. One of them, `investment_share`, is a second formula for the investing rate.
  - Budget `_page` is 369 lines. It recomputes the category averages `BudgetService` already has, overwrites its own first loop, and calls the private `_owned_spending`.
  - `register.create_investment_entry` is 171 lines and opens its own database transaction.
  - Radon rates `register.page` at complexity 119, the highest in the code.
- **Layers the linter cannot see, 9K.**
  - 18 top-level modules and `lightning.sync` are in no layer: `bank_imports`, `money_from_others`, `reserves`, `zakat`, `integrity`, `fx` and others. A contract that places them all breaks only once (`sync/transport.py:550 → runtime.paths`), so adopting it is cheap.
  - `bootstrap.py:193-207` wires callbacks so that budgeting calls planning, which is a higher layer.
  - `bootstrap.validate_history` is 52 lines of ledger checking that call private `TransactionService` methods.
  - `database/connection.py:169` imports `lightning.undo`.
  - `runtime/app.py:profile_app` is a single 746-line function of nested routes.
- **Two startup paths, 9K.** Legacy `main.py:100` always posts month-end checkpoints. A profile open posts them only when a price file fills. With no `market.zip`, a profile opened on 2026-12-05 posted 0 checkpoints where `process_due` posted 10.

## Keep

- The three layers and the single posting writer.
- Integer money with `validate_posting` as the one gate.
- `fx.rate_for` as the one rate lookup.
- The figures registry and its tests.
- The request cache: it switches off inside transactions, clears on writes and hands out copies.
- Careful savepoint rollback.
- Append-only migrations, with a backup before an upgrade.
- The price thread only fetches; saving happens on the database's own thread.
- A linear import confirm, at about 40 statements a row.

Two parts are not defects: the older lend-and-hand-back sync runs in production while the edit journal runs in the lab, and
[4A](../issues/4-edit-journal-and-devices/4A-edit-journal.md) already retires the old sync at the J6 cutover.

## Order to fix

1. **2P, 2Q** (money and undo): small to medium, each with a test that reproduces it.
2. **3AF**: small, and the largest speed gain. **3X** was built on main from this audit's call chains (#85), with the empty-write fix.
3. **7N, 2R, 2T**: small. The figure a person sees must have one formula.
4. **7O, 2S**: small and medium, felt when importing and unlocking.
5. **9I–9L**: cleanup, done when the code around them is next touched.

## Owner decisions

- **Legacy mode.** `python -m lightning` still opens a plaintext `data/lightning.db` with real-data paths: `fetch_if_due`, a browser-only settings branch and a legacy filename rule. Should it shrink to `--demo` and `--sample` only? Most tests use that plaintext path, which never checks that the database is used from its own thread (9K).
- **Backups on unlock.** Should an automatic backup be taken at most once a day, keeping daily, weekly and monthly copies, instead of the newest 30 unlocks (2S)?

## How this was run

- **Reviews:** three read-only reviews (ledger; read and plan; runtime and imports).
- **Scans:** an AST and identifier scan for unused definitions, `vulture`, `radon cc`, `pylint` duplicate-code, and `lint-imports`.
- **Measurements:** SQL counted with SQLite's trace callback. Pages were fetched through FastAPI's `TestClient` on Mohab's sample (`LIGHTNING_TODAY=2026-10-02`). Every "without" figure monkeypatched only the named call and compared the HTML byte for byte.
- **Limits:** timings are single runs on Linux with plaintext SQLite. Windows and SQLCipher will be slower, though the query counts carry over.
- **Changes:** no code was changed.
