---
title: More AI prompt buttons that carry Lightning's context
type: feature
area: import
status: ready
created: 2026-10-30
by: Claude Sonnet 5.5
skills: feedback-review
app_version: 1.5.4
repo: app
---

## Report
Owner, 2026-10-30: every AI hand-off is two buttons, Copy prompt and Edit prompt, never the text (done for the statement import, the workbook setup and Export for AI; one partial, `partials/ai_prompt.html`). Each says why it helps: the prompt carries context an AI tool cannot guess. Which other screens would use one?

## Fix
Candidates, each a prompt built locally from names and categories only, never amounts unless the person exports them:
1. **A rejected CSV.** On the mapping and review screens, when rows fail, a prompt that holds the file's header, the error lines and the schema, so the AI fixes the file instead of the person.
2. **Counterparty clean-up.** On Counterparties, a prompt with the saved names and aliases asking which are duplicates or spellings of one name, answered as a list to paste into Add alias.
3. **Spending analysis.** On Spending, the period's analysis prompt beside the page's own figures (the Export for AI prompt already exists in Settings; link to it from the screen where the question arises).
4. **Budget question.** On Budget, a prompt that explains the plan's own words (pace, rolled-over, held for) before asking how to reach a target.
5. **Category mapping for a bank.** On the first import into an account, a prompt that asks the AI to map the bank's own category words to the person's categories.
Build each with `partials/ai_prompt.html`, a "why this helps" line, an Arabic string and a test that the text is never open on the page.
