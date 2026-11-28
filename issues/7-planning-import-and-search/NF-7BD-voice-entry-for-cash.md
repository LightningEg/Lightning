---
title: Say a cash spend in Egyptian Arabic or English and it fills the entry sheet, on the phone only
type: feature
pillar: capture
size: L
model: opus
status: new
created: 2026-11-28
by: Claude
---

## Report
[r41](r41-the-next-big-thing/report.md) phase 2 (owner, 2026-11-27: voice entry yes, on the device). Cash is the
spending people forget; Say and Pockito take voice ("150 pounds on fuel").

## Fix
Three steps, in order.

## 7BD1 A mic button in the Add sheet uses the phone's own speech recognizer · M
Android only: the phone's recognizer (an offline language pack when present); Lightning sends nothing. Done when: the
native test shows the transcript reaches the sheet.

## 7BD2 Ordinary tested rules read the amount, category and date from the words · M
Amounts in Arabic or Latin digits and words ("ميه وخمسين"), a category or payee from the person's own names and recent
entries ("بنزين" → Fuel), today unless a day is said. Done when: 40 sample phrases in Egyptian Arabic, English and
mixed parse as expected.

## 7BD3 The sheet opens filled and editable; nothing saves until Save · S
Needs 7BD1 and 7BD2 merged first. Done when: a phone browser test speaks through a stub and finds the filled sheet;
Mohab gets a voice step.
