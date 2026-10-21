---
title: PC screens break the guideline in 20 places not yet filed - a page that scrolls sideways, misleading charts, colours off meaning
type: polish
area: product
status: ready
created: 2026-10-20
by: Claude
skills: guideline-audit
app_version: 1.3.0
commit: 7591231
repo: app
---

## Report
Found by [Audit 1](../../reports/audit-1.md) (§3 PC) on Mohab's sample and the demo at 1366 and 1920 px. Only what 3C, 3Q, 3G and 3H do not
already list. The brand audit passes; it cannot see `<select>` text colour, the first-run page, `<fieldset>` boxes or overlapping chart labels.

**High**
1. **Settings › Sale factors scrolls sideways (A15).** "After sale" for Deposits prints "0NBE 3-year certificate · 22% · …" with no break and runs out
   of the card (page 1532 px wide at 1366). `templates/settings/index.html:27,30`: the `<small>` needs its own line and must wrap.
   Shot: [pc-sale-factors-overflow.png](../../reports/audit-1/pc-sale-factors-overflow.png).

**Charts that mislead (A12)**
2. Chart end labels drawn on each other, as 3C, in new places: holding "Value against cost" (102,085 over 88,868), the demo's Budget pace chart
   ("Plan 8,719" over "8,774"). Shot: [pc-chart-end-labels-overlap.png](../../reports/audit-1/pc-chart-end-labels-overlap.png). Fix with 3C.
3. Health › Over time: Savings rate and Net worth trends have no axis and do not start at zero, so net worth looks steep beside the Overview's flat one.
4. Currencies "USD · Value against cost" plots USD cash only: it falls from about 100,000 to 12,126 when the cash bought the ETF, while the card above says
   Foreign money 114,211; the axis runs to 200,000.
5. Holding "Price against what you paid": the dashed average-cost line is Meadow; dashed Meadow means the plan. Use Neutral #C5D3D0 (A12.1.2).

**Colour off its meaning (A03)**
6. Overview "Left in plan": the used part of the meter is Meadow; spent of plan is soft rose, as on Budget. Shot: [pc-overview-kpis.png](../../reports/audit-1/pc-overview-kpis.png).
7. Categories: "− Expense" is #A02E5A and "± Both" #0A5AB0, neither an A03 colour. First run: the sample cards' "Load" is Azure (links are Ink, underlined).
8. Gam'eya: five late instalments are Muted grey with no Late chip, and "Next instalment" shows a past date. Holding "Worst month −1.1%" is strong rose.

**A16 shipping list**
9. Five or more names: Investments › Biggest holdings (six bars plus "3 more"), the Planner's five-class split.
10. "L1 › L2": the transaction page's "Personal › Entertainment"; every row of Review activity (which also shows money out without "−").
11. Card in a card: Settings › Budget's four boxes; Spending's small multiples; Certificates' nine `<fieldset>` boxes; first run's account-type list.
12. Dropdown for your data: Certificates "Buy from" and "Forecast payout account"; the empty profile's Budget spending groups.
13. A card alone: Cash planning "What you owe"; the transaction page's "Expense categories".

**Controls and words**
14. The period control reads "Monthly" with the ‹ month › stepper as a separate pill; A10.2 says "Month", arrows inside the one track (Overview, Spending,
    Budget, Investments, Currencies, Export for AI).
15. A05: the line under the title is a slogan ("Where your money went", "Your spending plan", Currencies, Prices, Held for others, From SMS, Review
    activity, Deleted, Settings tabs) instead of the exact dates; Overview and Cash planning have none.
16. Certificates: a 5,400 px page with ten Primary buttons (A10.1 allows one).
17. Settings › Counterparties: Person/Business buttons cover the suggested-category field; "Save alias" is clipped.
18. Budget for a month with no plan says "Set your first spending limit" though later months have one.
19. Ctrl-K: the first Escape only clears the query (A10.5: Escape always means no). Hide amounts posts through the undo journal, so "Saved changes" appears in every header.
20. Small: transaction title is the reference at 14 px, "OUTFLOW" in capitals, raw "2026-10-20T21:36:42+00:00"; Planner has no h1 and shows decimals;
    missing spaces around links ("Openthe register", "onRecurringto"); Review activity, Weekly review and Sale factors light the Summary tab; From SMS has no
    way back; at 1920 content is 1,435 px wide (owner question 7 in the report).

## Fix
Fix in the stylesheet or template that owns each, regenerate the RTL mirrors, rerun `tests/test_brand_audit.py` and Mohab. Extend the brand audit to
`<select>` text, the first-run page, `<fieldset>` and label overlap so these stay fixed.
