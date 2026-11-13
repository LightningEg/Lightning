---
title: One name per thing and no accounting jargon - ledger, counterparty, reevaluation, Title Case categories, three names for planning
type: polish
pillar: feel
size: M
model: sonnet
status: parked
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

## 3BH1 A test that keeps jargon off the screen · S · #425
Files: new `tests/test_voice.py`.
Do: render (with the sample household, English and Arabic; copy the set-up from `tests/test_arabic_no_english.py`) the main PC and phone pages listed in `tools/phone_check.py` `PAGES`, take the visible text, and assert it contains none of a list of words. Start the list with the words that are already gone (`Successfully`, `Please`, `Submit`, `Error:`, `Invalid`) so it passes today; each later step adds its own word.
Done when: `python -m pytest tests/test_voice.py -q` passes and the list lives at the top of the file with a one-line reason per word.

## 3BH2 "Counterparty" becomes "Payee" (Arabic: الطرف التاني → الجهة) · M
Needs 3BH1 merged first.
Decided (owner, 2026-11-08): "Payee" for money out and in, "Who" as a column heading.
Files: `grep -rln "Counterpart" lightning/ui ai/GLOSSARY.md` (63 keys; the nav heading on `/counterparties`).
Do: rename the visible words only; keep `/counterparties` and every variable. Add "counterparty" to the test's list.
Done when: `tests/test_voice.py` passes with the word listed.

## 3BH3 "Ledger" and "reevaluation" leave the screen · S
Needs 3BH1 merged first.
Files: `grep -rn "ledger\|Ledger\|reevaluation\|Reevaluation" lightning/ui/i18n.py lightning/ui/templates` (57 + 12 keys), `lightning/deposits/service.py:296`.
Do: "Reevaluation ledger" → "Value updates"; "reevaluation" → "value update"; sentences with "ledger" are rewritten without it ("in your records", or just dropped: "Principal cannot exceed the CD's currently owned ledger balance." → "You can take out at most {amount} from this certificate."). Add both words to the test's list.
Done when: `tests/test_voice.py` passes with "ledger" and "reevaluation" listed.

## 3BH4 One name per place · S
Needs 3BH1 merged first.
Files: `lightning/ui/sections.py` (section and tab names), `lightning/ui/templates/not_found.html`, `lightning/ui/templates/investments/holding.html:83`, `lightning/ui/templates/budget.html:83`, the "YTD" button (`grep -rn '"YTD"\|>YTD<' lightning/ui`).
Do: the section is "Cash planning" everywhere (tab and heading too, not "Plan"/"Planning"); "Back to the dashboard" → "Back to Overview" (phone: "Back to Home"); "The journey" → "How it went"; "Could not save; retry with Enter or blur." → "Not saved. Press Enter to try again."; "YTD" → "This year". Add "dashboard" and "journey" to the test's list.
Done when: `tests/test_voice.py` passes with both listed, and `grep -rn "'Plan'\|\"Planning\"" lightning/ui/sections.py` shows only the section's single name.

## 3BH5 One spelling per word · S · #426
Files: `lightning/ui/i18n.py`, templates.
Do: "Gam’eya" → "Gam'eya" in the 2 places (`grep -rn "Gam’eya" lightning`); Arabic دهب → ذهب (glossary spelling: check `ai/GLOSSARY.md`), انت → إنت; Free cash's Arabic is the glossary's النقدية المتاحة everywhere, and brand-voice's «المتاح للصرف» is for Safe to spend only (check `grep -n "المتاح" guideline/brand-voice.md`). Curly apostrophes in visible English strings: `’` in place of `'` inside words, in templates and `ARABIC_UI` keys **and** their callers together (a key change must change every `|tr` that uses it).
Done when: `grep -rc "دهب\|\bانت\b" lightning/ui/i18n.py` is 0 and `python -m pytest tests/test_arabic_no_english.py -q` passes.

## 3BH6 Built-in categories in sentence case · M · opus · #427
Files: `lightning/database/seed.py`, a new migration (skill `add-migration`: read `skills/add-migration/SKILL.md` first), `lightning/ui/i18n.py` (Arabic keys for the new names).
Do: change the 27 Title Case seed names ("Eating Out" → "Eating out", "Utilities & Bills" → "Utilities & bills", "Unaccounted Money Found" → "Unaccounted money found" …) for new profiles; the migration renames them in existing profiles **only where the user has not renamed them** (match the old exact name and the seed's code). Keep codes.
Done when: the migration's test upgrades a profile made with the old seed and finds the new names, and a renamed category keeps its user name. `python -m pytest tests/test_migrations*.py tests/test_mohab_year.py -q`.

## 3BH8 More words found by r35 · S
Needs 3BH1 merged first.
From [r35 F14](../12-desktop-ux/r35-ux-against-users-questions/report.md): "Completed payment occurrences" (Reserves) → "Payments made"; "Unreconciled events" and "Money at risk" (Weekly review) → "To match" and "Late or due"; "Cash ownership history" (Held for others) → "History"; "Funded spending left" and "Unfunded bills due" (payday) → plain sentences; "Other Investments" beside "Other" in one Investments legend (rename the class or the remainder); "Age of Money" → "Age of money". Arabic with each; add the retired words to the test's list.
