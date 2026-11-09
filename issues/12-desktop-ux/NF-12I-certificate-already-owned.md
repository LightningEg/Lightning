---
title: Record a certificate you already own, bought before you started tracking
type: feature

pillar: own
size: M
model: opus
status: ready
created: 2026-11-09
by: Claude
skills: bug-hunt
app_version: 2.1.2
commit: 90f0190
repo: app
---

## Report
[r30](r30-investments-beyond-stocks/report.md) C1. Most people start Lightning with certificates they already hold. The only way to
add one is *Buy a certificate*, which always takes the money from a bank or cash account on the purchase date
(`lightning/deposits/service.py` `purchase`). Dated before tracking began it is refused: "CIB Payroll had 0.00 EGP of your
cash on 2024-01-15; this purchase needs 50,000.00 EGP." Dated today it wrongly takes the money out of the bank now.
*Holding I already own* (Investments) does not list a CD portfolio, and a new CD portfolio has no starting balance.

## Fix
On the certificate form, a choice *I already own it*: no "Buy from"; it posts an opening (`OPN`) unit line at the
principal on the day tracking starts (as `_is_holding_opening` holdings do), keeps the true purchase date in the terms so
the payout schedule and maturity are right, and counts as a baseline, never new money. Tests: an owned certificate dated
two years back saves with no bank movement, shows in Holdings value, forecasts only future payouts, and redeems normally.
