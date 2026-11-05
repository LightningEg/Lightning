---
title: The site screenshot tool breaks on the new Overview, so the site's screens are not recaptured
type: tech
pillar: reach
size: M
status: new
created: 2026-11-05
by: Claude
---

## Report

`python tools/site_shots.py` stopped at the first section crop on 2026-11-05: `section.stat-tiles` (the `a-kpis` crop) no longer exists since the Overview rates moved (3AM3), and the Get set up card is now a closed disclosure (fixed in this item's first commit). Other selectors in `SECTIONS` (`article.overview-sankey-card`, `#plan-forecast`, `#recurring-suggest`, `#currency-USD`) and the PC header (section tabs now sit beside the title, 3AM5) may have drifted too. The headline figures the site quotes (net worth 910,304, safe to spend 112,288, portfolio 752,486) still match the app, so only the screens' shape is stale.

## Fix

Point each `SECTIONS` selector at the current element, run the tool in English and Arabic, look at the screens the site quotes (skill `site-recapture` step 3), then recapture both repos. Test: the tool completes and `python tools/site_check.py` passes.
