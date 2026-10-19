---
title: Download shared prices brings nothing: only the exchange-rate pack is published, and not since 11 Oct
type: bug
area: market
status: ready
created: 2026-10-16
by: Claude Sonnet 5.5
skills: feedback-review
app_version: 1.1.0b1
commit: 8f478a2
repo: app
---

## Report
Feedback batch 004, ticket 109: "downloading prices doesn't work anymore". Severity: medium.

## Investigation
The app code is fine: it reads `index.json` from the Market_Data repository. That index lists only the `fx` pack (last date 2026-10-11); the EGX, US and fund packs were never published (sources keep `publish=False`, NOW › Next 1).
Since run 27 (11 Oct) every scheduled "Price packs" run waits on the market-publishing environment approval and is cancelled by the next one, so nothing publishes even for fx.

## Fix
Owner action, not code: approve or remove the required reviewer on the market-data environment for scheduled runs, and decide which packs may be published. Until then the Price files page should say what is published (it says "Not published yet").
