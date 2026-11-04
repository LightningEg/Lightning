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
already list. The original brand audit could not see select text colour, the first-run page, fieldset boxes or overlapping chart labels. The Chromium audit now checks category select colours, first-run Load, visible boxed fieldsets and chart-end overlaps on its visited pages; wider coverage remains to review.

**Charts that mislead (A12)**
3. **2026-11-04:** PC Financial health uses zero-based axes for its Savings rate and Net worth trends, keeps gaps for missing months, and requires three known points. The current lead shows Savings rate; Net worth remains in the no-lead fallback.
4. Currencies "USD · Value against cost" plots USD cash only: it falls from about 100,000 to 12,126 when the cash bought the ETF, while the card above says
   Foreign money 114,211; the axis runs to 200,000. **2026-11-04:** The PC chart now labels the series as cash only and explicitly excludes investments; a combined history and the axis still need review.
5. **2026-11-04:** Holding average cost uses a Neutral dashed reference; plan references remain Meadow. The Chromium brand audit checks its computed stroke.

**Colour off its meaning (A03)**
6. **2026-11-04:** The current Overview KPI uses the spending tone for the used meter within plan (`kpis.overview` and `.kpi-card.tone-out`); over plan uses Strong rose. The original shot predates the KPI rebuild in `5e847d41`.
7. **2026-11-04:** Category Expense and Both controls use Ink, Income uses Meadow text, and the first-run Load link is Ink and underlined. The Chromium brand audit checks computed styles.
8. **2026-11-04:** PC Gam'eya marks a passed scheduled date as "Date passed · not recorded" and calls the past date the oldest unrecorded instalment; due-today is not called late. The current screen reports the count and total rather than listing the old five rows. **2026-11-04:** Ordinary negative holding monthly changes use Ink and keep their sign.

**A16 shipping list**
9. **2026-11-04:** The current Investments lead removes Biggest holdings when the portfolio can be valued; a six-holding browser fixture confirms it is absent. The older fallback limits its bars to four named holdings and a Neutral Other. The Planner stack now shows four named parts and a Neutral Other with the exact remainder; all detailed allocation rows and inputs remain available.
10. **2026-11-04:** PC Review activity uses category leaf names and shows a minus on money out. Transaction details retain category hierarchy as a header and separate lines rather than a breadcrumb.
11. **2026-11-04:** PC Budget settings and certificate receipt fieldsets retain their semantic groups without boxes; Spending small multiples and the first-run account list no longer have nested surfaces. Chromium checks computed borders, backgrounds and shadows.
12. **2026-11-04:** PC Certificates account fields and the empty-plan Budget spending group use the existing type-and-pick control. Chromium checks filtering, submitted IDs and required validation.
13. Cash planning "What you owe" remains to review. **2026-11-04:** On PC, transaction "Expense categories" and reserve assignment share a row when both are available and the window is wide enough; they stack at narrower widths.

**Controls and words**
14. **2026-11-04:** The shared PC period control says "Month" and places ‹ month › inside the one track. Chromium checks navigation, custom ranges and Arabic on Overview; the same macro serves Spending, Budget, Investments, Currencies and Export for AI.
15. A05: review the status and date lines on Spending, Currencies, Prices, Held for others, From SMS, Review activity, Deleted and Settings tabs. **2026-11-04:** The PC Spending header now shows the selected exact dates, including for empty periods; its status sentence remains to review. The Currencies header distinguishes balances at the end date from realized gain and spread over the period, and its balance note uses that end date rather than saying today. **2026-11-04:** Overview, Budget and the Cash planning forecast now use a status and dates in their headers (6a0bf774); the original observations predate that rebuild.
16. **2026-11-04:** PC Certificates keeps the purchase as its Primary; receipt matching and redemption actions are Secondary, including when the row is expanded. Chromium checks one visible Primary on a sample with three receipt groups. Page length remains to review.
17. **2026-11-04:** Expanded sample Counterparties rows have no Suggested category/Person/Business overlap at 1024, 1366 or 1920 px. PC Save alias is intentionally screen-reader-only; its Enter hint appears and Enter saves an alias in Chromium.
18. **2026-11-04:** An unplanned month says "Set spending limits for this month", whether or not other months have plans.
19. **2026-11-04:** Escape closes Ctrl-K even with a query; the Chromium brand audit checks it. **2026-11-04:** Hide amounts saves its profile preference without creating an undo action or running payment matching; the previous undo remains available. Synchronized profiles still propagate the preference.
20. Small: **2026-11-04:** The transaction heading names the action at 28 px, its exact reference remains visible below and in the browser title, and ledger effects use sentence-case words instead of "OUTFLOW"; **2026-11-04:** Recorded and updated timestamps show date, time and UTC offset in readable form; **2026-11-04:** Planner has an h1 (5d6cef98) and its suggested amounts use whole EGP (2ce89717);
    **2026-11-04:** Spaces around the Integrity register and Cash planning Recurring links are restored; Review activity, Weekly review and Sale factors light the Summary tab; **2026-11-04:** PC From SMS links back to Accounts; at 1920 content is 1,435 px wide (owner question 7 in the report).

## Fix
Fix remaining findings in the stylesheet or template that owns each, regenerate the RTL mirrors when needed, and rerun `tests/test_brand_audit.py` and Mohab. Expand the new select, first-run, fieldset and label-overlap checks to additional pages and chart types.

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
The Chromium audit now checks category select colours, first-run Load, visible boxed fieldsets and overlapping trend/pace end labels on visited pages. The controls are tested against both passing and failing browser geometry. More page and chart-label coverage remains to review.
