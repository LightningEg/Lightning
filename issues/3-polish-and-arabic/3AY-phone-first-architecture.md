---
title: Phone-first architecture - five places that each answer one question, state-aware screens, and a phone decoupled from the PC
type: polish
look: visual
pillar: everywhere
size: L
status: new
post: no
created: 2026-11-06
by: Claude
skills: guideline-audit, arabic-check, number-audit
app_version: 2.0.3
commit: 4af457b
repo: app
---

## Report
[The phone UX architecture report](../../reports/2026-11-06-phone-ux-architecture/report.md) (owner, 2026-11-06: "The
phone UI is not usable. I want a full architecture design, tab by tab, on how to make it usable. Do it as a UX designer
and think of the user journey. Phone is decoupled from PC").

After Audits 10 and 13 the quick jobs take three taps or fewer, but the phone is still a PC dashboard set out as one column.
One question gets four answers: bills are counted 17, 7, 13 and "11,760 due before payday" on the same day. A week away
turns into a wall of red "34 days late" rows. Home changes meaning when the month changes. 78 of the 104 page templates
have no phone version, so the phone shows PC markup. Findings F1-F13 are in the report.

## Fix
The report's design: **Home** (Safe to spend, To do, Latest, This month; always today), **Budget** (flexible Left in plan,
needs attention, categories, Fixed costs as one row; months live here), **Add** (a sheet, amount first), **Activity**
(All plus To review, one card at a time), **Money** (Net worth, the balances themselves, Coming up, what you owe,
investments, goals; Settings behind ⚙). One bill state and a catch-up state are worked out in Python services. The phone
gets its own router, screens and stylesheet, and never falls back to a PC page.

**Done when** the report's Acceptance holds: J1-J10 at their targets; Home in 1.2 screens with at most 8 figures; one bill
count everywhere, on a fresh profile and on one left alone for a week; no phone URL renders a PC template; A16 and
`tools/phone_check.py` pass; then the owner's one end-to-end phone check.

`post: no`: the design waits on the owner's decisions (3AY2), and the steps share the phone shell.

## 3AY1 Four state and copy bugs on today's screens · S
Ship before the redesign. (a) The Net worth tile says "Today" over a past month's figure, and on a past month the hero
repeats the tile (`routes/dashboard.py` `_worth_tile`): the tile names its date, and the hero never shows the same figure as
a tile. (b) "N new transactions since your last visit on <today>": never name today, and count a bulk import or a sample
load as one event (`since`). (c) "Net worth · in us dollars": stop lower-casing the label (`phone/dashboard/index.html`).
(d) Late bills listed under "Next 14 days" on More: the heading says what the rows are, or late rows move to their own
heading. Done when: a test for each in `tests/test_phone_*.py`, and Mohab passes.

## 3AY2 Owner decisions D1-D4 · owner
The tab bar (Home · Budget · Add · Activity · Money), Home without the stepper and without Net worth, late bills as one
catch-up question, and the Part C rewrite. Asked as a pick-list; record the answers here and in the Project Overview's
owner decisions.

## 3AY3 Guideline Part C rewrite, in both repos · M
C01.1 "Same brand, own structure"; C03.1 the tab bar; C04.2 the stepper only on Budget and Activity; C04.4 To do and To
review; C11.1 Home; C11.3 Money; new C13 States. Needs 3AY2 merged first. Done when: the website's `guideline/` copy is
the same (`cmp`), a PR is open in each repo, and `tests/test_docs_structure.py` passes with the sibling repo present.

## 3AY4 The phone shell: its own router, base, stylesheet and navigation · L
`lightning/ui/phone/` mounted only by `profile_app(..., phone=True)`, with an import-linter contract that it does not
import `lightning.ui.routes`. `phone/base.html`, and a `phone.css` standalone on the theme tokens. A stack per slot,
back-gesture order, the "This is on your PC" page in place of any PC fallback, figures always at the right edge, and
status-bar icons that follow the theme (with IV-3F). Needs 3AY3 merged first. Done when: a test fails if a phone route
renders a template outside `templates/phone/`; `tests/test_phone_nav_browser.py` and `tools/phone_check.py` pass.

## 3AY5 One bill state and the catch-up state · L
`lightning/planning/bill_state.py`: each payment's state for a day (late and stale, late, due soon, before payday, later,
paid, skipped), plus days since the last entry and imports recorded as one event. The PC's Cash planning and Needs you read
it too. Done when: on Mohab's year, and on the same profile a week later with nothing recorded, Home's To do, Money's
Coming up, the Bills page and Safe to spend agree (`tests/test_bill_state.py`), and skill `number-audit` passes.

## 3AY6 Home · M
Safe to spend with its working as a sheet, To do (three rows, one action each, *See all*), Latest five, This month; the
first-run, catch-up, payday, overspent and calm states. Needs 3AY4 and 3AY5 merged first. Done when: 1.2 screens and at
most 8 figures at 412 × 915; the first Latest row above 600 px; each state has a test on a dummy profile.

## 3AY7 Add as a sheet over any slot · M
Amount first; Out / In / Move; the last account; chips by use; Paste SMS and Pay a bill at the top; a toast with the
category's left and Undo; returns to the slot it came from. Needs 3AY4 merged first. Done when: J1 is 3 taps and Save shows
with the keyboard open at 320 px.

## 3AY8 Activity with To review · L
All (the month, one money line, the day's net only with two or more rows, row sheets with category chips and a rule) and
To review (one card at a time over the review inbox's sortable items; *Not now* replaces Mark as reviewed and Snooze).
Needs 3AY4 merged first. Done when: the first row is above 330 px; one tap per reviewed item; clearing the queue clears
Home's To do row.

## 3AY9 Budget, flexible first · L
Left in plan counts flexible spending only (a service, with the PC agreeing), needs attention, the category list without
fields, Fixed costs as one row, the category sheet, the *Make my plan* step and the payday strip. Needs 3AY4 merged first.
Done when: the first category row is above 400 px; Mohab's fixed costs no longer move the pace; skill `number-audit`
passes.

## 3AY10 Money and its pages · L
Net worth with its sheet (parts, over time, US dollars and 21K gold); account balances (four, then more) with the line
that reconciles them with what you own; Coming up with no late rows; the Bills page; What you owe; Investments (holdings
first); an account with *Check against the bank*; Settings behind ⚙, with "Best on your PC" rows. Old URLs (`/more`,
`/plan`, `/accounts`, `/transactions`) redirect. Needs 3AY4 and 3AY5 merged first. Done when: any balance is one tap
from any slot, and bills are counted once.

## 3AY11 Remove the old coupling · M
Delete the phone switches in `lightning/ui/routes/` (`on_phone`, `lazy_folds`, `request.state.phone`), `_phone_template`,
and the `phone/` templates the new screens replaced. Needs 3AY6 to 3AY10 merged first. Done when: `grep -rn "state.phone"
lightning/ui/routes` is empty and the full suite passes.

## 3AY12 Arabic, themes and 320 px · M
Every new string in the catalogue, the mirrored layouts, dark and paid themes, 320 px. Needs 3AY6 to 3AY10 merged first.
Done when: skill `arabic-check` and `tools/theme_check.py` pass, and `tools/phone_check.py --arabic` passes.

## 3AY13 Owner's phone check · owner
One end-to-end check on a phone once 3AY12 is merged (it replaces 3AN13). Anything wrong becomes its own step.
