# Audit 7 — app visual flow

2026-10-25 · Codex · Owner-requested PC/phone visual recovery and implementation.

## Scope and brand

Read the real FastAPI/Jinja app, section registry, PC/phone guidelines, brand voice and glossary before restoring the work. This is presentation work, not a new financial engine or a replacement app. Keep the actual Lightning mark, bundled typefaces, theme tokens, financial colour meanings and distinct PC/phone layouts. Do not change the five bottom slots or the independently planned amount-first quick-add work (3AD).

## Page-by-page disposition

| Page | Logic and visual treatment | Result |
|---|---|---|
| Shared phone frame | Page-title disclosure exposes icon-and-word destinations matching PC sections, plus Transactions, Financial health, Weekly review and Profile and lock. Two columns, 48px rows, scrollable on short screens, RTL logical positioning. | Implemented; Investments opens directly. |
| Overview | Keep answer, Needs you and KPIs ahead of optional setup. Put secondary position and period breakdowns behind native disclosures; preserve their figures and links. Phone still gives Latest a convenient position. | Implemented on PC/phone. |
| Budget | Explicit category-specific monthly-limit names and translated save states; compact phone limit field aligned beside its category without pushing amounts off screen. | Implemented on PC/phone. |
| Transactions and account register | Add accessible names to date, counterparty, category, notes, held-for, amount, account and save actions. Keep existing signed values, arrow chips, selection, edit and Undo behaviour. | Labels implemented; existing financial flow preserved. |
| Cash planning | Preserve safe-to-spend lead and the due/payment/forecast contract rather than duplicating amounts in a new summary. | Reviewed; no calculation or schedule change. |
| Recurring items | Remove the second competing inline amount-edit form; keep the existing explicit offer, last-paid context and translated “Use … from now on” action. | Implemented; rent-rise regression passes. |
| Loans | Preserve repayment timing, still-to-pay and loan actions. Shared phone sizing improves row readability. | Reviewed; no debt-rule change. |
| Reserves | Preserve emergency target, funded state and its explicit actions; do not invent a second financial-health target. | Reviewed; no reserve-rule change. |
| Investments | Localize phone grouping/chart names; preserve holdings and all regrouping/lens calculations. | Implemented labels; views covered by tests. |
| Investment planner | One page heading; remove repeating legend; whole EGP in prominent proposal amounts. | Implemented; allocation logic unchanged. |
| Investment prices | Waiting checkpoint tasks first, then update sources, then dated manual prices. Shared files/import stay in a disclosure. Pending fields identify asset and date. | Implemented; endpoints/session inputs preserved. |
| Accounts | Preserve account-type grouping, account totals and money actions; shared PC holding links remain identifiable without theme-specific colours. | Reviewed; shared styling only. |
| Held for others | Keep the held total visible even at zero instead of hiding the purpose of the page. | Implemented; ownership calculations unchanged. |
| Financial health/settings | Name minimum versus maximum and below versus above alerts accurately, including Arabic. No changes to saved thresholds or bands. | Implemented labels only. |
| Weekly review | Decisions before history, explanations and optional activity/reminder content; each group has its heading. | Implemented on PC/phone. |
| Settings | Remains configuration, not the only entry into Investments or Accounts. Keep theme/data/export controls. | Reviewed; page picker supplies direct access. |
| Spending, categories, checks, activity | Preserve each page's existing purpose and controls; include in PC/phone EN/AR route and overflow checks. | Reviewed; no unrelated rewrite. |

## Steps taken

1. Recreated the lost upstream checkout and compared recovery edits against an untouched source snapshot.
2. Read app navigation, templates and brand requirements; separated convenience-focused phone work from full PC workspace presentation.
3. Added a small token-only `visual-flow.css` adapter in both real frames; no framework migration, new colours or external assets.
4. Restored page hierarchy, direct navigation, disclosure and form-label changes listed above.
5. Added a phone navigation regression; preserved the stronger existing planning assertion instead of weakening it after the changed rent offer was caught.
6. Rendered 20 routes × EN/AR × PC 1440px/phone 390px/small phone 320px: 120 responses, all 200, no document horizontal overflow or page errors. Opened the phone menu and followed Investments in both languages. Visually reviewed the PC/phone contact sheets and menu.
7. Corrected the inherited `*-grid !important` rule that otherwise collapsed the phone picker to one column; checked the computed two-column layout in the real browser.
8. Ran the focused regression suite, Mohab's year and module import contracts. Full suite: 2,479 passed, 41 skipped, 8 subtests passed, 2 failures. The newly introduced issue metadata failure was corrected and its test rerun successfully; the packaging fixture requires sandbox-blocked Git writes and remains an environment acceptance gap.
9. Documented the architecture adapter and owner acceptance item 3AH; regenerated the issue index and prepared the independent visual-flow PR, separate from theme PR #136.

## Evidence

Representative real-app captures are in [audit-7/](audit-7/): PC/phone Overview, Budget, Investments and Weekly review in English/Arabic, plus page picker. Captures use disposable sample data, never private profiles.

Focused tests: phone frame/budget/investments, planning, Mohab, review decisions/inbox, investment views, health limits, Arabic labels/numbers, data pickers and app guards all passed. Import contracts: 4 kept, 0 broken.

## Remaining acceptance gaps

- Physical Windows/WebView2 and Android checks, screen-reader testing and broad all-theme contrast acceptance were not performed here.
- Browser captures use sample data; the user's private profile was not opened. Functional data workflows are covered by automated tests, not claimed as private-profile browser acceptance.
- Existing 3AD quick-add work, financial formulas, account ownership rules and native sync are deliberately untouched.
- The website's app screenshots need recapture after approval/merge, not replacement with mockups.
- Full-suite packaging test `test_the_docs_only_skip_compares_with_the_last_successful_windows_build` remains unverified in this tarball/no-Git sandbox; its fixture attempts Git staging. No packaging source or assertion was weakened. Final affected/doc/issue/Mohab rerun passed with one existing skip.

Owner review is tracked in [3AH](../issues/3-polish-and-arabic/3AH-visual-flow-acceptance.md).