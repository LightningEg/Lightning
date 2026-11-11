---
title: Link the three comparison pages and add a fourth that compares Lightning with an AI assistant
type: feature
pillar: reach
size: M
model: sonnet
status: ready
created: 2026-11-11
by: Claude
skills: none
repo: website
post: no
---

## Report

Owner decision 2026-11-11 (OW-8AA, signed off): the three comparison pages (a spreadsheet, a traditional expense tracker, a cloud budgeting app; English and Arabic) are approved with the ratings as written, so they are no longer hidden. The owner also wants a fourth comparison: **an AI assistant**. The honest framing is that you do not own your data with an AI assistant, it can be powerful, and it is expensive.

## Fix

In the website repository, from the one scorecard `comparisons.json`:

1. Link the three approved pages from the menu and the home page (English and Arabic).
2. Add the fourth page, "AI assistant", to `comparisons.json` with every row rated and each rating citing a row of `ai/COMPETITION.md` or a test; add the missing competitor rows to `ai/COMPETITION.md` first. Keep the claim fair: AI is strong at answering open questions and drafting; Lightning wins on data ownership, traceable numbers and Egypt fit; say that AI costs a subscription or per-use fees and that what you send leaves your device. Do not name a vendor's price unless it is dated and cited.
3. `python tools/comparisons.py build`, check the Arabic page reads right to left, update the sitemap and `llms.txt`.

## Done when

The four pages are linked from the menu and Home in English and Arabic, the AI page's ratings each cite a source, and the website's own tests pass.
