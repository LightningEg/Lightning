---
title: In Arabic, delete confirmations open as a harmless "OK" dialog with focus on Yes, so Enter deletes
type: bug
look: visual
severity: medium
pillar: protect
size: S
model: sonnet
status: ready
created: 2026-11-08
by: Claude
---

## Report

Report [r28](r28-international-polish/report.md) F1. `window.askFrom` (`lightning/ui/static/app.js:503-506`) translates the text first, then splits the title on `?` and decides danger with `/\b(delete|remove)\b/i`. Arabic confirmations end in `؟` and contain neither English word, so every Arabic delete (category, transaction, view, rule …) gets the info tone, an "OK" button, no title/message split, and focus on Yes (`app.js:498`). The English safeguard "Enter must not delete" is lost in Arabic.

Reproduce: Settings › Language › العربية, Categories, delete a category: the dialog says موافق and Enter confirms.

## Fix

Decide danger from the caller, not the words: `data-confirm-delete` (and any caller that deletes) passes `tone: "danger"`; split on `?` or `؟`. Test: a browser test in Arabic opens a delete confirm and asserts the danger tone, the localised Delete label and focus on No.

## How to work on this item

Each step below is one pull request. Read only the files a step names. Run the step's test command, then `python -m pytest tests/test_issues.py -q`; delete the step's heading in the same commit (AGENTS.md §3).

## 3BB1 Delete confirmations are dangerous in every language · S
Files: `lightning/ui/static/app.js` only (`window.askFrom` near line 503; the `[data-confirm-delete]` submit listener near line 843; `window.confirmSubmit` near line 532).
Do: (1) In `askFrom`, split the title on `?` **or** `؟`: `split(/(?<=[?؟])\s+/)`. (2) In the `[data-confirm-delete]` listener, when `options` is the string from `confirmHost.dataset.confirmDelete` (or the fallback string), call `window.confirmSubmit(event, window.askFromOptions(text, {tone: "danger", ok: t("Delete")}))`, where `askFromOptions` is a new helper that returns the `{title, message}` object `askFrom` builds, so the dialog gets the danger tone without guessing from English words. (3) Keep the English regex for plain `data-confirm` texts, and also match the Arabic verbs `احذف|امسح|شيل`. Do not change `ask()`.
Done when: a new browser test `tests/test_confirm_dialog_browser.py` (copy the profile set-up from `tools/phone_check.py` lines 70-97) switches the locale to Arabic, opens Categories, presses a category's delete button and asserts the open `dialog.ask-dialog` has class `tone-danger`, its yes button has class `is-danger`, and `document.activeElement` is the `[data-ask="no"]` button; the same test in English passes too. `python -m pytest tests/test_confirm_dialog_browser.py -q`.
