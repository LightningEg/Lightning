---
title: For Geeks audit ideas left for the owner to choose
type: owner
area: website
status: ready
created: 2026-10-21
by: Claude
skills: none
repo: website
---

## Report

An outside visual audit of For Geeks (`forgeeks*.html`, 2026-10-21) scored proof next to claims 6/10 and motion 5/10.
What it found that the guideline already asks for is built (website `claude/forgeeks-audit-fixes`): fresh counts through
`tools/geeks_stats.py`, the secure card linking `lightning/security/keys.py`, a hero word in Ink that no longer moves the
line, a ringed theme chip, a quiet terminal during the replay, [secret] at 4.5:1, two font weights, the mission's columns
balanced, the stack rows on one line, the current kept off headings, the roadmap glow running once, the M1 count's source,
the contribute page linking Home's stack, `docs/GLOSSARY.md` and AGENTS.md instead of copying them (16,795 → 14,466px on a phone, owner 2026-10-21), the Arabic footer's For Geeks link labelled English, and
D07's demo port (8766).

## Left for the owner

1. **Motion moments** (the audit's seven). D08 says motion is the weather, never the content, so each is a new D07
   block and a guideline change first. Worth weighing: *a posting that must balance* beside the `ledger.py` code, and
   *a row becomes ciphertext* on the secure card. Not as drawn: *nothing leaves the PC, 0 requests out* is false: the app
   fetches market prices and rates (`lightning/market/http.py`).
2. **Stats in CI.** `python tools/geeks_stats.py ../Lightning --check` fails when the page drifts; a website job that
   clones the app would make it automatic, but would also turn unrelated site PRs red after any app merge.
3. **Arabic links to English pages.** No guideline rule; the footer now says «(بالإنجليزي)» and opens a new tab. Make it
   a B09 rule?

## Fix

The owner picks; each chosen idea becomes its own item here.
