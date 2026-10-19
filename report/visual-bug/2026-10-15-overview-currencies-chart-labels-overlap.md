---
title: Currencies chart draws its two end labels on top of each other
category: visual-bug
area: overview
status: reported
created: 2026-10-15
reporter: Claude
skills: website-sync
app_version: 1.1.0b1
commit: f5f551c
issue: 35
repo: app
---

## Report
Overview › Currencies, YTD, Mohab's sample (`--sample`, `LIGHTNING_TODAY=2026-10-04`): in "USD · Value against cost" the last point carries 12,126 (value) and 11,703 (cost) in the same place, so it reads "12,7G6".
When the two series end close together, show one label, or offset the second. Severity: low.
