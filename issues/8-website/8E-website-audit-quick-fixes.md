---
title: Website audit quick fixes (one download wording, version in structured data, blank sync frame)
type: bug
area: website
status: building
created: 2026-10-21
by: Claude
skills: website-sync
repo: website
---

## Report

From the owner's website audit (PDF, 2026-10-21, "does it make people download?"), checked against the site code that day.
Each is small and needs no owner decision.

- **Three wordings for one action.** "Download the free beta" on 11 pages (`guides.html` and every guide) vs "Download free" in
  the header and home. Arabic: hero «جرّب ببلاش», nav «نزّل ببلاش». Use "Download free" / «نزّل ببلاش» everywhere.
- **`softwareVersion` is stale.** `index.html:51` and `ar/index.html:44` say `1.1.0-beta.1`; the Arabic release log says 1.3.0.
  Take it from `version-registry.json`; add `fileSize`. Update `llms.txt` if it names a version.
- **Download buttons land on the top of a status page.** Point them at `current-status.html#downloads` and put
  "Windows 10/11 · version · size" under the main button (Android "in testing" as a quieter link).
- **PC frame in "One Ledger. Two Screens." looks blank** in screenshots and slow loads (`css/sync-demo.css` `.sync-pc-veil`,
  `background:var(--paper)`). Reproduce first; the screenshot must show until the demo runs.
- **Sample profiles** (`sample-profiles.html`): no download button before 3,627 px, no JSON-LD. Add "Download and open Mohab's
  year" under the stories; add `WebPage` + `BreadcrumbList`.
- **How It Works** loads 12 images (542 KB) at once: `loading="lazy"` on all but the first.
- **Header logo** has empty `alt`: give it `alt="Lightning"`.

Not taken: the audit's "replace `blog.html`'s meta refresh with a 301" (GitHub Pages cannot send one; the refresh plus
canonical is already the README rule).

## Built

Site PR #46 (`claude/website-audit-fixes`): everything above except the guide pages' wording, which 8H carries.
Not taken: logo alt (`alt=""` is right beside the visible word), How It Works images (already lazy), `#downloads`
(the Downloads hero holds the files; `#downloads` skips them).

## Done when

One wording per language, the structured data matches the release, every download button reaches the file in one step,
and the sync frame never shows blank. New release ID (visible copy changed).
