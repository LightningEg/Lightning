---
title: In Arabic, delete confirmations open as a harmless "OK" dialog with focus on Yes, so Enter deletes
type: bug
look: visual
severity: medium
pillar: protect
size: S
status: new
created: 2026-11-08
by: Claude
---

## Report

Report [r28](r28-international-polish/report.md) F1. `window.askFrom` (`lightning/ui/static/app.js:503-506`) translates the text first, then splits the title on `?` and decides danger with `/\b(delete|remove)\b/i`. Arabic confirmations end in `؟` and contain neither English word, so every Arabic delete (category, transaction, view, rule …) gets the info tone, an "OK" button, no title/message split, and focus on Yes (`app.js:498`). The English safeguard "Enter must not delete" is lost in Arabic.

Reproduce: Settings › Language › العربية, Categories, delete a category: the dialog says موافق and Enter confirms.

## Fix

Decide danger from the caller, not the words: `data-confirm-delete` (and any caller that deletes) passes `tone: "danger"`; split on `?` or `؟`. Test: a browser test in Arabic opens a delete confirm and asserts the danger tone, the localised Delete label and focus on No.
