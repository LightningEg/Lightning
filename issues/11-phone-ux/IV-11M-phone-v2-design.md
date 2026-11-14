---
title: The phone wears design v2.0, screen by screen, as the owner's mockup shows
type: polish
look: visual
pillar: feel
size: L
model: opus
github: 658
status: building
created: 2026-11-14
by: Claude
---

## Report
The owner gave "Lightning phone mockups v2.0" (22 screens at 390 px, 2026-11-14): Welcome, Your profile, Recovery key, Home first day, Home, Add, a transaction, Home in Dendera, Budget (Categories, Spending, Edit plan, one category), Plan (Coming up, Recurring, Loans, Reserves), Money, Activity, To review, Investments, one account, Settings. The mockup file stays with the owner (6 MB, embedded fonts); this item records what it asks. "It might not go 1:1 with our phone": where our figures differ, ours win and the layout follows the mockup.

Today's phone (sample household, `python tools/phone_check.py --shots <dir>`) is flat rows on the page gradient: no cards around lists, the Lead without a card, Activity in the tab bar, Cash planning reached from Money.

## Owner decisions (2026-11-14)
1. **Tab bar:** Home · Budget · Add · Plan · Money. Plan is Cash planning (Coming up, Recurring, Loans, Reserves). Activity and To review open from Money ("‹ Money  Activity").
2. **Guideline:** Part C is rewritten to v2.0 (cards, heroes, header rows, the tab bar), English and Arabic, in both repositories.
3. **Content:** match the mockup fully: what a page leads with and the features it shows that we lack (first-day steps, Work claims on Budget, the gameya turn grid, goals with progress, the To review card flow) are built, not left out.
4. **Delivery:** a foundation pull request, then one per area.

