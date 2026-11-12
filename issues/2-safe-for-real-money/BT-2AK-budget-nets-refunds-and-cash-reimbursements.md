---
title: A purchase that is returned or reimbursed must not leave the budget over by its full amount
type: bug
look: technical
severity: medium
pillar: plan
size: M
model: opus
status: new
created: 2026-11-12
by: owner
---

## Report
Owner, 2026-11-12: buy something for 500, return it, and the budget still shows 500 over. Cash reimbursements and refunds should reduce spending to the net.

Finding: not reproduced when the refund is recorded as money in under the same expense category (`money_out_by_category` nets it to 0, checked on the sample ledger). So the owner's case takes another route: a refund filed under an income category, a transfer, or the reimbursement flow (`lightning/reimbursements.py`). Not solved in the session that heard this.

## Fix
Find which route the owner used (ask for the two transactions' categories), then make the Budget net it: a refund or reimbursement linked to a purchase reduces that purchase's category in the month of the purchase. Test: buy 500, return 500 through each route; Budget actual is 0.
