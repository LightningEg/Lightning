---
title: The phone's slots disagree in small ways - two figures called Left in plan, an Arabic chart that runs against its labels, "To review1", a PC tab bar under Add
type: bug
look: visual
severity: medium
pillar: everywhere
size: M
model: sonnet
status: ready
created: 2026-11-09
by: Claude
skills: guideline-audit, bug-hunt
app_version: 2.1.2
commit: 90f0190
---

## Report

Audit r35 F2 and F3 ([report](../12-desktop-ux/r35-ux-against-users-questions/report.md)). Each is small; together they are what makes the phone feel unfinished. Demo household, 360 px, 2026-11-09.

- **Two Left in plan.** Home's This month row: "Spent 19,001 · Left in plan 6,598". Budget's hero: "Left in plan 5,468". Home passes `plan["left"]` (the whole plan, `lightning/ui/phone/screens/home.py:105`); Budget counts everyday money (C11.2). [texts](../12-desktop-ux/r35-ux-against-users-questions/evidence/phone/texts.json)
- **Arabic Money chart.** The month labels are mirrored (newest on the left) but the line and its end dot are not, so the latest value sits over the oldest month. [screen](../12-desktop-ux/r35-ux-against-users-questions/evidence/phone/money-arabic-chart.webp)
- **"To review1".** The count is a `<b>` after a space inside an inline-flex chip, so the space is lost (`lightning/ui/templates/phone/activity_home.html` line 10). [slots](../12-desktop-ux/r35-ux-against-users-questions/evidence/phone/sheet-home-budget-add-activity.webp)
- **A PC tab bar on the Add page.** `/accounts/add-transaction` on the phone ends with the PC's Import, Accounts, Held for others, Zakat bar under the form. [slots](../12-desktop-ux/r35-ux-against-users-questions/evidence/phone/sheet-home-budget-add-activity.webp)
- **"Nothing is due soon."** on Money while Money › Bills lists WE Internet and North Cairo Electricity under Before payday. [Money](../12-desktop-ux/r35-ux-against-users-questions/evidence/phone/sheet-money-accounts-bills-review.webp)
- **Empty Money prints zeros.** A new profile reads "0 accounts hold 0." and "0 since the start of the month." [first run](../12-desktop-ux/r35-ux-against-users-questions/evidence/phone/sheet-first-run-and-add-sheet.webp)

## Fix

One name, one figure, and nothing left over from the PC. One PR per step; each step's test is named in it.

## How to work on this item

Read only the files a step names; `python tools/guideline.py C11` prints the phone screens' rules. After each step: the step's test, `python tools/phone_check.py` and `python tools/phone_check.py --arabic`, then `python -m pytest tests/test_mohab_year.py -q`. Delete the step's heading in the same commit.

## 11L1 Home's This month row shows Budget's Left in plan · S · sonnet
Files: `lightning/ui/phone/screens/home.py`, `lightning/ui/templates/phone/home.html`. Home's row uses the same everyday figure as Budget's hero (`c.forecaster.everyday(month, day)`), or names the other figure differently if the whole plan is wanted (ask the owner with a pick-list before renaming). Done when a test renders `/home` and `/budget/flexible` on one profile with an unpaid bill and finds the same Left in plan on both.

## 11L2 The Arabic trend chart runs the way its labels do · S · sonnet
Files: `lightning/ui/templates/phone/money.html`, `lightning/ui/static/phone.css` (then rebuild `phone.rtl.css`, skill guideline-audit step 6). In Arabic the newest month is on the left for both the labels and the line (mirror the SVG or stop mirroring the labels; check C07 for which). Check the Investments and Report trend charts for the same fault. Done when a browser test in Arabic finds the end dot's x within the newest label's column.

## 11L3 "To review 1", and no PC tab bar under Add · S · sonnet
Files: `lightning/ui/templates/phone/activity_home.html`, `lightning/ui/static/phone.css`, the phone Add page template. The count sits apart from the label (a gap, not a typed space). The Add page renders no section tab bar on the phone. Done when a test finds the chip's text "To review" and its count as separate boxes at least 4 px apart, and no `[role=tablist]` from the PC's sections on `/accounts/add-transaction` with `phone=True`.

## 11L4 Money's Coming up agrees with Bills; an empty Money says one line · S · sonnet
Files: `lightning/ui/phone/screens/money.py`, `lightning/ui/templates/phone/money.html`. Coming up shows the next bill before payday when Bills has one (or the line says "Nothing is due this week." if the week is what it means). With no account, Money shows the first-run line and Add account, not "0 accounts hold 0." or a change of 0. Done when a test covers both states.
