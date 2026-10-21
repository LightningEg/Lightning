---
title: Bill matching misses payments from another account, offers last month's payment as this month's, and counts early salary twice
type: bug
area: planning
status: ready
created: 2026-10-20
by: Claude
skills: bug-hunt
app_version: 1.3.0
commit: 7591231
repo: app
---

## Report
Found by [Audit 1](../../reports/audit-1.md) (§2 Logic), by posting through the app on Mohab's sample and the demo. Severity: high. Each leaves a
paid bill late or counts money twice, and the way out the app offers (record it again) spends it twice.

1. **Paid from another account, never linked.** Vodafone (planned from Vodafone Cash) paid 350 from CIB on 10-12: it stays "not paid yet · Late 11 days"
   in Needs you, Free cash takes the 350 off a second time, the pay popup offers only September's payment, and the activity page offers nothing.
   `planning/repository.py::candidates` (line 135) always filters by the item's account; `workflows/activity.py::_planned_choices` does too. 3H CP-7
   covers only the Record form.
2. **Last month's payment offered as this month's.** `plausible_candidates` (`planning/service.py:270`) looks 45 days either side of the due date and
   does not skip transactions already linked to another payment or dated before the item's start. Landlord's 10-03 popup offers the 09-03 rent of
   12,000; one click removes October's rent from Bills due. Every newly tracked item shows "Possible early/changed payment" at once. The popup text
   (`templates/planning/pay.html`) says the payment matches "only one of its category or counterparty details"; it matches both, only the date is out.
3. **Early salary counted twice.** Demo: salary paid 12 days early: Safe to spend jumps 41,953 → 86,953 and the forecast still adds November's 45,000
   (November's closing 54,783 → 99,783). The only signal is a small hint on Recurring; Needs you says nothing.

## Fix
Manual review searches every owned cash account in the item's currency (automatic matching stays strict to the account); drop candidates already linked
or nearer the previous due date than this one; fix the popup text; when the matcher sees an early income or bill, put "Link" in Needs you (7L).
Tests: a cross-account payment links by hand; last month's payment is not offered; early salary is not counted twice in the forecast.
