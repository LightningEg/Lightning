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

`post: no`: the steps share the phone shell and follow one design.

**State (2026-11-10).** The five slots, the one bill state, catch-up and the decoupling are built: no PC route asks who is
looking (`tests/test_phone_decoupled.py`). How a phone page is made now (screen, presenter, or a PC template in the phone
frame) is in Architecture › UI contract › *The phone is its own layer*; read it before any step below. Steps marked
`sonnet` name their files and their proof; the `opus` ones still need a design choice.


## 3AY4 The phone stylesheet stands alone, and each slot keeps its stack · L · opus
Built: the router, `phone/base.html`, the status bar colour, "This is on your PC" (`BEST_ON_PC` empty on purpose, owner
2026-11-08). Left, in this order:
(a) `phone.css` standalone on the theme tokens. The bundle (`PHONE_CSS` in `ui/web.py`) still starts with `style.css`,
because the 78 pages in `tests/phone_pc_templates.txt` are PC markup in the phone frame. Do it after 3AY15 to 3AY18 empty
that list: then drop `style{rtl}.css` from `PHONE_CSS` and move into `phone.css` only the rules the phone templates use.
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
and the route `/overview/fold/{name}` are deleted. Also left: an account page with *Check against the bank* first, and
Settings rows marked "Best on your PC". Done when: no phone URL renders `phone/dashboard/index.html` and
`tests/test_backend_roadmap.py` has a query budget for Home instead of the Overview.

## 3AY14 To do's "See all" page · S · sonnet
Home's *See all n* opens the PC's Needs you page. Add `screens/todo.py` (`build(c, day)`: the same `todo_rows` Home
calls, not cut to three; copy the calls from `screens/home.py`), `templates/phone/todo.html` (the To do rows of
`phone/home.html`, back to Home), a route `/todo` in `phone/router.py`, and point Home's link at it. New strings go in
`ui/i18n.py`. Done when: a test in `tests/test_phone_home.py` shows `/todo` lists every row `todo_rows` returns, Home links
to it, `/todo` is in `NEW_PHONE_SCREENS` (`tests/test_arabic_no_english.py`) and in `tools/phone_check.py`'s `PAGES`.

## 3AY15 Phone templates: the sheets the slots open · M · sonnet
Give each a `templates/phone/<same name>` that extends `phone/base.html` and uses the phone parts (`phone-section`,
`phone-rows`, `phone-row`, `partials/sheet.html`): `planning/pay.html` (the bill's pay sheet; Add and Catch up open it),
`budget/category_sheet.html`, `planning/early_payment.html`, and the popups under `transactions/` and `categories/` in
`tests/phone_pc_templates.txt`. The route does not change: `presenters.phone_template` picks the phone file by its
name. Delete each finished line from the list. Done when: `tests/test_phone_decoupled.py` and `tests/test_phone_own_base.py`
pass, and `tools/phone_check.py` (English and `--arabic`) passes with the sheet's address added to `PAGES`.

## 3AY16 Phone templates: Investments and Cash planning pages · M · sonnet
The same as 3AY15 for the `investments/` (12) and `planning/` (8 left) lines of `tests/phone_pc_templates.txt`. Follow
`phone/investments/index.html` and `phone/planning/plan.html`. A page that is only practical on a PC (price files, the
planner's bulk grid) is not given a template: list it for the owner in a GitHub issue as a `BEST_ON_PC` candidate and
leave its line. Done when: as 3AY15.

## 3AY17 Phone templates: Settings, rules, exports and the top-level pages · L · sonnet
The same as 3AY15 for the `settings/` (7), `rules/`, `exports/`, `analysis/`, `accounts/`, `birdview/`, `dashboard/` and
top-level (27) lines. `financial_health.html` is one of them: its phone template replaces the `phone_mode()` tests inside
it (`presenters/health.py` stays). Done when: as 3AY15, and `grep -rn "phone_mode()" lightning/ui/templates --include=*.html`
finds nothing outside `templates/phone/` and `partials/`.

## 3AY18 The last phone routes leave the PC files · S · sonnet
`tests/phone_routes_in_pc_files.txt` names three PC route files that still hold a route drawing a phone template:
`accounts.py` (`/accounts/add-transaction`, `phone/accounts/pick.html`), `budget.py`
(`/budget/category/{id}/payments`, `phone/budget_payments.html`; move `_last_payments` and `_tree_ids` to
`ui/budget_rows.py`) and `dashboard.py` (`/overview/fold/{name}`; skip it if 3AY10 deleted it). Move each route to
`phone/router.py` with `render_phone`, as `/birdview/expenses/more` was moved. Done when: that file lists nothing and
`tests/test_phone_decoupled.py`, `tests/test_architecture.py` and the routes' own tests pass.

## 3AY13 Owner's phone check · owner
One end-to-end check on a phone once 3AY10 is merged (it replaces 3AN13), including a native reader's pass over the Arabic
of the strings added in 3AY6 to 3AY12 and the catch-up screen. Anything wrong becomes its own step.
