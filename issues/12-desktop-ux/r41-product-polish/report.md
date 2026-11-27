# Product polish across a household's daily workflows

Date: 2026-11-27
Reviewed commit: e1426e49 (v2.3.3)
Code: r41
Pillar: feel

## Evidence

A fresh checkout of the release and a disposable encrypted sample household. Chromium rendered Cash planning, Recurring, Upcoming, Investments, Accounts and Transactions at 1366 pixels. The phone checker exercised Home, Budget, Plan, To do, Activity and Settings at 360 and 320 pixels in English and Arabic. Desktop used English. Native device behavior, screen readers, real statements and actual customer balances were outside this review.

## Priority findings

1. Update and recovery remain a financial trust issue. PR 772 addresses the Windows helper, desktop links and some mixed-patch negotiation. The historical schema 87/95 pair still cannot share a live ledger. Expose the last confirmed change, pending edits and which device needs action at the point of failure. A backup opened for comparison must identify how to resume editing. Verify one interrupted update and one replacement phone with a dummy book. [Update audit](../../2-safe-for-real-money/r40-update-survival/report.md).
2. A due outside backup runs synchronously while the request holds the session mutex. A failed attempt normally waits until tomorrow or folder reselection. Provide an immediate retry and keep verified backups off the time-critical page render, with a consistent snapshot and profile-lock coordination. Actual native latency needs measurement. [Request handling](../../../lightning/runtime/app.py), [outside copy](../../../lightning/runtime/outside_copy.py).
3. Home places Safe to spend today (51,420 EGP in this example) beside About 331 a day until payday. The latter is Budget's remaining everyday allowance of 1,324 over four days. Label the basis and link to the current Budget. Keep the separate cash and budget calculations. [Home](../../../lightning/ui/templates/phone/home.html).
4. English Budget's Dismiss control extended 6 px past the right edge at 320 px. The Settings theme picker extended 33 px on the right in English and 26 px on the left in Arabic. Test the affected controls at text zoom, with keyboard focus and long labels. No equivalent clipping was flagged on these six pages at 360 px. [Phone checker](../../../tools/phone_check.py).
5. Unit prices in the desktop holdings overview use zero decimals at 10 and above. Preserve precision sufficient to explain gains when average cost and price appear equal. Keep whole-pound rounding for headline wealth totals. [Holdings](../../../lightning/ui/templates/investments/index.html).
6. Split accounting and journal operations exist. The ordinary Money out form and a per-person net position are unfinished. Use one 1,200 EGP payment with two 400 EGP shares to verify register, budget and person balances. [Feature record](../NF-12G-money-lent-and-split-with-others.md).
7. Statement cleanup already supports mapping, reviewed posting and remembering a category. Editing counterparties afterwards is per-name. Offer selection of recurring spelling variants, a preview of affected entries and rules, then an explicit merge. [Phone counterparties](../../../lightning/ui/templates/phone/counterparties.html).
8. Cash planning identifies an account shortfall and opens its account. Carry the account and shortfall date into a view of the contributing payments, then into a proposed transfer or schedule change. Recalculate after confirmation. [Cash planning](../../../lightning/ui/templates/planning/plan.html).
9. The phone's PC-only page says the data is the same and offers Back. Make that statement depend on confirmed sync and identify the precise PC destination. [Phone handoff](../../../lightning/ui/templates/phone/on_pc.html).
10. Separate tested, waived and pending acceptance in the release view. Prioritize a single installation/update/restore test with real hardware and the same shortcut. Commercial checkout and Play prices have a separate owner decision at launch. [Launch checklist](https://github.com/LightningEg/Lightning/issues/579).

## Work already present

Recurring rendered 13,480 EGP as 30% of 45,000 income and separately showed fixed costs at 35.5%. Upcoming correctly showed 17,980 due and “The same as October”. Cash planning links to payday funding and reserves. Investments already shows average cost and price now. Older issue descriptions alone would have incorrectly classified these as missing.

## Recommended order

First protect continuity through updates and make recovery actionable. Then fix the reproduced clipping, label the budget pace and preserve unit-price precision. Next connect shared-expense capture, statement cleanup and shortfall resolution. Validate with one tester household from first setup through payday, an offline edit, update and recovery. Track where they stop, which figure they interpret incorrectly and whether they finish the task unaided.
