---
title: In Arabic the "·" beside a number reads as a zero (Late 17 days shows as 170), decimals mix "." and ",", and a few strings stay English
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
Found by [Audit 1](../../reports/audit-1.md) (§5 Arabic) on Mohab's sample and the demo, PC 1366 px and phone 390 px. The Arabic tests pass.

**High: a figure reads wrong.**
1. The middle dot "·" between a word and Arabic-Indic digits looks like the Arabic zero "٠", so the number reads ten times bigger.
   - Cash planning: "Late · 17 days" (`i18n_system.py:729`: "متأخر · {n} يوم") reads "متأخر ١٧٠ يوم" (170 days).
   - On a holding, "Months up · down 5 · 1 of 6" reads "١٠٥" (105).
   - Every row subtitle "date · Bill" reads as one long number ("٢٠٢٦-١٠-٠٣ · فاتورة").
   - Shots: [ar-dot-reads-as-zero-plan.png](../../reports/audit-1/ar-dot-reads-as-zero-plan.png), [ar-dot-reads-as-zero-holding.png](../../reports/audit-1/ar-dot-reads-as-zero-holding.png).

**Medium.**
2. **Decimals and percent signs mix.**
   - One holding card shows "±١.٦%" with a point and "+٣,٨%" with a comma.
   - The zakat strings use "٢٫٥٪", while the screens use "%".
   - Use one Arabic decimal separator "٫" and one percent sign everywhere.
3. **Left in English on every page:** the undo button's title and aria-label, "تراجع · Saved changes (Ctrl+Z)".
4. **Left in English elsewhere:**
   - The "Plan this transaction" page: its title, heading and text (`/plan/from-transaction/{id}`).
   - The phone Settings stacked labels "Setting" and "Where".
   - "1 entry" on Held for others.
   - The placeholder "e.g. 100 shares, 12.5 grams".
   - The budget move preview: "the total plan stays the same", and "Transportation 68 ← 90", which reads backwards in RTL.
   - The raw code "MONTH_END" after "مُنشأ تلقائيًا ·".
5. **Overlaps:** the Plan timeline's "اليوم" (Today) is drawn on top of "Landlord +٥". Chart axes use a Latin "k" ("١٠٢k").

**Low.**
6. "قرض · الدفعة ١٠ من ٢٤" wraps so "٢٤" sits alone on the next line.

Not rechecked: 3A, 3B, 3E and the voice review. The audit agent stopped on a spend limit after the crawl and screenshots.

## Fix
- In Arabic, use the Arabic comma "،" or a spaced bullet in place of "·" next to digits: in `localize_html`, or one separator token in the templates.
- Format decimals and percents through one Arabic formatter.
- Add the missing strings to `ui/i18n.py`.
- Add a test that fails when an Arabic page has "·" next to an Arabic-Indic digit.
