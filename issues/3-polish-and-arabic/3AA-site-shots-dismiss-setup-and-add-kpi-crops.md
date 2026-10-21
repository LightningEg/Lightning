---
title: site_shots.py: dismiss Get set up, park the mouse, keep the + button off figures, add the rate crops
type: tech
area: tools
status: ready
created: 2026-10-21
by: Claude Sonnet 5.5
skills: site-recapture
app_version: 1.3.0
commit: 6e1c043
repo: app
---

## Report
`tools/site_shots.py` as it stands gives screens the website cannot use. The 2026-10-21 recapture ran a patched copy; the tool should carry the same changes:
- **Get set up:** the sample's Overview opens with the "Get set up" card (4 of 5 done, a pending import) above Net worth. Click `form[action="/setup/guide"] button` (PC) and `post(ph, "/setup/guide", action="dismiss")` (phone profile, before the pairing) before the first shot.
- **Mouse:** after that click the pointer stays on the page and a later screen shows a hover ring (a dark outline on the Housing & Rent tile in Expense analysis). Call `mouse.move(0, 0)` after it.
- **Phone + button:** see 3Z. Scroll `phone-plan` by 200 and `phone-account` by 60 (Arabic 88) so the button sits between rows.
- **Rate crops:** since 3W the savings and investing rates are no longer above the fold. Add `a-kpis` (`section.stat-tiles`) and `a-sankey` (`article.overview-sankey-card`) as section crops, 13 px around, at 1296 wide, sidebar hidden, scale 2000/1440; the website's Saved this year card and Investment Tracker quote them.
- **Arabic pairing screens:** `sync-pc` and `sync-phone` are still unusable in Arabic (the borrowed line is English and the lent popup is cut off at the left edge); the website keeps the English ones.

## Fix
Make the changes above in `tools/site_shots.py`, update its docstring, and run it for en and ar. Branch `claude/site-shots-setup-and-rates`.
