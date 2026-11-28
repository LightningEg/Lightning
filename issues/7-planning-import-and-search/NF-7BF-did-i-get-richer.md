---
title: Did I get richer? The month's report answers in pounds and in grams of gold, and says why
type: feature
pillar: understand
size: M
model: opus
status: building
created: 2026-11-28
by: Claude
---

## Report
[r41](r41-the-next-big-thing/report.md) phase 3 (owner adopted 2026-11-27; no share card). The phone's Report (Money ›
Report) leads with Change in what you own and lists Kept and Investing result apart; nothing says whether the month left
you richer, why, or what it means in gold, the way most Egyptian households measure savings. NF-12AL (#638), which r41
named for this phase, delivered Budget's "what changed" card instead; its steps are all done.

## Fix
- The lead gets its verdict: "Richer. You own 30,731 more than on 30 Sep." (Poorer, less; No change).
- "In gold: 2.1 grams of 21K more" (or fewer): what you own at each end divided by the stored 21K price on that day
  (PositionService.in_other_units, ZakatService.gold_price_24k), left out when a price is missing.
- "Why it changed": Kept + Investing result + Other changes (prices, gold, currencies, loans) add up to the lead.
- All of it in Python; the template only shows it. Inflation waits for the owner's pick of a source.
Done when: a test on Mohab's sample finds the verdict, the gold line and the three parts adding up to Change in what you
own; Arabic; Part C at 360 and 320 px; Mohab's year passes.
