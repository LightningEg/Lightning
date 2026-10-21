---
title: Arabic leftovers - the budget move preview arrow, two overlaps and a wrapped number
type: bug
area: arabic
status: ready
created: 2026-10-20
by: Claude
skills: arabic-check
app_version: 1.3.0
commit: 7591231
repo: app
---

## Report
Found by [Audit 1](../../reports/audit-1.md) (§5 Arabic) on Mohab's sample and the demo, PC 1366 px and phone 390 px.
Fixed: the "·" beside a number (now "،"), one decimal mark and one percent sign, the undo button and the English strings of the
Plan this transaction page, the phone Settings labels, "1 entry", the placeholder, the budget move subtitle and "MONTH_END".

1. The budget move preview "Transportation 68 ← 90" reads backwards in RTL (`budget_move.html`, the arrow between the old and new plan).
2. **Overlaps:** the Plan timeline's "اليوم" (Today) is drawn on top of "Landlord +٥". Chart axes use a Latin "k" ("١٠٢k").
3. Low: "قرض · الدفعة ١٠ من ٢٤" wraps so "٢٤" sits alone on the next line.

Not rechecked: 3A, 3B, 3E and the voice review.

## Fix
- Check the arrow with a native reader and fix it in the template.
- Move the "اليوم" label off the payment label; write chart axes as "ألف" or the Arabic compact form.
- Keep a number and its unit on one line (a no-break space).
