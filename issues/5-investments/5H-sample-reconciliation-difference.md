---
title: Mohab's sample shows an unresolved portfolio reconciliation difference of +1,394
type: bug
area: investments
status: new
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
