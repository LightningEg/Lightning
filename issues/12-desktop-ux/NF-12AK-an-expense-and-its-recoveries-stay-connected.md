---
title: An expense and its refunds and reimbursements stay connected, and estimates stop counting one-time purchases as monthly
type: feature
pillar: plan
size: L
model: opus
github: 637
status: new
created: 2026-11-13
by: Claude
---

## Report
#626 (2026-11-13), parked for the owner's design pick. Category exclusion is the only way to leave a purchase out of estimates, so one 9,000 laptop next to 1,000 a month of normal spending makes the average 4,000, and excluding the category loses the normal 1,000. A full refund two months later makes the January average **−6,000**. A 1,200 expense with a pending 1,200 claim counts fully in the estimate with no "expected back". A refund of a reserve-funded purchase shows −200 monthly-plan spending. Reproductions: the scripts in #626.

## Fix
To agree first (owner): how a transaction-level estimate exception works without changing ledger or cash-flow actuals, and how it sits beside category exclusions; how returns match their purchase for estimates (not for cash); where a reserve-funded refund goes. Then: paid / returned / expected back on the expense and in Budget, an optional *Leave out of estimates* on capture and edit, a grouped review with undo. Split with skill `split-large-item` once the contract is agreed. Never exclude a purchase because it is large.
