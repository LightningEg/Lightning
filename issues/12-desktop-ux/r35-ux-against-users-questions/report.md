# Audit 16: does every screen answer its user's question? Cohesion, efficiency and smart features

Date: 2026-11-09 · Author/reviewer: Claude
Repository: app · Reviewed commit: 90f01900587841fa8fdea859fbf9f2cc8314140a
Code: r35 · App version: 2.1.2

## Assessment

The guideline gives every page one question (A09.1 on the PC, C03 on the phone). Measured against those questions, Lightning's **content is right and its frame is not yet one product**. The pages the guideline names mostly lead with the right figure: Cash planning, Budget, Accounts and the phone's Home and Budget answer in the first screen. What stops the app feeling polished is smaller and more frequent:

1. **The same thing sits in a different place on each tab.** 13 of 24 PC tabs have no answer sentence, the page title is the section on six tabs and the tab on eleven, Undo moves between the header and a second row, and the period bar has three forms.
2. **Small contradictions between screens.** The phone's Home and Budget give two figures called Left in plan; Money says net worth fell this month while its chart and the Report say it rose.
3. **Long pages and repeated lists.** Three PC tabs run past three screens; Cash planning lists the same late bills twice.
4. **Smart features that stop one step short.** Suggestions exist, but their defaults and counts are blunt (Refill offers to take Safe to spend to 0; Overview says "Needs you · 17" over one row), and the way to see how a figure is worked out has six different names.

Nothing here is wrong money in the ledger. One finding (F1) is a wrong sentence on a headline figure.

## Owner direction (asked in this session, 2026-11-09)

| Question | Answer |
| --- | --- |
| Which surface first? | **Phone first** (Google Play is the next launch), then the PC. |
| How strict is cohesion on the PC? | **One skeleton, enforced by a test.** Every tab: title, answer sentence, dates, then the same controls in the same order. |
| Which kinds of smart? | **All four:** notices and proposes the next step; does repeated work; explains every figure in place; answers a typed question. Always a suggestion the user confirms. |
| Long PC pages? | **The answer on one screen, the rest on request.** |

## Scope and method

Every PC section tab and its main sub-pages (32 pages) on Mohab's sample year (`--sample`, date pinned to 2026-10-21, prices offline) at 1366 × 768: one first-screen and one full-page capture each, with the title, answer sentence, page length in screens, cards and controls measured from the page. Every phone page `tools/phone_check.py` visits (45 pages at 360 px) on the demo household, plus a new profile's first run, the Add sheet opened from Home, and the five slots in Arabic. Six PC pages were repeated in Arabic. Each page was read against its question in A09.1 or C03, then against A09 (page order), A09.2 (one home, less on screen) and A16. Figures that disagreed were traced to the line of code.

Earlier audits were read first (r19, r24, r26, r27, r28, r29) and their open items are linked, not filed again.

## Scorecard: the question, and what the first screen says

**PC** (A09.1; ✓ answers it, ◐ partly, ✗ does not).

| Page | Its question | Answer sentence | Lead | Screens | Verdict |
| --- | --- | --- | --- | --- | --- |
| Overview | Where do I stand, and what needs me? | "You kept 93% of what came in this month." | Net worth ✓ | 1.5 | ◐ The sentence answers a saving question, not standing. Needs you shows "17", one row "· 7" and "Show all 4" (F9). |
| Spending | Where did my money go? | ✓ | Three KPI cards, no Lead card | 4.1 | ◐ Opens on last month while every other tab opens on this month; the categories start at the fold (F5, F6). |
| Budget | How much can I still spend this month? | "You are 10,105 under your plan's pace." | Left in plan ✓ | 2.1 | ✓ The sentence could say the amount left. A loose Ask an AI paragraph sits between cards (F8). |
| Cash planning | How much is safe to spend before payday? | ✓ | Safe to spend, worked out beside it ✓ | 4.0 | ✓ The best page. Late bills appear twice; a card sits in the Lead card (F7). |
| Reserves | Am I safe if something goes wrong? | none, no dates | "0.5 months" banner ✓ | 2.2 | ◐ A refill form comes before the fund's own state; "The aim is six" here, "Below 3 months" on Limits (F10). |
| Limits | How do my figures compare with my limits? | ✓ | "5 of the 6" ✓ | 2.0 | ◐ The working beside the Lead is a savings-rate chart, not the limits. |
| Investments | What do I hold, and how is it doing? | ✓ | Portfolio value ✓ | 3.4 | ◐ Cost is 325,088 in the Lead and 725,088 in the table; "What changed" is five rows of 0 EGP (F6). |
| Accounts | Where is my money? | ✓ | What you own, How it adds up ✓ | 2.2 | ✓ |
| Transactions | What happened? | none | a register | 3.3 | ◐ The filled (primary) button is "Choose an account" (F8). |
| Compare periods | (answer strip) | ✓ | Money out ✓ | 1.3 | ✓ |
| Reports | (answer strip) | none | three cards | 1.0 | ◐ "+315,749 against 0 before" in rose: a year compared with nothing (F11). |
| Recurring, Loans | follow-ups of Cash planning | none | KPIs / Loans still to pay | 2.6 / 2.0 | ◐ No sentence, no dates. |
| Currencies | follow-up of Investments | one technical sentence | four KPI cards | 1.8 | ◐ Its own period bar (All time, YTD, Month, Custom), unlike every other tab (F5). |
| Settings tabs | Is my data right? | mixed | forms | 1.0 to 3.2 | ◐ Ask an AI takes two fifths of Your data (F8); Data checks says it passes three times. |

