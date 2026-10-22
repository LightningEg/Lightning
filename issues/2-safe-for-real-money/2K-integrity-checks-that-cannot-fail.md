---
title: Four Integrity checks compare a figure with itself, so they can never fail
type: tech
area: integrity
status: ready
created: 2026-10-21
by: Claude
---

## Report
Found by [Audit 4](../../reports/audit-4.md) §2. Each check rebuilds its total from the same parts it then compares against:
- **"Free cash plus reserves and bills due equals spendable cash"** (`integrity.py:89-92`) builds free cash with `reserves.cash_summary` (cash − allocated − bills), then adds the parts back. It never reads `Position.free_cash`.
- **"Ownership split by account"** compares account value with (account value − custody) + custody.
- **"What I own plus held for others"** and **"Account balances equal asset classes"** read the same in-memory holdings on both sides.

Architecture says these checks verify Free cash; tests only check that they appear.

## Fix
Compare independent paths (for example `Position.free_cash` against a ledger sum), or remove the check. Test: corrupt one side
in a temporary profile and expect the check to fail.
