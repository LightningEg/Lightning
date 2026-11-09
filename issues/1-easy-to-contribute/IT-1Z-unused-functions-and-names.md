---
title: Unused functions and names - five that nothing calls, and eleven that only tests call
type: tech
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
Found by [r31](r31-code-review-and-loose-ends/report.md) F11: vulture, then each name searched with `grep -rnw` in `lightning/`, `tools/`, `android/app/src` and `tests/`.

**Nothing calls these (not even a test):**

| Name | Where |
| --- | --- |
| `TransactionService._tagged_notes` | `lightning/transactions/service.py:375` |
| `TransactionService._submission` | `lightning/transactions/service.py:774` |
| `TransactionService._ownership_cash_keys` | `lightning/transactions/service.py:904` |
| `TransactionService._tagged_cash_keys` | `lightning/transactions/service.py:912` |
| `excel_sheets` | `lightning/statement_files.py:97` |
| parameter `include_ids` of `_categories` | `lightning/workflows/ai_analysis.py:41` |

**Only tests call these** (production never does): `ReportingService.foreign_currency_accounts`, `.bridge_for_month`, `.monthly_trend` (`lightning/reporting/service.py`); `RuleService.category_for_name`, `.depends_on_more_than_name`; `TransactionService.set_transaction_owner`; `AssetService.remove_price`; `rebuild_trade_rates` (`lightning/transactions/conversion.py:179`); `pending_migrations` (`lightning/database/migrator.py:170`); `compose_parts` (`lightning/security/cosmetic_parts.py:83`); `MarketBundle.daily_closes`.

Left out on purpose: everything under `lightning/sync/journal/`, `lightning/runtime/journal*` and `lightning/ui/journal*` (claimed work, still being wired).

## Fix
1. Delete the five functions of the first table and the unused parameter (check its two call sites pass nothing). For each, run `grep -rnw <name> lightning tests tools` first; if anything appears that this report missed, leave that one and say so in the commit.
2. Do **not** delete the second list. Add each name to this item's file under a heading "Kept, test-only" with one line saying what it was for (read its docstring), and stop: whether a tested-but-unused function is a planned feature or leftover is the owner's call (ask with the question tool, options: delete with its tests / keep as planned API).
3. `ruff check lightning tools`; `python -m pytest tests/test_transactions.py tests/test_statement_files.py tests/test_architecture.py -q` (use the real file names: `ls tests | grep -i "transaction\|statement"`), then the full suite once.

## Done when
The five are gone, the suite passes, and the second list has the owner's answer recorded here. Release-note: none.