**Phone** (C03).

| Slot | Its question | First screen | Verdict |
| --- | --- | --- | --- |
| Home | Am I OK today, and what do I do next? | Safe to spend 51,420, To do, Latest | ✓ "This month · Left in plan 6,598" is not Budget's Left in plan 5,468 (F2). |
| Budget | How much is left, and on what? | Left in plan 5,468, Needs attention | ✓ The figures at the end of each category row have no name; a full category shows "—". |
| Add | Record it now. | the sheet | ◐ Opened from Home, the focus is on Out/In/Move, not Amount (r27 J1, seen again). The Add page shows the PC's Import, Accounts, Held for others, Zakat bar under the form (F3). |
| Activity | What moved, and what needs sorting? | In and Out, the days | ✓ The chip reads "To review1" (F3). |
| Money | What do I have, what do I owe, what is coming? | Net worth, What you own, Accounts | ◐ The sentence is wrong (F1); the Arabic chart runs against its labels (F3); "Nothing is due soon." with two bills before payday (F3). |
| First run | | Welcome, then "Three steps to your first answer" | ◐ The currency gate and the empty Activity are IV-11A (open). Empty Money says "0 accounts hold 0." and "0 since the start of the month." |

Reached from Money, the phone's Investments, Cash planning, Financial health and Reserves are still the PC's pages in one column (IV-3AY11, open).

