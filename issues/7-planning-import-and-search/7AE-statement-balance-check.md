---
title: Use the statement's Balance column to check the import and to start an account
type: feature
pillar: capture
size: M
status: ready
created: 2026-11-05
by: Claude Opus 5.5
---

## Report
Most bank exports carry a running Balance. The map step offers it nowhere, so it is lost. It is the strongest check
there is: after the review, Lightning's balance on the last statement day should equal the statement's. On a first import
into a new account it also gives the opening balance, which today the person types separately. Evidence: [the
report](../../reports/2026-11-05-import-scenarios/report.md), F19.

## Fix
- Optional "Balance" in the map step (aliases Balance, Running balance, الرصيد).
- Review header: "The statement ends at 86,143 EGP; after posting, Lightning will show 86,143" in Good tone when equal;
  when not, the difference and an "Adjust balance" link.
- First import into an account with no entries: offer the balance before the first row as the opening balance.
