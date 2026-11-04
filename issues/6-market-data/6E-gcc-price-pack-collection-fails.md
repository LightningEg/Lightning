---
title: The Gulf-stocks price pack fails in the scheduled collector (run 103, 2026-11-04)
type: bug
look: technical
severity: low
pillar: own
size: S
status: new
created: 2026-11-04
by: Claude
---

## Report
Manual "Price packs" run 41824666768 (all packs) failed in its Collect step; the owner reported the `gcc` pack as the cause. The pack is checked-only (its source does not allow republishing), so no published price is affected, but the run goes red. The source error text was not read: the logs do not print it, only the run's Summary table does.

## Fix
Read the Pack/Source/OK/Error table in that run's Summary (or run `python -m tools.market collect --packs gcc` where TradingView's scanner is reachable), then fix the adapter in `lightning/market/sources` with a test.