## Findings

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F1 | medium | **Phone Money: "−10,438 since the start of the month" while the chart rises and the Report says +31,895.** `position.at(day.replace(day=1))` is the end of day 1, after the salary and the first bills, so the month's change leaves out the first day. Expected: the change from the last month's end, the same figure the Report shows. | [texts](evidence/phone/texts.json), [Money](evidence/phone/money-english-chart.webp); `lightning/ui/phone/screens/money.py:104` | [BT-11K](../../11-phone-ux/BT-11K-phone-money-change-since-month-start.md) |
| F2 | medium | **Two figures named Left in plan on the phone.** Home's This month row says 6,598 (the whole plan, `plan["left"]`); Budget's hero says 5,468 (everyday money, C11.2). The 1,130 between them is a bill not yet paid. Expected: one name, one figure; Home's row repeats Budget's. | [texts](evidence/phone/texts.json); `lightning/ui/phone/screens/home.py:105` | [BV-11L](../../11-phone-ux/BV-11L-phone-slots-agree-with-each-other.md) |
| F3 | low | **Phone finish.** (a) In Arabic the Money chart's labels are mirrored (newest on the left) but the line is not, so the latest dot sits over the oldest month. (b) "To review1": the count touches the label. (c) The Add page shows a PC tab bar under the form. (d) Money says "Nothing is due soon." while Bills lists two before payday. (e) Empty Money prints zeros as sentences. | [Arabic chart](evidence/phone/money-arabic-chart.webp), [slots](evidence/phone/sheet-home-budget-add-activity.webp), [first run](evidence/phone/sheet-first-run-and-add-sheet.webp) | [BV-11L](../../11-phone-ux/BV-11L-phone-slots-agree-with-each-other.md) |
| F4 | medium | **The Add sheet opened from Home does not start on the amount** (focus on `kind`). r27 J1 found it on 2026-11-08; it still reproduces on this commit. | `phone_capture.py` prints `add focus: kind`; [sheet](evidence/phone/sheet-first-run-and-add-sheet.webp) | IV-3AY7 (open), r27 J1 |
| F5 | medium | **No single page frame on the PC.** 13 of 24 tabs have no answer sentence. The title is the section on six tabs (Recurring, Loans, Reserves, Categories, Counterparties, Data checks) and the tab on eleven (Planner, Investment prices, Currencies, Compare periods, Reports, Rules, Import statements, Accounts, Held for others, Zakat, Financial health). Undo sits in the header on Overview, Budget and Cash planning, and on a second row on Spending, Investments, Transactions and Settings. The period bar is in the header (Overview, Budget), on a second row (Spending, Investments, Limits) or its own design (Currencies). Spending opens on last month; the others on this month. | [headers](evidence/pc/headers.json), [Overview](evidence/pc/overview.webp), [Spending](evidence/pc/birdview_expenses.webp), [Investments](evidence/pc/investments.webp), [Currencies and others](evidence/pc/sheet-planner-prices-currencies-zakat.webp) | [IV-12Y](../IV-12Y-one-page-skeleton-on-the-pc.md) |
| F6 | medium | **Pages longer than their answer.** Spending 4.1 screens, Cash planning 4.0, Investments 3.4, Transactions 3.3 (a register, fine). Investments shows "What changed" as five rows of 0 EGP and a card that says "Nothing moved in this period."; A09.2 asks for one line or nothing. Overview ends with two collapsed headings and a third of a screen empty. | [metrics](evidence/pc/metrics.json), [Spending](evidence/pc/birdview_expenses.webp), [Cash planning](evidence/pc/plan.webp), [Investments](evidence/pc/investments.webp) | [IV-12Z](../IV-12Z-answer-on-one-screen-on-the-pc.md), IV-3AM3 |
| F7 | low | **Cash planning repeats itself.** Needs you lists Landlord, Car loan and Vodafone as late with Mark paid; "The next 30 days", directly under it, lists the same rows with Mark paid again. "Can I afford this?" is a white card inside the Lead card (A16: card in a card). Zakat day is a loose underlined row between cards. | [Cash planning](evidence/pc/plan.webp) | [IV-12Z](../IV-12Z-answer-on-one-screen-on-the-pc.md) |
| F8 | low | **Actions in the wrong home.** Transactions' filled button is "Choose an account"; the page's main job (add or import) is not the primary. Ask an AI is a form of its own inside Settings › Your data, with a period bar, and appears again as a loose paragraph with two buttons on Budget. | [Transactions](evidence/pc/transactions.webp), [Settings](evidence/pc/settings.webp), [Budget](evidence/pc/budget.webp) | [IV-12Y](../IV-12Y-one-page-skeleton-on-the-pc.md) |
| F9 | medium | **Needs you counts three ways on Overview:** the heading says 17, the one row says "Bills and payments · 7", the link says "Show all 4". A person cannot tell how many things wait. Expected: one count, of the rows they will see. | [Overview](evidence/pc/overview.webp) | [IV-12AA](../IV-12AA-suggestions-with-sensible-defaults.md) |
| F10 | medium | **Refill's main button takes Safe to spend to nothing.** Reserves offers "Refill 117,786 · After this, Safe to spend is 897" on the PC and "Refill 51,420 · After this, Safe to spend is 0" on the phone, as the filled button, ahead of the instalments. BT-2AH made the amount safe for the plan; as a default it still empties the figure the phone's Home leads with. The page also says "The aim is six" where Limits says "Below 3 months". | [Reserves](evidence/pc/plan_reserves.webp), [phone](evidence/phone/sheet-plan-budget-health-reserves.webp) | [IV-12AA](../IV-12AA-suggestions-with-sensible-defaults.md) |
| F11 | low | **A comparison with nothing reads as an alarm.** Reports: "This year against last year · +315,749 against 0 before" in rose. With no data before, say so and leave the colour out. This month and This quarter show the same 3,410 in October. | [Reports](evidence/pc/sheet-compare-reports-import-add.webp) | [IV-12AA](../IV-12AA-suggestions-with-sensible-defaults.md) |
| F12 | medium | **Six names for "how is this worked out".** "Show the numbers", "How it is worked out", "See details", "See them", "Opens Cash planning" and a bare chevron all open a figure's working, some in place and some on another page. Expected (owner: explain every figure in place): one gesture, one label, the working in place, then one link to the figure's home. | [Overview](evidence/pc/overview.webp), [Limits](evidence/pc/financial-health.webp) | [NF-12AB](../NF-12AB-every-figure-explains-itself-in-place.md) |
| F13 | medium | **PC search finds names, not answers.** Typing "food" returns the category and a link "Find transactions with food"; the phone lists the payments at once. Neither says how much. Expected (owner: answers a typed question): "food last month" gives the figure, its comparison and the rows. | [Search](evidence/pc/sheet-review-payday-account-search.webp), [phone texts](evidence/phone/texts.json) | [NF-7AQ](../../7-planning-import-and-search/NF-7AQ-search-answers-a-typed-question.md) |
| F14 | low | **Words still off the brand voice**, beyond IV-3BH's list: "Completed payment occurrences" (Reserves), "Unreconciled events" and "Money at risk" (Weekly review), "Cash ownership history" (Held for others), "Funded spending left 0 · Unfunded bills due" (payday), "Other Investments" beside "Other" in one legend (Investments), "Age of Money" in title case (Reports). | [Reserves](evidence/pc/plan_reserves.webp), [review and payday](evidence/pc/sheet-review-payday-account-search.webp) | IV-3BH (words added to its report) |

