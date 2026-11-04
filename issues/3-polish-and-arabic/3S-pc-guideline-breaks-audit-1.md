---
title: PC screens break the guideline in 18 places not yet filed - misleading charts, colours off meaning
type: polish
pillar: feel
size: L
status: ready
post: no
created: 2026-10-20
by: Claude
skills: guideline-audit
app_version: 1.3.0
commit: 7591231
repo: app
---

## Report
Found by [Audit 1](../../reports/2026-10-20-demo-readiness/report.md) (§3 PC) on Mohab's sample and the demo at 1366 and 1920 px. Items 1 (Sale factors scrolled sideways) and 2 (chart end labels) are fixed; the numbers below keep their places. Only what 3C, 3Q, 3G and 3H do not
already list. The brand audit passes; it cannot see `<select>` text colour, the first-run page, `<fieldset>` boxes or overlapping chart labels.

**Charts that mislead (A12)**
3. **2026-11-04:** PC Financial health uses zero-based axes for its Savings rate and Net worth trends, keeps gaps for missing months, and requires three known points. The current lead shows Savings rate; Net worth remains in the no-lead fallback.
4. Currencies "USD · Value against cost" plots USD cash only: it falls from about 100,000 to 12,126 when the cash bought the ETF, while the card above says
   Foreign money 114,211; the axis runs to 200,000. **2026-11-04:** The PC chart now labels the series as cash only and explicitly excludes investments; a combined history and the axis still need review.
5. **2026-11-04:** Holding average cost uses a Neutral dashed reference; plan references remain Meadow. The Chromium brand audit checks its computed stroke.

**Colour off its meaning (A03)**
6. **2026-11-04:** The current Overview KPI uses the spending tone for the used meter within plan (`kpis.overview` and `.kpi-card.tone-out`); over plan uses Strong rose. The original shot predates the KPI rebuild in `5e847d41`.
7. **2026-11-04:** Category Expense and Both controls use Ink, Income uses Meadow text, and the first-run Load link is Ink and underlined. The Chromium brand audit checks computed styles.
8. Gam'eya: five late instalments are Muted grey with no Late chip, and "Next instalment" shows a past date. **2026-11-04:** Ordinary negative holding monthly changes use Ink and keep their sign; the gam'eya finding remains open.

**A16 shipping list**
9. **2026-11-04:** The current Investments lead removes Biggest holdings when the portfolio can be valued; a six-holding browser fixture confirms it is absent. The older fallback limits its bars to four named holdings and a Neutral Other. The Planner stack now shows four named parts and a Neutral Other with the exact remainder; all detailed allocation rows and inputs remain available.
10. "L1 › L2": the transaction page's "Personal › Entertainment"; every row of Review activity. **2026-11-04:** PC Review activity shows a minus on money out; category hierarchy remains to review.
11. Card in a card: Settings › Budget's four boxes; Spending's small multiples; Certificates' nine `<fieldset>` boxes; first run's account-type list.
12. Dropdown for your data: Certificates "Buy from" and "Forecast payout account"; the empty profile's Budget spending groups.
13. A card alone: Cash planning "What you owe"; the transaction page's "Expense categories".

**Controls and words**
14. The period control reads "Monthly" with the ‹ month › stepper as a separate pill; A10.2 says "Month", arrows inside the one track (Overview, Spending,
    Budget, Investments, Currencies, Export for AI).
15. A05: the line under the title is a slogan ("Where your money went", "Your spending plan", Currencies, Prices, Held for others, From SMS, Review
    activity, Deleted, Settings tabs) instead of the exact dates; Overview and Cash planning have none.
16. Certificates: a 5,400 px page with ten Primary buttons (A10.1 allows one).
17. **2026-11-04:** At 1366 px, one expanded sample Counterparties row has no overlap between Suggested category and Person/Business. PC Save alias is intentionally screen-reader-only and an Enter hint accompanies the field. Other rows and widths remain to check.
18. **2026-11-04:** An unplanned month says "Set spending limits for this month", whether or not other months have plans.
19. **2026-11-04:** Escape closes Ctrl-K even with a query; the Chromium brand audit checks it. Hide amounts posts through the undo journal, so "Saved changes" appears in every header.
20. Small: **2026-11-04:** The transaction heading names the action at 28 px, its exact reference remains visible below and in the browser title, and ledger effects use sentence-case words instead of "OUTFLOW"; **2026-11-04:** Recorded and updated timestamps show date, time and UTC offset in readable form; **2026-11-04:** Planner has an h1 (5d6cef98) and its suggested amounts use whole EGP (2ce89717);
    **2026-11-04:** Spaces around the Integrity register and Cash planning Recurring links are restored; Review activity, Weekly review and Sale factors light the Summary tab; **2026-11-04:** PC From SMS links back to Accounts; at 1920 content is 1,435 px wide (owner question 7 in the report).

## Fix
Fix in the stylesheet or template that owns each, regenerate the RTL mirrors, rerun `tests/test_brand_audit.py` and Mohab. Extend the brand audit to
`<select>` text, the first-run page, `<fieldset>` and label overlap so these stay fixed.

## 3S1 Charts that mislead (A12) · M
Report items 3-5: Health over-time axes, Currencies USD value against cost, the holding's dashed average-cost line colour. Verify first: audits 10 and 12 (3AL, 3AM) rebuilt many screens. Reproduce this on the current build; if it is already fixed, delete the step and name the commit that fixed it.

## 3S2 Colour off its meaning (A03) · M
Report items 6-8: Left in plan meter, Categories chip colours and first-run Load, Gam'eya late instalments. Verify first: audits 10 and 12 (3AL, 3AM) rebuilt many screens. Reproduce this on the current build; if it is already fixed, delete the step and name the commit that fixed it.

## 3S3 The A16 shipping list · M
Report items 9-13: five or more names, `L1 › L2`, card in a card, dropdown for your data, a card alone. Verify first: audits 10 and 12 (3AL, 3AM) rebuilt many screens. Reproduce this on the current build; if it is already fixed, delete the step and name the commit that fixed it.

## 3S4 Controls and words · M
Report items 14-19: period control, slogans under titles (A05), Certificates' ten Primary buttons, Counterparties overlap, empty-month Budget wording, Ctrl-K Escape. Verify first: audits 10 and 12 (3AL, 3AM) rebuilt many screens. Reproduce this on the current build; if it is already fixed, delete the step and name the commit that fixed it.

## 3S5 Small things · S
Report item 20.

## 3S6 Teach the brand audit what it cannot see · M
Extend `tests/test_brand_audit.py` to `<select>` text colour, the first-run page, `<fieldset>` boxes and overlapping chart labels so these stay fixed.
