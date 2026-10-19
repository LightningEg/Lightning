---
title: In Arabic the holdings table's price and FX split reads out of order
category: visual-bug
area: arabic
status: reported
created: 2026-10-15
reporter: Claude
skills: website-sync
app_version: 1.1.0b1
commit: f5f551c
issue: 34
repo: app
---

## Report
Investments › holdings table, Arabic, Mohab's sample on 2026-10-04 (`tools/site_shots.py --lang ar`, `a-holdings-usd.webp`). Under the Invesco NASDAQ 100 ETF's +١٣٬٢١٨ the split renders as
"+٢٬٢٠٦ تغير السعر: جزء السعر +١١٬٠١١ · جزء العملة": the FX part's figure jumps to the start, so it reads as the price change. The English line is "Price change: Price part +11,011 · FX part +2,206".
`investments/index.html` `gain-split`: isolate each signed figure in `<bdi dir="ltr">`, as other Arabic figures are. Severity: low.
