---
name: site-recapture
description: Recapture the website's app screenshots from Mohab's sample year and bring every figure the site quotes into line with them, in English and Arabic, with release IDs, structured data, llms.txt and the sitemap. Use when the app changes a screen or a figure the site shows, before a marketing push, or when asked "are the snapshots up to date?".
---

# Site recapture

Tool-neutral. The website (`Lightning_website`, beside this repo) shows real screens from Mohab's 2026 and quotes their figures beside them (guideline B07): one capture date, one app version, every figure on the screen next to it.
A recapture is stale-proofing, not redesign: same screens, same crops, new figures. Read the site's `README.md` sections *Version identity and archive*, *Landing pages* and *App screenshots* (`grep -n '^## '`, then read the range).

## Token rules

Never open a guideline file whole; `python tools/guideline.py --dir ../Lightning_website/guideline B07` prints a section. Read screenshots you need to judge, not all of them. Find figures with grep, not by reading pages.

## Steps

1. **Is it stale?** Start the sample (`LIGHTNING_PRICES_OFFLINE=1 LIGHTNING_TODAY=2026-10-04 python -m lightning --sample --no-browser`, port 8767) and compare the Overview's net worth, Cash planning's safe to spend and Investments' portfolio with the site's (`grep -c` them in `index.html`).
   Any difference means a recapture. Keep the sample date the site uses unless the owner asks for a new one; the sample's CSVs end there. Stop the server before step 2.
2. **Capture.** `python tools/site_shots.py <scratch>/en`, then `--lang ar` into another folder. It needs Playwright, Chromium and `sqlcipher3` (`pip install sqlcipher3`; without it profile setup fails with "ModuleNotFoundError").
   It writes every screen the site uses at the site's sizes (see its docstring), the phone and the PC borrowing from it from two real paired profiles, and the import review last.
3. **Look at them.** Open the ones whose figures the site quotes and any that changed shape. A screen with a fault (a toast, the + button over a figure, an error or "unresolved" notice, overlapping labels) is not edited (B12): file an item in `issues/` and either fix the app first or keep the old screen for that page.
   The Arabic app may still show some lines in English (the device line, today): keep the English pairing screens for Arabic pages until it is translated, and say so in the site README.
4. **Folders.** Copy only the files the live pages use into the site's `assets/app/mohab-year-YYYY-MM-DD/` and `ar-YYYY-MM-DD/` (list them: `grep -oh 'assets/app/[a-z0-9-]*/[a-z0-9-]*\.webp' *.html ar/*.html | sort -u`). Never change or delete an old folder: archived pages use them.
5. **Release IDs first.** In the site, `python tools/release.py <spec.json>` archives every page you will change and gives it a new ID, before you edit (site README › Version identity and archive). Page-specific CSS or JS you will change goes in the page's `snap` list.
6. **Figures.** Build an old → new map from the app's HTML (`curl -s` the page, strip tags, grep), never from memory. Replace whole figures (`432,467`), never parts; the Arabic pages write them in Arabic-Indic digits with `٬` (`٤٣٢٬٤٦٧`), with `<bdi dir="ltr">` around signed ones.
   A figure whose meaning changed (the investing rate became a share of what you kept, 2026-10-14) needs its sentence rewritten, not just its number. New rows on a screen (a savings-target row in safe to spend) need a new row in the breakdown and its alt text.
   Update `width`/`height` on images whose size changed, every `alt` that quotes a figure, the JSON-LD FAQ answers that repeat visible text, scripts that hold figures (`data-from`/`data-to` on the runway), `llms.txt` and the site README's *App screenshots*.
7. **Check.** In the site: `python tools/site_check.py` (links, JSON-LD, snapshots, version list, titles), then view the changed sections at 1280 and 390 px wide in light mode; nothing may scroll sideways.
8. **Ship.** One branch per repo (`claude/<feature>`), merge to `main`, push both. Changelog line here (the site has none) and a `NOW.md` message if other AIs quote site figures.

## Report

Which screens changed and why; the old → new figure map; any screen kept old and the report that explains it; commits in each repo.