## Smart features: what to build, in the owner's four kinds

Each is a suggestion the person confirms; none moves money by itself. Most extend what exists (NF-3AZ built the first ten).

| Kind | Proposal | Item |
| --- | --- | --- |
| Notices and proposes | Refill suggests the plan's monthly top-up first and says what Home will show after; the full amount is the second choice. Needs you gives one count. A comparison with no history says so. | IV-12AA |
| Does repeated work | Late bills on the PC: one "Catch up" that walks the late rows (paid, on which day, or not yet), as the phone's catch-up does (C11), not six separate Mark paid buttons. | IV-12AA |
| Explains in place | Click or tap any headline figure: its working opens in place, with one link to its home page. One label everywhere. | NF-12AB |
| Answers a typed question | Search understands a category or payee with a period ("food last month", "Carrefour 2026") and answers with the figure, its comparison and the rows. Offline, no AI service. | NF-7AQ |

## Recommended order (phone first)

1. **Phone, before Google Play:** BT-11K (F1), BV-11L (F2, F3), then the open IV-3AY7 focus (F4), IV-11A and IV-3AY11.
2. **PC frame:** IV-12Y (one skeleton and its test), then IV-12Z (one screen).
3. **Smart:** IV-12AA (defaults and counts, small), NF-12AB (explain in place), NF-7AQ (search answers).

## What works and should be kept

Cash planning's Lead (Safe to spend with its working row by row), Budget's pace chart, Accounts' "How it adds up", the phone's Home (one figure, To do with one verb each), the phone Budget's Needs attention, and the Activity day list. Nothing scrolled sideways at 360 or 320 px, and no PC page logged a script error.

## Validation and limits

- `python tools/phone_check.py --shots OUT`: "Nothing scrolls sideways or clips past the viewport at 360 or 320."
- `evidence/pc_capture.py`: 32 PC pages, all HTTP 200, no console errors, no sideways scroll ([metrics](evidence/pc/metrics.json)). `evidence/pc_headers.py`: the titles and sentences in F5 ([headers](evidence/pc/headers.json)). `evidence/phone_capture.py`: the first run, the phone texts and the Add focus.
- Browser evidence only (Chromium, automation). Not checked: a physical phone or its keyboard, the Windows WebView, paid themes, dark surfaces, the edit journal, forms' error states, speed. The full test suite was not run: no app code changed.
- The sample year is pinned to 2026-10-21 with prices offline, so Investments' zero change this month is the data, not a fault; the finding is how nothing is shown. Late bills on that date are the sample's.
- Home's "About 249 a day" under Safe to spend is the owner's decision of 2026-11-09 (one daily allowance, BV-12A) and is not a finding.
- Phone screenshots taken at once catch charts mid-draw; the Money chart was re-captured after it settled.

## Dated follow-ups

