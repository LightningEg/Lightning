---
title: Coders - every merge counts, offers by label, the leaderboard advertises who built what
type: feature
area: website
status: ready
created: 2026-10-27
by: Claude
repo: both
---

## Report

[Audit](../../reports/2026-10-27-store-and-community/report.md) C1–C2. No offer was ever published, so no merge ever paid or scored.

## Fix

- **Every merge counts:** `rewards.yml` (app) and its website twin call `record_merge` for every merged non-owner, non-bot pull request into main, closing an issue or not: recognition points by size band (small 20, medium 50, large 100; from additions+deletions excluding lockfiles and generated files), once per pull request, held for unlinked GitHub accounts like awards are. Coins still come only from offers.
- **Offers by label:** an issue labelled `coins:100` (owner or maintainer adds it) publishes the offer through `issues: labeled`; removing it closes the offer. Console stays for edits.
- **Leaderboard advertises:** each row shows GitHub login (linked), the last merged pull request title and link, merges this month, and the member's portfolio link if public; a *Hire or thank* line on their profile.
