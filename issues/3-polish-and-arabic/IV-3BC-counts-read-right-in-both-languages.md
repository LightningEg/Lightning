---
title: Counts read right in English and Arabic - "1 days left", "Delete 1 transactions?", "2 معاملة"
type: polish
pillar: feel
size: M
model: sonnet
status: ready
created: 2026-11-08
by: Claude
---

## Report

Report [r28](r28-international-polish/report.md) F3. There is no shared plural helper: 47 hand-rolled `'s' if` ternaries and "(s)" (`dashboard/index.html:27`, `phone/dashboard/index.html:22`); `web.py:270 _units_of` adds "s" to any unit. Live English errors: "1 days left" (`ui/kpis.py:123`), "1 categories" (`categories/list.html:46`), "{n} months" (`planning/recurring.html:48`), "1 of 1 payments made" (`keynotes.py:212`), "Delete {count} transactions?" (`app.js:850`), "for {count} categories" (`budget.html:83`). In Arabic, `translate(key, n=…)` agrees for four nouns only (`i18n.py:3485-3511`); a count built in English first ("2 transactions", "Across 1 accounts", "1 row") translates to "2 معاملة", "في 1 حسابات", "1 صف". 135 keys contain `{n} <plural noun>`.

## Fix

One helper on both sides: `plural(n, one, other)` in Python/Jinja and `window.lightningPlural` in JS, backed by an Arabic table (1, 2, 3–10, 11+) for every counted noun in the UI (account, transaction, row, category, month, day, payment, item, bill). Replace the ternaries and the listed sites. Test: a parametrised test renders n = 0, 1, 2, 3, 11 for each noun in both languages; a grep test forbids `'s' if` in `lightning/ui`.

## How to work on this item

Each step is one pull request; do them in order. Read only the files a step names. Run the step's test command and `python -m pytest tests/test_arabic_ranges_and_counts.py tests/test_arabic_no_english.py -q`; delete the step's heading in the same commit.

## 3BC1 One English plural helper and the five wrong counts · S
Files: `lightning/ui/i18n.py` (add the helper next to `translate`, line ~3514), `lightning/ui/web.py` (register it as a Jinja filter next to `templates.env.filters["money"]`, line ~134), `lightning/ui/kpis.py:123`, `lightning/ui/templates/categories/list.html:46`, `lightning/ui/templates/planning/recurring.html:48`, `lightning/ui/keynotes.py:212`.
Do: add `def counted(n, one: str, other: str) -> str` returning `f"{n} {one}"` when `n == 1` else `f"{n} {other}"`; register `templates.env.filters["counted"]`. Use it at the four Python/Jinja sites: "1 day left"/"{n} days left", "1 category"/"{n} categories", "1 month"/"{n} months", "1 payment"/"{n} payments". Add the singular English strings to `ARABIC_UI` with the same Arabic as the plural key.
Done when: new `tests/test_counted.py` asserts `counted(1, "day", "days") == "1 day"`, `counted(2, …) == "2 days"`, `counted(0, …) == "0 days"`, and renders `/categories` on the sample household with a group holding one category and finds "1 category", not "1 categories". `python -m pytest tests/test_counted.py -q`.

## 3BC2 Arabic agrees for every counted noun the UI uses · S
Needs 3BC1 merged first.
Files: `lightning/ui/i18n.py` (`_COUNTED`, line ~3485).
Do: add (one, two, plural) forms for حساب (حساب واحد، حسابين، حسابات), فئة (فئة واحدة، فئتين، فئات), صف (صف واحد، صفين، صفوف), بند (بند واحد، بندين، بنود), فاتورة (فاتورة واحدة، فاتورتين، فواتير), قاعدة (قاعدة واحدة، قاعدتين، قواعد), عنصر (عنصر واحد، عنصرين، عناصر), سنة (سنة واحدة، سنتين، سنين). Nothing else changes: `_agree_counts` already applies them.
Done when: `tests/test_counted.py` gains a parametrised test: for each noun and n in 1, 2, 3, 11, `translate("{n} accounts", "ar", n=n)` (and the matching English key per noun; add keys to `ARABIC_UI` if missing) gives the one/two/plural/singular form. `python -m pytest tests/test_counted.py -q`.

## 3BC3 Counts built in English before translation · M
Needs 3BC2 merged first.
Files: the sites found by `grep -rn "'s' if\|\"s\" if\|(s)" lightning/ui lightning/workflows --include=*.py --include=*.html` (47 today; e.g. `kpis.py:240-242`, `keynotes.py:206`, `templates/rules/past.html:6`, `templates/dashboard/index.html:27`, `templates/phone/dashboard/index.html:22`), and `web.py:270 _units_of`.
Do: at each site, replace the hand-built plural with `counted()` in English **and** make sure the string reaches `translate(key, locale, n=…)` as a `{n} <noun>` key (not a finished English sentence), so Arabic agreement from 3BC2 applies. `_units_of` must not add "s" to a unit the user typed: take the unit as given.
Done when: the grep above returns no line in `lightning/ui` or `lightning/workflows`, and a new test in `tests/test_counted.py` greps for it so it stays at zero. Mohab: `python -m pytest tests/test_mohab_year.py -q`.

## 3BC4 Counts built in the browser · S
Needs 3BC2 merged first.
Files: `lightning/ui/static/lightning-t.js`, `lightning/ui/static/app.js:850`, `lightning/ui/templates/budget.html:83`.
Do: (1) in `lightning-t.js`, after filling values, apply the same agreement as `_agree_counts` for Arabic: ship the `_COUNTED` table to the page with the rest of `LIGHTNING_UI` (find where `ARABIC_UI_SRC` is built in `web.py` ~line 477) and port the function (one, two, 3–10 plural, else singular). (2) In `app.js:850` pass `count: ids.size` as a number (formatting happens after agreement), and add the English key "Delete 1 transaction?" so English says it right. (3) `budget.html:83` "for {count} categories" the same way.
Done when: a Node test `tests/plural-runtime.test.cjs` (copy the harness of `tests/theme-runtime.test.cjs`) loads `lightning-t.js` with a two-entry Arabic table and asserts "Delete {count} transactions?" with count 1, 2, 5, 11. `node tests/plural-runtime.test.cjs`.
