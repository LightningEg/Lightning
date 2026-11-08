---
title: One name per thing and no accounting jargon - ledger, counterparty, reevaluation, Title Case categories, three names for planning
type: polish
pillar: feel
size: M
status: new
created: 2026-11-08
by: Claude
---

## Report

Report [r28](r28-international-polish/report.md) F16-F18.

- **Jargon on screen:** "ledger" in 57 keys (heading "Reevaluation ledger"), "Counterparty/Counterparties" in 63 (a nav heading), "reevaluation" in 12; "Principal cannot exceed the CD's currently owned ledger balance" (`deposits/service.py:296`); stiff formal Arabic for "Undo this import?" (هل تتراجع… ستُحذف 3 قيود).
- **Several names for one thing:** Cash planning / Plan / Planning; Held for others / money-from-others / أموال لغيرك; "Back to the dashboard" on the 404 page under a nav that says Overview; Gam'eya 43× vs Gam’eya 2×; ذهب 32× vs دهب 25×; إنت 13× vs انت 11×; brand voice fixes «المتاح للصرف» (0 uses) while the glossary has النقدية المتاحة.
- **Case and phrasing:** 27 of 61 seed categories in Title Case (`database/seed.py`, e.g. "Eating Out", "Unaccounted Money Found"); "Could not save; retry with Enter or blur." (`budget.html:83`); "The journey" (`investments/holding.html:83`); "YTD" as a button; headings built from codes ("Edit FND:AZMM", `investments/asset_form.html:4`; `investments/form.html:4`); 30 straight apostrophes in visible strings vs 6 curly; "Add currency" names two different actions.

## Fix

Per term, one PR: pick the plain word in the Glossary first (payee/who for counterparty, "history" or nothing for ledger, "value update" for reevaluation), rename keys and Arabic together, keep routes. Seed categories to sentence case through a migration that renames only untouched defaults (skill add-migration). Curly apostrophes in visible strings. Tests: a voice test lists banned words in rendered pages (ledger, counterparty, reevaluation, dashboard, journey) for EN and AR; Mohab's year for each rename.
