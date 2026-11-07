---
title: Arabic - page-header date ranges read backwards, figures use two thousands separators, and counts disagree with their nouns
type: bug
look: visual
severity: medium
pillar: feel
size: M
status: new
created: 2026-11-06
by: Claude
---

## Report

Audit r26 F6 ([report](../12-desktop-ux/r26-user-test-pc-and-phone/report.md), [evidence](../12-desktop-ux/r26-user-test-pc-and-phone/evidence/07-ar-date-range-reversed.png)). Every page header wraps "X لحد Y" in `<b dir="ltr">` (`lightning/ui/templates/partials/macros.html:129`, also `birdview/expenses.html:4`), so a right-to-left reader meets the end date first ("٦ نوفمبر لحد ١ نوفمبر"). `analysis/compare.html:3` has the same wrapper and a hard-coded English "to". Hero figures use a Latin comma ("١٩٧,٩٧١") while other figures use "٬" ("٢٦٤٬٤٧١"). Counts disagree with their nouns: "بعد ٣ يوم", "٢ دفعة عائد", "يغطي ٠٫٨ شهور". The gold account's history shows "Investment revaluation" in English.

## Fix

Isolate each date, not the whole phrase (each date in its own LTR isolate inside an RTL line); translate Compare's "to"; one thousands separator for every Arabic figure (the hero's formatter); a small Arabic count helper (1, 2, 3-10, 11+) for the phrases that carry a count; translate the revaluation label. Tests: the header's start date sits to the right of its end date in Arabic (browser); no "," inside an Arabic-digit figure; the count phrases for 1, 2, 3 and 11.
