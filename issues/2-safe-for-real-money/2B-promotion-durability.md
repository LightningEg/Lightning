---
title: Promotion durability: code and fault tests pass; the ordinary Windows reboot drill remains
type: tech
area: restore
status: building
created: 2026-10-19
by: Codex
---

## Report
Codex task 02d. Abrupt power-loss behaviour is unverified.

`tools/promotion_drill.py` prepares a new encrypted dummy profile, stops after a selected durable phase (P1–P4), and records filesystem, boot, hashes and recovery outcome after an ordinary Windows restart. It refuses an existing nonempty folder. No real profile is used.

On an ordinary Windows PC with the encrypted dependencies installed, run `python tools/promotion_drill.py prepare --root C:\\Lightning-drill-P3 --phase P3`, reboot, then `python tools/promotion_drill.py resume --root C:\\Lightning-drill-P3`. Use a separate empty folder for each phase. The deliberate nonzero prepare exit preserves interruption evidence. Keep `drill-evidence.json` with the acceptance record.

The drill has not been physically run. An ordinary reboot is not abrupt power-loss evidence. The owner release-risk gate remains in Architecture.

**Read:** Architecture › Promotion durability risk; `tests/test_database_promotion.py`.
