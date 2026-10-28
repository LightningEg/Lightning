---
title: A certificate's holding page shows price charts, nine empty "Units out" rows, no interest, and saves it as Equity Fund
type: bug
area: investments
status: ready
created: 2026-10-20
by: Claude
github: 162
skills: guideline-audit
app_version: 1.3.0
commit: 7591231
repo: app
---

## Report
Found by [Audit 1](../../reports/2026-10-20-demo-readiness/report.md) (§3 PC). Sample, `/investments/holding/10` (NBE 3-year certificate). Severity: medium (wrong data on screen).

- Planning › Allocation bucket shows "Equity Fund": the menu has no CDs option, falls back to its first entry, and the field saves on change.
- "How bumpy has it been?" draws price movement for a fixed-price certificate: nine rows of 0.0%, a flat "Fall from its high", "Months up · down 0 · 0 of 0".
- "Trades and payouts" lists nine "Units out — — 0" rows (monthly checkpoints mislabelled at `investments/journey.py:64`) and none of the interest payouts.

## Fix
For certificates, hide the volatility block, list interest received from `deposits/receipts.py`, drop the checkpoints from the trades list, and add
the CD bucket (or hide the bucket field). Test on the sample's certificate.
