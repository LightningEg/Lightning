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

**Owner picks (2026-11-11), all as recommended:** 3AY8 each review card's Primary is its kind's own verb (SMS *Looks right*, duplicate *Delete the copy*, interest *Match to deposit*, recurring *Track it*), with *Change* and *Skip* beside it; 3AY9 the payday strip shows from the salary's day until this month's plan is saved; 3AY10 the Net worth sheet is the parts, then US dollars and 21K gold as two rows; the small 12-month line stays right under the hero (once).

`post: no`: the steps share the phone shell and follow one design.

**State (2026-11-10).** The five slots, the one bill state, catch-up and the decoupling are built: no PC route asks who is
looking (`tests/test_phone_decoupled.py`). How a phone page is made now (screen, presenter, or a PC template in the phone
frame) is in Architecture › UI contract › *The phone is its own layer*; read it before any step below. Steps marked
`sonnet` name their files and their proof; the `opus` ones still need a design choice.


## 3AY8 Activity: a card for possible duplicates · S · opus
Built (2026-11-11): To review is one row per card (`phone/screens/review_cards.py`), each with its kind's own verb (owner
pick): a row to sort *Looks right* (its payee's usual category, one tap) or *Choose a category*; a payment that looks
monthly *Track it*; deposit interest *Match to deposit*; a bank message *Looks right*; Change and Skip beside it, Not now
on inbox items (`tests/test_phone_review_cards.py`). Activity has search and Out / In / Transfers. Left: possible
duplicates have no card, because no service lists them (they are merged from the register). Add a duplicate finder in
`lightning/transactions/`, then a card whose Primary is *Delete the copy* (the merge, with Keep both beside it).

## 3AY13 Owner's phone check · owner
One end-to-end check on a phone once 3AY4, 3AY8 and 3AY9 are merged (3AY9: commit on `claude/o7-phone-slots`, `tests/test_phone_budget_flexible.py`) (it replaces 3AN13), including a native reader's pass over the Arabic
of the strings added in 3AY6 to 3AY12 and the catch-up screen. Anything wrong becomes its own step.
