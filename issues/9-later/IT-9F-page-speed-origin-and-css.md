---
title: Page speed: a CSS trim
type: tech
pillar: reach
size: S
status: new
created: 2026-10-19
by: Claude
---

## Report
**Read:** Architecture › Page speed.

## Measured · 2026-11-06 (demo data, Chromium, loopback)
- **The cache already works.** `runtime/http.py` sends `private, max-age=86400` for `/static/`; every CSS file fetches in 0 ms on a repeat page. A stable origin would add nothing within a session and would weaken the random per-launch port and launch-code checks, so **owner decision (2026-11-06): drop the stable-origin half.**
- A repeat page takes about 70 ms, roughly 40 ms of it after the HTML arrives (style parse and layout, then script).
- `style.css` is 380 KB (76 KB gzipped); across 16 pages (Overview, Budget, Plan and its tabs, Transactions, Accounts, Investments, Health, Categories, Birdview, Settings, Zakat) only **30%** of it is used, `visual-flow.css` 32%. `themes.generated.css`, `theme-surfaces.css`, `theme-materials.css` count 0% because the default theme is on.

## Fix
Trim `style.css` rules no page can reach, then rebuild `style.rtl.css` (`tools/build_rtl_css.js`). Coverage misses hover, focus, dialogs, themes and unvisited pages, so check each rule against the templates and JS before removing it; run Mohab, `tools/theme_check.py` and `tools/phone_check.py`. Expect a few ms, not a rewrite: measure again after.
