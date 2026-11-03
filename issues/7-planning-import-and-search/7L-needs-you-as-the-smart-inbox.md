---
title: Smart suggestions exist but sit 2-3 clicks down - make Needs you the one inbox, widen Looks recurring
type: feature
pillar: plan
size: L
status: ready
created: 2026-10-20
by: Claude
skills: bug-hunt
app_version: 1.3.0
commit: 7591231
repo: app
---

## Report
Found by [Audit 1](../../reports/2026-10-20-demo-readiness/report.md) (§2 Logic). The services work, but a viewer finds them only on secondary pages: Looks recurring at the
bottom of Recurring, rule offers only on Weekly review, payday funding and reimbursements only from Weekly review. Needs you, the one inbox, carries
none of them. Wiring, not new engines. Builds on 3G §4.5 (Weekly review into Needs you) and 3H CP-10.

## 7L2 Needs you carries the suggestions · L · #224
In `workflows/review.py::ReviewInbox.items` add: "N payments look recurring · Track" (`planning.suggestions`, links to `/plan/recurring#recurring-suggest`);
`WeeklyReview.rule_offers` · Make a rule; reserve used →
Refill (3H RS-2, `reserves.links_for_reserve`); a category over plan this month (today only on Budget and in the save message); Health's "Needs you"
bands (emergency fund 0.8 months is flagged on Health but not in the list).

## 7L4 Pair what belongs together · M · #226
Reimbursements: the sample's Uber 1,200 (06-08) and ACME's 1,200 back (06-21) are never paired; suggest the pair. Import: after posting, say which bills
the import settled ("2 posted, 1 linked · settled Landlord and WE Internet"). Certificate Match all lands on the long certificate page; return to Needs you.

## Fix
One branch per step (7L1, the false raise prompt, is done). Mohab: add a step where a tracked suggestion and a rule offer appear in Needs you and are accepted there.


## Implementation of 7L2 · 2026-11-03

Needs you now includes existing recurring candidates and reusable-rule offers, partially used replenishable/emergency reserves, current category overruns, and the emergency-fund alert band. Items use the existing situation identity, Mark as reviewed, Snooze and Restore controls. Rule offers are grouped with activity; no suggestions post money or create plans/rules automatically. Remaining health-band coverage and the 7L4 pairing improvements stay open.
