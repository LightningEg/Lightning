---
title: Stored month-end figures
type: tech
area: reporting
status: blocked
blocked_by: a profile past about 4,000 transactions or a tab past 400 ms
created: 2026-10-04
by: unknown (moved from docs/proposals)
---

# Stored month-end figures

**Status: proposal · decided not to build yet, 2026-10-04.** Why not now is in [Architecture](../../docs/ARCHITECTURE.md) › Position and reporting contract (*No stored calculations table*).

**Build when** a real profile passes about 4,000 transactions, or any tab passes 400 ms (Budget › All time took 236 ms on 2,239 transactions, 2026-10-04).

**Design.** Store month-end values of ledger figures for closed months only (What you own, Holdings value per class, Money in and Money out per category), keyed by figure name and month. Clear them from the earliest changed date with SQLite triggers on `ledger_entries`, `transactions`, `price_history` and the valuation tables, so no write path can miss it. Rebuild on read. Add a test that checks stored against live values. Plan figures (Free cash, Safe to spend, budgets) depend on today, reserves and settings, so they are never stored.
