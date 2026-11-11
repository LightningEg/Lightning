---
title: Phone-first architecture - five places that each answer one question, state-aware screens, and a phone decoupled from the PC
type: polish
look: visual
pillar: everywhere
size: L
model: opus
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

**Owner picks (2026-11-11), all as recommended:** 3AY8 each review card's Primary is its kind's own verb (SMS *Looks right*, duplicate *Delete the copy*, interest *Match to deposit*, recurring *Track it*), with *Change* and *Skip* beside it; 3AY9 the payday strip shows from the salary's day until this month's plan is saved; 3AY10 the Net worth sheet is the parts, a small 12-month line, then US dollars and 21K gold as two rows.

`post: no`: the steps share the phone shell and follow one design.

**State (2026-11-10).** The five slots, the one bill state, catch-up and the decoupling are built: no PC route asks who is
looking (`tests/test_phone_decoupled.py`). How a phone page is made now (screen, presenter, or a PC template in the phone
frame) is in Architecture › UI contract › *The phone is its own layer*; read it before any step below. Steps marked
`sonnet` name their files and their proof; the `opus` ones still need a design choice.


## 3AY4 The phone stylesheet stands alone, and each slot keeps its stack · L · opus
Built: the router, `phone/base.html`, the status bar colour, "This is on your PC" (`BEST_ON_PC` empty on purpose, owner
2026-11-08). Left, in this order:
(a) `phone.css` standalone on the theme tokens. 3AY15-17 are built (2026-11-11): `tests/phone_pc_templates.txt` is empty and no
PC template asks `phone_mode()`. Now drop `style{rtl}.css` from `PHONE_CSS` (`ui/web.py`) and move into `phone.css` only the
rules the phone templates still use (they keep some shared classes: `field`, `import-check`, `category-sheet*`, `money-input`,
the import review's and reserves' own classes).
(b) A stack per slot: tapping the chosen slot returns to its top; Android back pops within the slot, then Home, then
leaves (`static/phone-nav.js`; report r25 › Cross-cutting 5).
Done when: `PHONE_CSS` has no `style` entry, `tools/phone_check.py` and `tools/phone_check.py --arabic` pass, and
`tests/test_phone_nav_browser.py` proves the back order.

## 3AY8 Activity: the review cards that are rows, and search · M · opus
Built: All and To review (one card, *Not now*), and a row's own sheet with category chips, now the phone router's
(`/transactions/{id}/sheet`, `ui/row_sheet.py`). Left: the card kinds that are single rows (SMS, duplicates, interest,
recurring) instead of grouped items; search and filters on `/activity` (today they are on `/transactions`); a rule
offered from the sheet. Needs a choice of what each card's one action is. Done when: one tap per reviewed item for every
kind, and `tools/phone_check.py` shows the first row above 330 px.

## 3AY9 Budget: the payday strip and This month in detail · M · opus
Built: `/budget` flexible first. Left: the payday strip, *This month in detail* (what replaces the older
`phone/budget.html`, which *Edit your plan* still opens through `presenters/budget.py`), then skill `number-audit` on the
flexible figure. Done when: the first category row is above 400 px, Mohab's fixed costs do not move the pace, the audit
passes, and `phone/budget.html` with its presenter is deleted.

## 3AY10 Money: the net worth sheet, then the older Overview goes · M · opus
Built: Money, `/money/accounts`, `/money/bills`, `/money/report`, the redirects. Left: Net worth's sheet (parts, over
time, US dollars and 21K gold): the parts are what the older Overview's sheets show (`phone/dashboard/index.html`,
`presenters/overview.py`). When the sheet has them: the phone router answers `/` for every query (a period link goes to
`/money/report`, an empty profile gets its own `phone/welcome.html`), and `phone/dashboard/`, `presenters/overview.py`
and the phone router's `/overview/fold/{name}` are deleted. Also left: an account page with *Check against the bank* first, and
Settings rows marked "Best on your PC". Done when: no phone URL renders `phone/dashboard/index.html` and
`tests/test_backend_roadmap.py` has a query budget for Home instead of the Overview.

## 3AY13 Owner's phone check · owner
One end-to-end check on a phone once 3AY10 is merged (it replaces 3AN13), including a native reader's pass over the Arabic
of the strings added in 3AY6 to 3AY12 and the catch-up screen. Anything wrong becomes its own step.
