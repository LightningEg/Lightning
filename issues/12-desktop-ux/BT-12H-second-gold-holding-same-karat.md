---
title: A second gold holding of the same karat cannot be added (GLD:24K already exists)
type: bug
look: technical
severity: medium
pillar: own
size: S
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
[r30](r30-investments-beyond-stocks/report.md) G1. Investments › New investment › Type Gold, karat 24, name "BTC 10g bar": saved as `GLD:24K`.
A second one (name "Second 24K bar (5g)", karat 24) is refused: "GLD:24K already exists.", shown on the Ticker field
whose help says "For gold leave empty." The code is built from the karat alone (`lightning/assets/service.py`
`create_investment`, the `GOLD` branch), so one profile can hold one gram-gold investment per karat; a 24K one also
collides with a `GLD:24K` price reference when the profile has one.

## Fix
Build a gram-gold code from the name when no ticker is typed (as Other does: `OTH:APARTMENT-NEW-CAIRO`), keeping the
karat in `purity`. Test: two 24K gold investments with different names both save; live prices still price both by purity.
