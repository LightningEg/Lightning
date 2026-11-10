---
title: One name per thing and no accounting jargon - ledger, counterparty, reevaluation, Title Case categories, three names for planning
type: polish
pillar: feel
size: M
model: sonnet
status: ready
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

## How to work on this item

Each step is one pull request, one term at a time. The Glossary (`ai/GLOSSARY.md`, read only the term's line: `grep -n "<term>" ai/GLOSSARY.md`) is changed first in the same PR; then English keys, their Arabic in `lightning/ui/i18n.py`, templates and tests. Never rename a route, a database column or a code. Run `python -m pytest tests/test_arabic_no_english.py tests/test_mohab_year.py -q` and delete the step's heading in the same commit.

## 3BH5 Curly apostrophes in visible English strings · S · #426
Done in 3BH5's first part: Gam'eya (straight, the 43× spelling), ذهب, إنت and النقدية المتاحة for Free cash. Left: about 30 visible strings use a straight `'` inside a word where 6 use `’`. Pick one with the owner (the guideline has no rule), then change it in templates and `ARABIC_UI` keys **and** their callers together (a key change must change every `|tr` that uses it).
Done when: `grep -rn "[a-z]'[a-z]" lightning/ui/templates` shows only code, and `python -m pytest tests/test_arabic_no_english.py -q` passes.

## 3BH6 Built-in categories in sentence case · M · opus · #427
Files: `lightning/database/seed.py`, a new migration (skill `add-migration`: read `skills/add-migration/SKILL.md` first), `lightning/ui/i18n.py` (Arabic keys for the new names).
Do: change the 27 Title Case seed names ("Eating Out" → "Eating out", "Utilities & Bills" → "Utilities & bills", "Unaccounted Money Found" → "Unaccounted money found" …) for new profiles; the migration renames them in existing profiles **only where the user has not renamed them** (match the old exact name and the seed's code). Keep codes.
Done when: the migration's test upgrades a profile made with the old seed and finds the new names, and a renamed category keeps its user name. `python -m pytest tests/test_migrations*.py tests/test_mohab_year.py -q`.

## 3BH7 Headings never show a code · S · #428
Files: `lightning/ui/templates/investments/asset_form.html:4`, `lightning/ui/templates/investments/form.html:4`.
Do: "Edit FND:AZMM" → "Edit {name}" with the asset's display name; "Edit OUT-…" → "Edit transaction" with the date and payee as the subtitle. One `|tr` key each with a value, not `'Edit ' ~ …`.
Done when: `grep -rn "'Edit ' ~" lightning/ui/templates` is empty.

## 3BH8 More words found by r35 · S
From [r35 F14](../12-desktop-ux/r35-ux-against-users-questions/report.md): "Completed payment occurrences" (Reserves) → "Payments made"; "Unreconciled events" and "Money at risk" (Weekly review) → "To match" and "Late or due"; "Cash ownership history" (Held for others) → "History"; "Funded spending left" and "Unfunded bills due" (payday) → plain sentences; "Other Investments" beside "Other" in one Investments legend (rename the class or the remainder); "Age of Money" → "Age of money". Arabic with each; add the retired words to the test's list.
