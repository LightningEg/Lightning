---
title: Legacy mode - `python -m lightning` still opens a plaintext database with real-data paths
type: owner
area: architecture
status: ready
created: 2026-10-21
by: Claude
---

## Report
Found by [Audit 5](../../reports/2026-10-21-backend-streamlining/report.md) §3. The stale code is removed (2026-10-22): 17 unused functions, `counterparty_suggestions`,
the always-on `allow_foreign`, the unread `weekly_review_remaining` and `budget_carryover_month`, repeated imports and a legacy
`owner_id` guard. Kept on purpose, because tests use them as oracles for a figure another path computes: `ReportingService.monthly_trend`,
`bridge_for_month`, `foreign_currency_accounts`, `Position.deposits_after_sale`, `reserves.allocation_at`,
`TransactionService.set_transaction_owner`, `migrator.pending_migrations`, `conversion.rebuild_trade_rates` (Architecture says so)
and `live_prices.fetch_now`. `market_url` stays: it points the price download at a mirror.

Left, for the owner: `python -m lightning` still opens a plaintext `data/lightning.db`. Code that exists only for it:
`live_prices.fetch_if_due`, the browser branch of `ui/routes/settings.py` (browser-only settings), and the legacy filename rule
in `bootstrap.py`. Most tests use that plaintext path, which never checks that the database is used from its own thread.

## Fix
If the owner agrees: legacy mode opens only `--demo` and `--sample` (no default real-data file), and a strict owning-thread option
for the test fixture.
