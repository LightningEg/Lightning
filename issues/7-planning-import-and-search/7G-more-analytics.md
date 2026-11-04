---
title: Age of Money and a spending calendar
type: feature
pillar: understand
size: M
status: building
created: 2026-10-19
by: Claude
---

## Report
Saved views, report and export are built; these analytics are not. Idea from Actual Budget.

## Implementation · 2026-11-04

FIFO pools owned cash by currency across accounts. Transfers preserve age; conversions carry consumed dates into received units. Opening cash and cash deficits have unknown age. Buys consume cash without entering the expense sample; sale proceeds and refunds start cash lots on receipt. Age is amount-weighted over the last ten positive cash expense transactions in profile currency, with the prior ten as context; any unknown lot makes that sample unavailable. Calendar reads Spending lines, including refunds, on posting dates and links to the register. PC shows month weeks; phone shows dated spending rows. Focused FIFO, conversion, cutoff, calendar and bilingual frame tests pass; acceptance and PR checks remain.
