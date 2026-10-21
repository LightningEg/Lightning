---
title: Mohab's sample shows an unresolved portfolio reconciliation difference of +1,394
type: bug
area: investments
status: ready
created: 2026-10-15
by: Claude
skills: website-sync
app_version: 1.1.0b1
commit: f5f551c
repo: app
---

## Report
`LIGHTNING_PRICES_OFFLINE=1 LIGHTNING_TODAY=2026-10-04 python -m lightning --sample`, Investments, YTD: "Portfolio reconciliation differs from closing value by +1,394. The source is unresolved." (`investments/index.html`, `recon_difference`). Same with online prices.
The sample gained a dollar brokerage (8 QQQM bought 2026-03-12, USD cash); the gap may be the FX revaluation of the USD holding, which f1a4ba9's certificate-interest fix would not cover. Severity: medium (the sample is what the website shows; this line undercuts "numbers you can trust"). Skill to use: number-audit.

## Investigation
Claude, number-audit, 2026-10-20 ([Audit 1](../../reports/audit-1.md) §1): the gap is the exchange-rate revaluation of the brokerage's **USD cash**.
Monthly: Jan 600 and Feb 500 (on 2,000 USD), then Mar–Sep 58.75, 58.75, 35.25, 47, 23.5, 35.25, 35.25 (on 235 USD); sum 1,393.75. The formula in
`ui/routes/investments.py:109-113` counts brokerage cash in the closing value (`investment_cash`) but has no term for its revaluation.

## Fix
Add the period's FX revaluation of investment cash as its own reconciliation line (or include it in Result), and a test that the sample's difference is 0.
