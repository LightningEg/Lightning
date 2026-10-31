---
title: More AI prompt buttons that carry Lightning's context
type: feature
pillar: understand
size: M
status: ready
created: 2026-10-30
by: Claude Sonnet 5.5
skills: feedback-review
app_version: 1.5.4
repo: app
---

## Report
Owner, 2026-10-30: every AI hand-off is two buttons, Copy prompt and Edit prompt, never the text (done for the statement import, the workbook setup and Export for AI; one partial, `partials/ai_prompt.html`). Each says why it helps: the prompt carries context an AI tool cannot guess. Five screens would use one; this is one of them.

## Fix
Candidates, each a prompt built locally from names and categories only, never amounts unless the person exports them:
1. **A rejected CSV.** On the mapping and review screens, when rows fail, a prompt that holds the file's header, the error lines and the schema, so the AI fixes the file instead of the person.
2. **Counterparty clean-up.** On Counterparties, a prompt with the saved names and aliases asking which are duplicates or spellings of one name, answered as a list to paste into Add alias.
3. **Spending analysis.** On Spending, the period's analysis prompt beside the page's own figures (the Export for AI prompt already exists in Settings; link to it from the screen where the question arises).
4. **Budget question.** On Budget, a prompt that explains the plan's own words (pace, rolled-over, held for) before asking how to reach a target.
5. **Category mapping for a bank.** On the first import into an account, a prompt that asks the AI to map the bank's own category words to the person's categories.
Build each with `partials/ai_prompt.html`, a "why this helps" line, an Arabic string and a test that the text is never open on the page.

## 7V1 A rejected CSV · M · #232
On the mapping and review screens, when rows fail, a prompt holding the file's header, the error lines and the schema, so the AI fixes the file instead of the person. Built from names and categories only, never amounts unless the person exports them. Use `partials/ai_prompt.html`, add a one-line why-this-helps and its Arabic string, and a test that the prompt text is never open on the page.

## 7V2 Counterparty clean-up · S · #233
On Counterparties, a prompt with the saved names and aliases asking which are duplicates or spellings of one name, answered as a list to paste into Add alias. Built from names and categories only, never amounts unless the person exports them. Use `partials/ai_prompt.html`, add a one-line why-this-helps and its Arabic string, and a test that the prompt text is never open on the page.

## 7V3 Spending analysis · S · #234
On Spending, link to the period's analysis prompt (the Export for AI prompt already exists in Settings) from the screen where the question arises. Built from names and categories only, never amounts unless the person exports them. Use `partials/ai_prompt.html`, add a one-line why-this-helps and its Arabic string, and a test that the prompt text is never open on the page.

## 7V4 Budget question · M · #235
On Budget, a prompt that explains the plan's own words (pace, rolled-over, held for) before asking how to reach a target. Built from names and categories only, never amounts unless the person exports them. Use `partials/ai_prompt.html`, add a one-line why-this-helps and its Arabic string, and a test that the prompt text is never open on the page.

## 7V5 Category mapping for a bank · M · #236
On the first import into an account, a prompt that asks the AI to map the bank's own category words to the person's categories. Built from names and categories only, never amounts unless the person exports them. Use `partials/ai_prompt.html`, add a one-line why-this-helps and its Arabic string, and a test that the prompt text is never open on the page.
