---
title: Saving a Budget field reloads the page and ends editing; it should save in place
type: bug
look: visual
severity: medium
pillar: plan
size: M
model: sonnet
status: new
created: 2026-11-12
by: owner
---

## Report
Owner, 2026-11-12: saving something inside the Budget refreshes the page and leaves editing mode. The owner wants no reload on save anywhere: stay where you are. Not solved in the session that heard this.

## Fix
Post the Budget forms with fetch (the pattern used by the register edit and `data-popup-return`), update the changed row from the response, keep focus and edit state, show the saved note. Test: a Mohab step that edits a limit, checks the page did not reload and the figure changed.
