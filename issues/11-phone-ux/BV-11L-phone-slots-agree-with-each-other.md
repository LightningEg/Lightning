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

- **Two Left in plan.** Home's This month row and the PC say 6,598 (the whole plan, the Glossary's meaning); the phone's Budget hero says 5,468 (everyday money) under the same name. Decided 2026-11-09: the phone's figure is renamed (step 11L1). [texts](../12-desktop-ux/r35-ux-against-users-questions/evidence/phone/texts.json)
- **Arabic Money chart.** The month labels are mirrored (newest on the left) but the line and its end dot are not, so the latest value sits over the oldest month. [screen](../12-desktop-ux/r35-ux-against-users-questions/evidence/phone/money-arabic-chart.webp)
- **"To review1".** The count is a `<b>` after a space inside an inline-flex chip, so the space is lost (`lightning/ui/templates/phone/activity_home.html` line 10). [slots](../12-desktop-ux/r35-ux-against-users-questions/evidence/phone/sheet-home-budget-add-activity.webp)
- **A PC tab bar on the Add page.** `/accounts/add-transaction` on the phone ends with the PC's Import, Accounts, Held for others, Zakat bar under the form. [slots](../12-desktop-ux/r35-ux-against-users-questions/evidence/phone/sheet-home-budget-add-activity.webp)
- **"Nothing is due soon."** on Money while Money › Bills lists WE Internet and North Cairo Electricity under Before payday. [Money](../12-desktop-ux/r35-ux-against-users-questions/evidence/phone/sheet-money-accounts-bills-review.webp)
- **Empty Money prints zeros.** A new profile reads "0 accounts hold 0." and "0 since the start of the month." [first run](../12-desktop-ux/r35-ux-against-users-questions/evidence/phone/sheet-first-run-and-add-sheet.webp)

## Fix

One name, one figure, and nothing left over from the PC. One PR per step; each step's test is named in it.

## How to work on this item

Read only the files a step names; `python tools/guideline.py C11` prints the phone screens' rules. After each step: the step's test, `python tools/phone_check.py` and `python tools/phone_check.py --arabic`, then `python -m pytest tests/test_mohab_year.py -q`. Delete the step's heading in the same commit.

## 11L1 Phone Budget's lead is named "Left for everyday" · S · sonnet
Owner decision 2026-11-09 (audit r36 F3, [report](r36-figures-one-owner/report.md)): "Left in plan" keeps its Glossary meaning (Planned − Spent, 6,598 in the demo) on every screen, so Home's This month row is right as it is. The phone's Budget keeps leading with everyday money (5,468) under its own name. Files: `lightning/core/figures.py` (a registry row `everyday_left`, "Left for everyday", function `planning.domain.EverydayBudget.everyday_left`; then `python -m lightning.core.figures`), `lightning/ui/phone/screens/budget.py` (read `e.everyday_left`; line 71 subtracts it again today), `lightning/ui/templates/phone/budget_flexible.html`, the Arabic label, guideline C11.2 in both repos. Done when phone Budget shows "Left for everyday" from the registry label and no screen shows two values under "Left in plan" (IT-12AE1's comparison passes).

## 11L3 "To review 1", and no PC tab bar under Add · S · sonnet
Files: `lightning/ui/templates/phone/activity_home.html`, `lightning/ui/static/phone.css`, the phone Add page template. The count sits apart from the label (a gap, not a typed space). The Add page renders no section tab bar on the phone. Done when a test finds the chip's text "To review" and its count as separate boxes at least 4 px apart, and no `[role=tablist]` from the PC's sections on `/accounts/add-transaction` with `phone=True`.

## 11L4 Money's Coming up agrees with Bills; an empty Money says one line · S · sonnet
Files: `lightning/ui/phone/screens/money.py`, `lightning/ui/templates/phone/money.html`. Coming up shows the next bill before payday when Bills has one (or the line says "Nothing is due this week." if the week is what it means). With no account, Money shows the first-run line and Add account, not "0 accounts hold 0." or a change of 0. Done when a test covers both states.
