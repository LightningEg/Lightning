# User journeys and visual unity: answering the question and finishing the job

Date: 2026-11-08 · Author/reviewer: Codex
Repository: app · Reviewed commit: b83aa21
Code: r27 · App version: 2.1.0

## Assessment

Lightning's strongest interaction is the short phone task: search for a payment, paste a bank message, or classify a row and continue. The weakest part is continuity between a financial answer and its next action. Users must still translate between screens' financial scopes, navigation labels and presentation styles. More features will help less than making existing features feel connected.

Priority: fix the reproduced Add focus failure; reconcile the explanations around spendable cash and forecasts; give phone questions direct destinations; then standardize the presentation of secondary workflows. Preserve the compact transaction sheets and progressive disclosure already working.

## Scope and method

Reviewed latest fetched main, using disposable encrypted profiles and sample household data, date fixed to 2026-11-08. Ran 30 desktop page visits at 1366 × 768 and 31 phone page visits at 360 × 800, plus Add; inspected screenshots and extracted headings, controls and positions. Executed phone capture, bill-sheet opening, payment search, SMS parsing, sorting and category disclosure. Checked narrow layouts at 320 px in the flow probe. Read r14's main questions, its dated correction, current issue index and r26 to avoid reporting existing capabilities as missing.

This is an expert walkthrough using browser automation, not interviews or a representative user study. Page visits establish availability, not completion of every workflow. No production money was used. Desktop bulk actions, fresh onboarding, Arabic, paid themes, physical Android keyboard, Windows WebView, offline sync and native file handling are not certified by this run. No app implementation was changed.

Evidence: [desktop metrics](evidence/desktop/metrics.json), [phone metrics](evidence/mobile/metrics.json), [interaction log](evidence/flows/flows.json). Reproduce page capture with `python issues/12-desktop-ux/r27-journeys-and-visual-unity/evidence/capture.py`; interaction script is adjacent `flows.py` and takes an output directory. Requires Chromium, Playwright and app dependencies. Screenshots and numbers are sample-data observations, not financial advice.

## Journey findings

