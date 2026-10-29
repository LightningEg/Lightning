---
title: Converting EGP to dollars raises net worth - the conversion's own rate revalues every dollar holding
type: bug
look: technical
severity: medium
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
Found by [Audit 1](../../reports/2026-10-20-demo-readiness/report.md) (§1 Engine). Sample, prices offline: Convert 5,200 EGP → 100 USD, fee 10. Net worth +875, Holdings value
+792, Dollar brokerage +6,086. The executed rate 52.00 is saved as a TRADE rate and, on that day, beats the MARKET and ONLINE rates
(`docs/ARCHITECTURE.md:293-295`), so every USD holding is revalued up from 51.60. Expected: net worth falls by the fee plus the spread paid. Voiding the
conversion restores everything exactly. Severity: medium. It is documented, but it shows in a demo as "I bought dollars and got richer".

2026-10-29, [use-case audit](../../reports/2026-10-29-use-case-audit/report.md) F5: a typo makes it worse. Sent 100 EGP and received 5,000 USD
(the two amounts swapped) saves without a question though the quote says 100% below the market rate; its rate (0.02) then values every
dollar holding at 0.02 EGP, so net worth falls from 100,000 to 95,002 that day and stays there. Whatever the owner decides, ask before
saving a conversion far from the day's rate.

2026-10-29, built: Convert (new and edit) asks once when the rate is 20% or more from the day's market rate; pressing
Convert again saves it as typed (`lightning/ui/routes/accounts.py` `check_conversion_rate`,
`tests/test_fx_conversion.py::test_a_rate_far_from_the_market_is_asked_once_before_it_is_saved`). The owner decision above stays open.

## Fix
Owner decision first: should a conversion's rate value other holdings? Proposal: value holdings with the market rate and keep the trade rate for the
conversion's own legs, so the spread shows as a cost.
