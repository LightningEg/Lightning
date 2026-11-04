---
title: Download shared prices brings nothing: only the exchange-rate pack is published, and not since 11 Oct
type: bug
look: technical
severity: medium
pillar: own
size: M
status: ready
post: no
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
Owner decision (2026-11-04): remove the required reviewer on the `market-publishing` environment, as `tools/security_setup.py` already intends (`approval=False`). Only packs whose sources allow republishing publish (today: the exchange-rate pack, `packs.py` `publish=True`); the others stay checked-only.
Owner step (an AI session cannot reach the environment settings): run `python tools/security_setup.py --apply` with the owner account, or clear *Required reviewers* in Settings › Environments › market-publishing. Then check that variable `MARKET_PUBLISH` is `true` and the secret `LIGHTNING_MARKET_TOKEN` is set.
Done when: a scheduled "Price packs" run finishes without waiting, `index.json` in Market_Data shows a new `fx` date, and Download shared prices fills. The Price files page already says "Not published yet" for the rest.

## Progress (2026-11-04)
The reviewer is removed; scheduled runs no longer wait. Manual run 103 collected `fx` but its push failed: 403 "Permission to elfekimuhammed/Lightning_Market_Data.git denied". `MARKET_REPO` now names `LightningEg/Lightning_Market_Data`. Owner step: a fine-grained token with resource owner `LightningEg`, only that repo, Contents read/write, saved as `LIGHTNING_MARKET_TOKEN` in `market-publishing`; the data repo's "security: price publication" rule must let the owner-admin push. Then run the workflow with packs `fx`.
Separate: run 103 also failed in Collect on the checked-only `gcc` pack (source error not yet read; see the run summary table). The app keeps the old `elfekimuhammed` raw URL, which still redirects (200).
