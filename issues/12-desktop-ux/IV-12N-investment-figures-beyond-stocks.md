---
title: Investments figures that mislead outside stocks: purchases shown as change in value, yearly rates on weeks, two Others
type: polish

pillar: understand
size: M
model: sonnet
status: new
created: 2026-11-09
by: Claude
skills: bug-hunt
app_version: 2.1.2
commit: 90f0190
repo: app
---

## Report
[r30](r30-investments-beyond-stocks/report.md) N1-N4.
- **Purchases counted as "Change in value".** *Money and value by class* draws end value less start value per class
  (`lightning/ui/routes/investments.py`, `class_changes`): buying a 62,000 bar moved Gold from +5,535 to +67,535 while
  *What changed* kept the price change at +6,063. The card's two halves disagree with the card above it.
- **A yearly rate on 69 days.** A gold pound held 69 days shows "+273.3 per year" in *Each purchase*; the certificate's
  +3.7% over 69 days stands beside its 22% rate with no yearly figure.
- **Two Others.** With five classes the donut folds Money Market Fund into "Other 0.1%" next to "Other Investments 95.8%".
- **"Not counting 5,500,000 of opening balances"** appears in the hero's caption after adding owned property; the
  sentence is long and the figure unexplained.

## Fix
Draw price change per class (the report's own parts), with money in beside it. Show a yearly rate only after a year (or
90 days, labelled "if it continued"); for a certificate show its rate. Name the folded slice "Smaller classes". Shorten
the opening-balance note and link it. Tests: `tests/test_investment_views.py` for the chart rows after a purchase;
Mohab's Investments step for the labels.
