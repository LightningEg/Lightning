---
title: Phone-first architecture - five places that each answer one question, state-aware screens, and a phone decoupled from the PC
type: polish
look: visual
pillar: everywhere
size: L
status: ready
post: no
created: 2026-11-06
by: Claude
skills: guideline-audit, arabic-check, number-audit
app_version: 2.0.3
commit: 4af457b
repo: app
---

## Report
[The phone UX architecture report](r25-phone-ux-architecture/report.md) (owner, 2026-11-06: "The
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

**Owner decisions (2026-11-06), all as recommended:** D1 Home · Budget · Add · Activity · Money, Settings behind ⚙ on Money; D2 Home always today, without the stepper or Net worth; D3 old late bills become one catch-up question; D4 Part C is rewritten in both repos first. Recorded in the Project Overview's owner decisions.

`post: no`: the steps share the phone shell and follow one design.


## 3AY4 The phone shell: its own router, base, stylesheet and navigation · L
Built: (a) `lightning/ui/phone/` with `router.py` mounted first by `profile_app(..., phone=True)` (`mount_phone`,
`render_phone` that accepts only `templates/phone/` names), an import-linter contract that it does not import
`lightning.ui.routes`, and `tests/test_phone_shell.py`. (b) `phone/base.html` never extends or includes the PC base and
every phone-owned screen extends it (`tests/test_phone_own_base.py`). (c, part) the status bar takes the app bar's colour
(`<meta name="theme-color">` in `theme-runtime.js`, read again on every theme change; a browser test). (d) `phone/on_pc.html`
at `/pc` ("This is on your PC") and a `BEST_ON_PC` list in the router that gives a listed path the same page; the list is
empty on purpose (owner, 2026-11-08): Data checks and price files still work on the phone, so a path joins it only when its
phone version exists or the owner says it is PC-only.
Left: `phone.css` standalone on the theme tokens instead of layered on `style.css` (the bundle still starts with
`style.css`; the sub-pages that render PC markup in the phone frame need it until 3AY11 gives them phone screens); a stack
per slot with back-gesture order; IV-3F (the app bar looks too white; its colour is also the status bar's now).
Done when: a test fails if a phone route renders a template outside `templates/phone/`;
`tests/test_phone_nav_browser.py` and `tools/phone_check.py` pass.

## 3AY6 Home · M
Built: `workflows/todo.py` (To do order and rows), `ui/phone/screens/home.py` (the screen and its state: first run,
catch-up, payday, overspent, calm), `phone/home.html` at `/home` with the hero as the sheet to its working; at 412 x 915
it ends within 1.2 screens above the tab bar, the first Latest row is above 600 px and it shows at most 8 figures
(`tests/test_phone_home.py`). Left: serve it at `/` when the tab bar changes (3AY10); a catch-up flow for the To do row
(it links to Paste SMS for now); a phone To do "See all" page (it links to the PC's Needs you page for now).

## 3AY7 Add as a sheet over any slot · M
Amount first; Out / In / Move; the last account; chips by use; Paste SMS and Pay a bill at the top; a toast with the
category's left and Undo; returns to the slot it came from. Needs 3AY4 merged first. Done when: J1 is 3 taps and Save shows
with the keyboard open at 320 px.
Built: the Add slot passes the page it opened from, so Save returns there; the sheet says Move; *Pay a bill* (only when
bills are due) opens the phone-owned `/add/bills`, each row opening that bill's pay sheet; Save stays on screen with the
keyboard open at 320 px (`overflow-x: clip` so the sticky bar sticks; `tools/phone_check.py` checks it); the category chips
lead with what was typed by hand in the same part of the day; J1 is three taps in a real browser
(`tests/test_phone_add_browser.py`). The toast with the budget's left and Undo already existed. Left: the bill sheet's own
phone template (it still uses the PC's pay page).

## 3AY8 Activity with To review · L
All (the month, one money line, the day's net only with two or more rows, row sheets with category chips and a rule) and
To review (one card at a time over the review inbox's sortable items; *Not now* replaces Mark as reviewed and Snooze).
Needs 3AY4 merged first. Done when: the first row is above 330 px; one tap per reviewed item; clearing the queue clears
Home's To do row.
Built (first slice): `ui/phone/screens/activity.py` and `phone/activity_home.html` at `/activity` (phone app only): All
(the month, one In/Out line, the register's day nets, month stepper) and To review (one card over the review inbox's
activity items, "n of N", its one action, *Not now* snoozes it to tomorrow; an empty queue says "All sorted" and clears
Home's To do row). Left: row sheets with category chips and a rule, the card kinds that are rows (SMS, duplicates,
interest, recurring) instead of grouped items, search and filters, first row above 330 px measured.

## 3AY9 Budget, flexible first · L
Left in plan counts flexible spending only (a service, with the PC agreeing), needs attention, the category list without
fields, Fixed costs as one row, the category sheet, the *Make my plan* step and the payday strip. Needs 3AY4 merged first.
Done when: the first category row is above 400 px; Mohab's fixed costs no longer move the pace; skill `number-audit`
passes.
Built (first slice): `ui/phone/screens/budget.py` and `phone/budget_flexible.html` at `/budget/flexible` (phone app only):
the hero is everyday money left (the forecaster's EverydayBudget, the figure the PC's Everyday card shows, so the two
agree), the pace sentence, Needs attention (at most four, then "and N more"), every flexible category with *left* as the
figure and no field, bills and loans as one Fixed costs row, a past month without Needs attention, and the Make my plan
step with no plan. Left: the category sheet's own phone template, the payday strip, *This month in detail*, switching
`/budget` itself (3AY10 with the tab bar), running `number-audit`, the first-row-above-400-px measure.

## 3AY10 Money and its pages · L
Net worth with its sheet (parts, over time, US dollars and 21K gold); account balances (four, then more) with the line
that reconciles them with what you own; Coming up with no late rows; the Bills page; What you owe; Investments (holdings
first); an account with *Check against the bank*; Settings behind ⚙, with "Best on your PC" rows. Old URLs (`/more`,
`/plan`, `/accounts`, `/transactions`) redirect. Needs 3AY4 and 3AY5 merged first. Done when: any balance is one tap
from any slot, and bills are counted once.
Built (first slice): `ui/phone/screens/money.py` and `phone/money.html` at `/money` (phone app only): Net worth with the
change since the month began, Accounts (four, then "N more", each a link to the account, the held-for-others line),
Coming up (the next three, never late; late bills are one pointer to Home), and one row each for What you owe,
Investments, Goals and reserves, Financial health, Settings. Left: the net worth sheet (parts, over time, dollars and
gold), the Bills page (Late as one question), the Investments and account pages (*Check against the bank*), Settings
with "Best on your PC" rows, the tab bar switch, `/more` `/plan` `/accounts` `/transactions` redirects, bills counted once
across the Bills page, Coming up and Home.
Built since: `/money/accounts` (every balance, behind "N more"), `/money/bills` (Late, This week, Before payday, After payday
from the one bill state; Coming up is a slice of it, tested) and an *Edit your plan* row on the new Budget. Switched 2026-11-08: the tab bar is Home, Budget, Add, Activity, Money. The phone router serves `/` (once an account
exists; the empty profile keeps its welcome page), `/budget` (month only) and redirects bare `/more`, `/accounts` and
`/transactions`; a URL with any other query key still reaches the older page (`_plain` route class), so no link broke.
The old-page tests were moved to the new screens or to those query URLs. The Overview's period report ("how did my year
go?") now has a phone page at `/money/report` (month, last month, year, all time; Money links to it); the older
`/?period=month` Overview stays until 3AY11 removes it.

## 3AY11 Remove the old coupling · M
Delete the phone switches in `lightning/ui/routes/` (`on_phone`, `lazy_folds`, `request.state.phone`), `_phone_template`,
and the `phone/` templates the new screens replaced. Needs 3AY6 to 3AY10 merged first. Done when: `grep -rn "state.phone"
lightning/ui/routes` is empty and the full suite passes.
Built since: the old More is retired (route and template removed; `/more` leads to Money; its tests read Money and the Bills
page).
Not done (2026-11-08): the PC routes still carry phone branches (`getattr(request.state, "phone", False)` in about fifteen
places) because the sub-pages (account, register, investments, Cash planning, search, Settings) have no phone-owned
screens yet; the old slot templates also stay reachable at query URLs until the Overview report has a phone home.

## 3AY12 Arabic, themes and 320 px · M
Every new string in the catalogue, the mirrored layouts, dark and paid themes, 320 px. Needs 3AY6 to 3AY10 merged first.
Done when: skill `arabic-check` and `tools/theme_check.py` pass, and `tools/phone_check.py --arabic` passes.
Built: the new phone screens are in the no-English test and `tools/phone_check.py` (English and Arabic, 360 and 320 px);
`phone_check.py --theme id` wears a paid theme (maintainer review) and checks the same pages, run clean for dendera-night
(also in Arabic), papyrus, cotton and nile. `tools/theme_check.py` measures the PC layout only, so it does not cover the
phone. Left: a native Arabic reader on the voice of the strings added in 3AY6 to 3AY12.

## 3AY13 Owner's phone check · owner
One end-to-end check on a phone once 3AY12 is merged (it replaces 3AN13). Anything wrong becomes its own step.
