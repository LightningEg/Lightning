---
title: The demo and the sample hide the smart features and show false alarms - fix the data before any demo
type: tech
area: product
status: ready
created: 2026-10-20
by: Claude
skills: bug-hunt
app_version: 1.3.0
commit: 7591231
repo: app
---

## Report
Found by [Audit 1](../../reports/audit-1.md) (§1, §2). What a viewer sees first is set by `lightning/demo.py` and the Mohab sample, not by the engine.

1. **Demo certificate never matches.** `demo.py:70` buys it at 18% paid on the 1st; `demo.py:93` posts 1,833.33 on the 15th (22%). The demo's only
   Needs-you item, "2 interest payments to match, 3,008 still unmatched", can never be matched by Match all, and the forecast uses 1,529 / 1,479 a month.
2. **The sample shows late bills today.** Its last transaction is 2026-10-02; on 2026-10-20 it shows 4 late bills (15,090), Needs you 7, and Free cash
   net of 15,740 bills. Its own items pin `LIGHTNING_TODAY=2026-10-04`: make `--sample` pin a date inside its data, or roll the data to today.
3. **No Looks recurring in the demo before the 25th.** Mom is posted on day 25 and the CIB fee is under the 50 EGP minimum. Add one untracked
   subscription early in the month (Shahid 99 or a gym 900) so the suggestion always shows, and leave one bill untracked.
4. **"Your income went up" is the first nudge on the sample's Overview, and it is false** (the yearly bonus ÷ 12; fix in 7L1).

## Fix
Edit `demo.py` and the sample loader; a test that the demo's Match all clears its interest item and that `--sample` opens with no late bill.
