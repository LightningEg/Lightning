---
title: Counts read right in English and Arabic - "1 days left", "Delete 1 transactions?", "2 معاملة"
type: polish
pillar: feel
size: M
status: new
created: 2026-11-08
by: Claude
---

## Report

Report [r28](r28-international-polish/report.md) F3. There is no shared plural helper: 47 hand-rolled `'s' if` ternaries and "(s)" (`dashboard/index.html:27`, `phone/dashboard/index.html:22`); `web.py:270 _units_of` adds "s" to any unit. Live English errors: "1 days left" (`ui/kpis.py:123`), "1 categories" (`categories/list.html:46`), "{n} months" (`planning/recurring.html:48`), "1 of 1 payments made" (`keynotes.py:212`), "Delete {count} transactions?" (`app.js:850`), "for {count} categories" (`budget.html:83`). In Arabic, `translate(key, n=…)` agrees for four nouns only (`i18n.py:3485-3511`); a count built in English first ("2 transactions", "Across 1 accounts", "1 row") translates to "2 معاملة", "في 1 حسابات", "1 صف". 135 keys contain `{n} <plural noun>`.

## Fix

One helper on both sides: `plural(n, one, other)` in Python/Jinja and `window.lightningPlural` in JS, backed by an Arabic table (1, 2, 3–10, 11+) for every counted noun in the UI (account, transaction, row, category, month, day, payment, item, bill). Replace the ternaries and the listed sites. Test: a parametrised test renders n = 0, 1, 2, 3, 11 for each noun in both languages; a grep test forbids `'s' if` in `lightning/ui`.
