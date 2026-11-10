---
title: Held for others gives instructions where it should give actions
type: polish
pillar: own
size: S
model: sonnet
status: new
created: 2026-11-10
by: Claude
skills: bug-hunt
app_version: 2.1.2
commit: a4f696b
repo: app
---

## Report
[r34](r34-accounts-and-transactions/report.md) H1. Evidence: [page](r34-accounts-and-transactions/evidence/pc-held-for-others.png). The page lists Mom · CIB Payroll · 10,000 and then
explains: "Use the account's transaction form and choose the person in Held for ... record a return with a negative
amount." The row has no action; the only button is *Open transactions*.

## Fix
Each row gets *Give back* and *Receive more* (prefilled entry: account, person, amount), and the page gets *Hold money
for someone*. The explanation goes. Money lent to others and split costs are NF-12G; this item is only the money you
hold. Tests: the two buttons post the same ownership entries the register does.
