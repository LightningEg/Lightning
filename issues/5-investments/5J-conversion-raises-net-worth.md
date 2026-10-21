---
title: Converting EGP to dollars raises net worth - the conversion's own rate revalues every dollar holding
type: bug
area: investments
status: new
created: 2026-10-20
by: Claude
skills: number-audit
app_version: 1.3.0
commit: 7591231
repo: app
---

## Report
Found by [Audit 1](../../reports/audit-1.md) (§1 Engine). Sample, prices offline: Convert 5,200 EGP → 100 USD, fee 10. Net worth +875, Holdings value
+792, Dollar brokerage +6,086. The executed rate 52.00 is saved as a TRADE rate and, on that day, beats the MARKET and ONLINE rates
(`docs/ARCHITECTURE.md:293-295`), so every USD holding is revalued up from 51.60. Expected: net worth falls by the fee plus the spread paid. Voiding the
conversion restores everything exactly. Severity: medium. It is documented, but it shows in a demo as "I bought dollars and got richer".

## Fix
Owner decision first: should a conversion's rate value other holdings? Proposal: value holdings with the market rate and keep the trade rate for the
conversion's own legs, so the spread shows as a cost.
