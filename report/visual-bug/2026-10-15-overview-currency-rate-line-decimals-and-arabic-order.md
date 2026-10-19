---
title: Currencies shows rates with six decimals, and the rate line reads out of order in Arabic
category: visual-bug
area: overview
status: reported
created: 2026-10-15
reporter: Claude
skills: website-sync
app_version: 1.1.0b1
commit: f5f551c
issue: 33
repo: app
---

## Report
Overview › Currencies › USD: "1 USD = 51.600000 EGP" and "Average rate 49.8000". Two decimals would match how rates are quoted in Egypt (A06).
In Arabic the same line renders as `USD = ٥١٫٦٠٠٠٠٠ EGP ١`: the bidi run is not isolated, so it reads backwards. Wrap it in `<bdi dir="ltr">` like other figures. Severity: low.