## The v2.0 language (from the mockup)
- **Frame:** app bar 64 tall, mark then the page's name (Bricolage 17/700), Search and Hide amounts; an inner page shows "‹ Section  Page". Tab bar 84 tall, white, a hairline on top; the chosen slot's icon sits in a 52×30 Meadow-pale pill (`#D7F0E3`), its word 12/800 Ink; others Muted 12/600. Add is a 56 px Nile disc raised 26 px with a 5 px white ring.
- **Hero card** (each page's Lead): 28 px corners, 22/20 padding, a soft green-to-azure wash, a white 1 px edge, two outline lightning marks in the top-right corner at 15-20% opacity; label with › (14/700 Ink-2), the figure at 44 (Bricolage 800) with EGP 14/700, one sentence whose verdict is bold in its meaning's colour ("**On pace.**"), then either a two-well pair (white 70% wells, 16 px corners, label 12.5 Muted, figure 18/700) or a ring (84 px, "59% spent") on the right.
- **List card:** white, 24 px corners, 1 px `#DDE9E6` edge, shadow `0 14px 34px -24px rgba(10,36,66,.42)`. A header row tinted by meaning (rose for To do and spending, azure for Latest and Activity, green for income, reserves and health) holds a 38 px white icon tile, the title (Bricolage 17/700), a 12.5 px Muted subtitle and "All 5 ›" on the right. Rows 64-66 tall: a 40 px round chip by meaning, name 15.5/700, note 13 Muted, the figure or a pill action (Pay on Nile, others on a pale well), hairlines inset 68 px.
- **Segmented track:** a pale well, the chosen tab white with a soft shadow, 13.5/700.
- **Quick actions** (Home): four 60 px tiles, 20 px corners, Expense rose, Income green, Transfer azure, From SMS white, the word under each.
- **A dashed card** offers what is not set up yet (Looks recurring "Make it a bill", Fixed bills from Plan).
- **Month stepper:** two 40 px white round buttons and the month in the middle with a calendar icon.
- Themes recolour it through tokens only (screen 08 is Home in Dendera).

## 11M1 Foundation: the v2.0 frame and parts · L · opus · #659
Tokens and parts in `static/phone.css` (token-only, themes keep working): app bar, tab bar with the Plan slot (`phone/base.html`, `ui/sections.py` for which slot a page keeps chosen, `phone-nav.js` stacks), the hero card, the list card with its header row, rows and pill actions, KPI wells, segmented track, quick-action tiles, dashed offer card, month stepper. Money lists Activity and To review. Done when: the tab bar reads Home · Budget · Add · Plan · Money in English and Arabic; every Plan page keeps Plan chosen and Activity keeps Money chosen; existing pages wear the new cards without sideways scroll at 360 and 320 (`tools/phone_check.py`); `tests/test_phone_frame.py`, `tests/test_mohab_phone.py` and Mohab pass.

## 11M2 Guideline Part C v2.0 in both repositories · M · opus · #660
`guideline/phone.html` and `phone-ar.html` say the v2.0 rules (C03 tab bar, C04 heroes, C06 cards, C08 list cards, C11 screens); the same files in the website repository in its own pull request (`cmp` passes); `tests/test_docs_structure.py` passes. Needs 11M1 merged first.

## 11M3 Home and the first day · L · opus · #661
Greeting; "In your accounts" hero with the share bar and the accounts; Safe to spend card with ring, verdict and two wells (Left in budget, Bills before payday); four quick actions; To do card with pill actions; Latest card. First day: "Safe to spend · 3 steps away" with a 0/3 ring and the Get your number steps (salary account, payday, first payment), Paste a bank SMS instead. Needs 11M1 merged first.

## 11M4 Add and a transaction · L · opus · #662
Add sheet: Expense/Income/Transfer track, Paste a bank SMS, Log again chips, the big amount in its meaning's colour, account and date chips, category chips with More, the keypad, Save expense. A transaction's sheet: tinted hero with the amount, Category (with "left after this"), Account (balance after), Date, Note rows; the SMS rule offer with Yes; Split it and Edit; Delete this transaction. Needs 11M1 merged first.

## 11M5 Budget · L · opus · #663
"Left for everyday" hero with ring and Planned/Spent wells; month stepper; Categories/Spending/Edit plan. Categories: a Personal card with progress per category and a Work card (paid for the company, to claim back, Claim); Fixed bills and savings as a dashed link to Plan. Spending: Where it went donut with four then Other, Six months bars with the usual line, Daily average and Biggest day tiles. Edit plan: "Left to plan" hero (Every pound has a job), Income/Planned wells, one well input per category with its usual, the Fixed bills card from Plan, Copy last month and Save plan. One category: over/left hero with the plan marker, Raise the plan and Move money, the usual-month note, This month's payments. Needs 11M1 merged first.

## 11M6 Plan · L · opus · #664
Coming up: "Due before payday" hero with the verdict, Coming in/Going out wells and a timeline to payday; Before payday and After payday cards with Pay. Recurring: "Every month" hero with Bills/Loans and savings wells, the dashed Looks recurring offer (Make it a bill), Bills and Savings and loans cards. Loans: "What you owe" hero with This month/Paid so far, each loan with progress and its next payment, the Gameya card with the turn grid. Reserves: "Set aside" hero with the goals ring and Reserves/Goals wells, Reserves and Goals cards with progress, Add and Done. Needs 11M1 merged first.

## 11M7 Money, Activity and To review · L · opus · #665
Money: Net worth hero with What you own/What you owe; Accounts, Activity (All transactions, To review), Investments and Health and planning cards. Activity: All/To review track, search, chips, month stepper, In/Out wells, one card per day with its net. To review: "1 of 4" with a progress bar, the message's card (chip, payee, amount, account and time, the SMS quoted, category chips, Always file here), Looks right, Change, Skip, and Up next. Needs 11M1 merged first.

## 11M8 Investments, one account, Settings and the welcome · L · opus · #666
Investments: Portfolio value hero with the allocation bar, Update prices and Record a buy, Six months line, Holdings with each change, the "best on your PC" note. One account: its header tile, Balance hero with In/Out this month, Transfer money and ⋯, day cards with the balance after. Settings: the profile card, How it looks, Your data and Safety cards. Welcome, Make it yours and Recovery key in the v2.0 look. Needs 11M1 merged first.

## 11M9 Paid themes wear v2.0 · M · sonnet · #667
Every theme in `tools/theme_shots.py` shows the hero, list cards and tab bar in its own colours (screen 08: Dendera's paper wash, gold edge, the frieze under the app bar); `tools/theme_check.py` passes. Needs 11M3 merged first.