| ID | Priority and status | User question, observation and better outcome | Follow-up |
| --- | --- | --- | --- |
| J1 | P1, reproduced failure | **I just paid: can I record it immediately?** Add opens with activeElement `kind`. Typing 120 does not fill Amount; choosing a category and saving triggers required-field validation. The Amount input declares autofocus, but actual focus disagrees. Preserve an amount-first path and verify the saved amount rather than counting button presses as success. [Failed Save](evidence/flows/t1-3-saved.png). | New finding recorded in this report |
| J2 | P1, observed friction | **Can I spend this money?** Phone Home leads with Safe to spend 51,420. Cash planning opens with Due before payday 1,480; its Safe to spend explanation is below the first viewport. The link changes the question before answering the follow-up. Link the Home figure directly to its explanation; keep upcoming bills independently accessible. [Home](evidence/mobile/00-overview.png), [Plan](evidence/mobile/08-plan.png). | [IV-3AY](../../11-phone-ux/IV-3AY-phone-first-architecture.md) |
| J3 | P1, reproduced presentation problem; existing issue | **Can I afford a purchase?** Cash planning's lowest point is 51,420, while Scenarios defaults to lowest scheduled cash 86,288.36; the comparison shows literal “None” for first shortfall. Different models may be valid, but the visible distinction is insufficient for a purchase decision. Explain included commitments beside the answer, say “No shortfall,” and carry account/date/amount into the result. Do not equate these two values without reconciling their definitions. [Scenarios](evidence/desktop/12-plan-scenarios.png). | [BV-12D](https://github.com/LightningEg/Lightning/blob/b83aa2109c92b36fa268879c33bf19fb5e692aa2/issues/12-desktop-ux/BV-12D-neighbouring-figures-that-disagree.md), [NF-3AZ](https://github.com/LightningEg/Lightning/blob/e3f9449b5c369aef8c0858e319a44adfa842c3d3/issues/12-desktop-ux/NF-3AZ-next-step-at-the-moment-of-need.md) |
| J4 | P1, observed ambiguity | **Salary arrived: what should I do next?** Phone payday preview proposes Bills protected 0, Everyday spending 6,948, Emergency and goals 60,420 and Left unassigned 0, while below it Due before payday is 1,480. Bills may be included in everyday funding, but users should not have to infer that. Explain the inclusion and distinguish an allocation from a bank transfer. Keep one preview, explicit confirmation and an understandable after-state. [Payday](evidence/mobile/13-payday.png). This is an explanation finding, not proof of overspending. | [NF-3AZ](https://github.com/LightningEg/Lightning/blob/e3f9449b5c369aef8c0858e319a44adfa842c3d3/issues/12-desktop-ux/NF-3AZ-next-step-at-the-moment-of-need.md) |
| J5 | P2, existing issue reconfirmed | **Am I on plan?** Budget leads with 1,586 over plan's pace while everyday spending is 59 below the previous month's same point. Phone Health is ahead of pace; rent and loan payments correctly say Paid for this month. Explain linear plan pace versus usual behavior; distinguish fixed, variable and mixed categories. Do not turn every early-month payment into an alarm. | [BV-12B](https://github.com/LightningEg/Lightning/blob/b83aa2109c92b36fa268879c33bf19fb5e692aa2/issues/12-desktop-ux/BV-12B-budget-pace-follows-the-usual-month.md), [IV-3AY](../../11-phone-ux/IV-3AY-phone-first-architecture.md) |
| J6 | P2, observed friction | **Why did my wealth change?** Overview gives +36,745 net-worth change, +28,183 net flow and +7,896 investment result in separate places. Investments also shows period net gain, lifetime total gain and unrealized gain. These scopes can legitimately differ; users need a clearly dated bridge rather than mental subtraction. Make the change figure open its existing explanation and label period versus lifetime consistently. | [NF-3AZ](https://github.com/LightningEg/Lightning/blob/e3f9449b5c369aef8c0858e319a44adfa842c3d3/issues/12-desktop-ux/NF-3AZ-next-step-at-the-moment-of-need.md), [IV-3H](../IV-3H-tab-by-tab-review.md) |
| J7 | P2, observed friction | **What needs me now?** Home's five items, weekly review's four decisions and Health's one alert count different sets. Their scopes are not obvious from counts alone. Group by user job and consequence; show why a task is included, the next action and what resolves it. Keep acknowledge separate from resolve. Weekly review already makes that last distinction explicitly. | [NF-3AZ](https://github.com/LightningEg/Lightning/blob/e3f9449b5c369aef8c0858e319a44adfa842c3d3/issues/12-desktop-ux/NF-3AZ-next-step-at-the-moment-of-need.md) |
| J8 | P2, proposal based on inspected entry screens | **Where did my money go, and can I fix it in bulk?** PC Reports tells the user to save a Transactions filter first; import starts from an account-specific page and describes file columns before the task. Link analysis → matching transactions → selection → preview → outcome, preserving dates and filters. A desktop workspace should show selection scope and recovery next to the bulk action. Bulk mutation correctness was not exercised in this run. | [IV-3AM](../IV-3AM-pc-declutter-tab-by-tab.md), [NF-7AB](../../7-planning-import-and-search/NF-7AB-import-review-as-questions.md) |

## Visual unity

The shared palette, soft input wells, rounded surfaces and typography are recognizable across the inspected screens. Neither desktop nor phone page capture detected horizontal overflow. Unity breaks primarily in hierarchy and interaction, rather than in branding.

- **One question, one lead answer.** Home's Safe to spend is a bare hero, Cash planning nests it inside a later white card, and Scenarios uses a comparison table with cents. These are related decisions but the reading order changes. Standardize answer → scope/date → explanation → action. Keep phone bills as a separate quick task rather than making every Plan visit a long dashboard. Follow-ups: IV-3AY, IV-3AM.
- **One navigation vocabulary per device.** The inspected phone still uses Overview / Budget / Add / Transactions / More. Search results retain the Overview heading; Payday activates Budget in the bottom bar. Those details weaken location awareness. The new phone architecture is in progress: assess the shipped routes rather than treating its planned slot names as already delivered. Follow-up: IV-3AY.
- **One treatment for secondary jobs.** Phone Payday combines a summary card, a customization disclosure, an enabling button, another bill card and an available-cash card. Compare scenarios leads with form controls and a table. Give each phone job a short introduction, relevant inputs, a clear result and a return path; use PC width for aligned comparisons rather than simply widening the phone stack. Follow-ups: IV-3AY, IV-3AM.
- **Consistent financial precision and meaning.** Hero totals use whole EGP, while Scenarios uses cents and bill sheets show 350.00. Exact precision belongs in editable or transaction-level fields; decision summaries should follow the guideline. Preserve positive/negative semantic colors, and make “No limit” distinct from “Good.” Health's introductory “everything else within your limits” overstates the result when some metrics have no limit. Follow-up: BV-12D.
- **Unify disclosures, not everything into cards.** The phone's category sheet, row sheet and automatically advancing sorting flow suit quick work. Keep these patterns. Avoid adding another summary card when a labelled row and a drill-down answer the question. Follow-up: IV-3AY.

## Features that should connect

These are proposals under existing NF-3AZ, not claims that their underlying features are absent:

1. Salary receipt → reviewed payday allocation → forecast after allocation → confirm. Explain the destination account and any transfer still needed.
2. Spending warning → exact contributing transactions → classify or adjust plan → updated warning. Preserve period and category through every step.
3. Bill due → match existing payment or record → confirmation with recovery → reduced due count. The inspected bill sheet already offers matching, recording and skipping; finish and test the full loop.
4. Unmatched certificate interest → suggested bank receipt → reviewed match → investment income explanation. Avoid asking the user to navigate independently between the same two records.
5. Repeated categorization → optional rule preview → affected rows → explicit apply. Never silently generalize a single correction.
6. Emergency shortfall → affordable replenishment preview → scheduled allocation → visible forecast effect. A one-time Refill action alone does not explain the ongoing plan.

## What is working, and what remains unproved

Search returned Carrefour payments before names and categories. Pasting the synthetic bank SMS filled 5,000, merchant, date, account and outgoing direction; the flow stopped before saving that SMS. Sorting a seeded row advanced to the next row. Opening the next bill exposed matching, recording and skipping in one sheet; this run did not submit the bill. All 61 sampled page visits returned HTTP 200 with zero measured horizontal overflow. This does not establish absence of all JavaScript errors or accessibility defects.

The initial capture script's three-button quick-add sequence is a failed journey, not a successful three-tap completion: the screenshots and amount field prove it. Do not reuse the script's tap count as success evidence. Phone virtual keyboard behavior needs physical-device verification.

r14 remains the question inventory, not an up-to-date missing-feature list. Purchase scenarios, funded payday allocation and investment explanations exist. The opportunities here are discoverability, truthful scope, consistent presentation and completion. Fresh onboarding (IV-11A), lending/splitting (NF-12G), native recovery and offline work retain their existing items; this audit adds no fresh verification of them.

## Recommended order and acceptance

1. **Capture reliability:** Add → enter amount → category → Save produces exactly one correct transaction; focus and recovery work on reopening and on native phone.
2. **Decision clarity:** a user can explain why Safe to spend, everyday allowance and scheduled cash differ, and see the effect of a purchase or payday allocation without visiting unrelated pages.
3. **Phone continuity:** every headline's drill-down answers the same question in the first screen; navigation highlights the actual destination; return preserves context.
4. **Desktop analysis:** category/date/selection survive analysis-to-register-to-action; bulk preview identifies affected and excluded rows; outcome offers the appropriate recovery.
5. **Unity regression:** repeat English/Arabic, narrow phone, PC, light/dark and representative paid themes with the same journeys. This matrix is proposed acceptance, not completed testing.

Recovery verification: explicitly filling Amount with 120 saved `OUT-2026-11-08-001`, reduced Food & Groceries remaining to 1,295.25 EGP and exposed Undo. See [recovery interaction log](evidence/recovery/flows.json). This establishes a working recovery, not correct initial focus.
