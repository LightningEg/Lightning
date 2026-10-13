# Lightning User Feedback — Batch 002

- **Source:** Google Drive → `Lightning Data` → `App Feedback`
- **Feedback dates:** 3–9 October 2026
- **Processed:** 13 October 2026
- **Builds represented:** 0.4.0-beta.1, 0.5.0-beta.1, 1.0.0-beta.1-android
- **Coverage:** 42 genuine submissions; excludes two test rows and one diagnostic row
- **Traceability:** Source worksheet row numbers are used below because the Ticket # field repeats across sessions/builds.
- **Privacy:** Submitter names, email addresses, session IDs, and attachment URLs are omitted.
- **Interpretation:** The grouped feedback records historical submissions. Current outcomes are in the audit below; reviewed batch markers do not mean every requested feature is implemented.

## Executive summary

Feedback clusters around cash planning semantics, investment accuracy and discoverability, Overview/report clarity, and stateful workflows that feel slow or lose context. The most consequential reported defects are incorrect XIRR visibility, incomplete allocation handling, stale cash cards after saving, confusing or unusable form controls, clipped mobile/help UI, and navigation or save actions that reset context. Feature requests include date-aware cash forecasts, user-defined goals, automated investment price data and richer charts.

## Investigation instructions for an AI

For each item, inspect the current implementation and tests before changing code. Trace the UI action to its underlying service/data model; reproduce the behavior with focused test data; identify whether the issue is limited to the reported build/device; and report findings with file paths, relevant functions, and a minimal reproduction. Keep accounting semantics intact: plans should not create ledger transactions, investment capital movements should not become income/expense, and forecasts should respect dates. Do not treat a visual preference as a defect unless it conflicts with the app’s guideline or blocks use. For external price data, inspect licensing, reliability, caching, staleness, and offline behavior before recommending a provider.

## Grouped feedback and investigation targets

### 1. Cash planning, reserves, goals, and forecasts

**Source rows:** 34–35, 39, 41–42, 65–67

Users want cash planning to show when money will actually be available, let them configure targets, and keep its controls concise and responsive.

- **Rows 34–35 — planned-item mapping and date-aware forecast:** Show only the selected mapping field (account by default; category or counterparty when chosen). Forecast end-of-month cash from free cash, recurring income, expected project income, remaining budget spending, recurring payments, and project costs. Also flag a shortfall before a later salary date (example: salary arrives on the 24th). Funded costs reduce free cash; expected flows affect forecast cash.
  - **Investigate:** Current forecast formula and date handling; whether due dates are honored; treatment of funded versus expected items; whether mapping fields are unnecessarily duplicated.
- **Row 39 — reserve account selector:** Account options are not visible until the query text is cleared, and not all options can be seen.
  - **Investigate:** Searchable select filtering, menu clipping/scrolling, keyboard behavior, and empty-query handling.
- **Rows 41–42 — income support and form density:** Include income categories in cash planning, use an action label appropriate for income rather than “I paid it,” and reduce explanatory field labels/space where the controls are already self-evident.
  - **Investigate:** Income/outflow type handling and whether labels/actions derive from the planned item’s direction.
- **Row 65 — user-defined goal:** Allow a fixed goal or a multiple of average income; show progress and forecast when the goal will be reached.
  - **Investigate:** Existing six-month target assumptions, goal persistence, and forecast projection inputs.
- **Rows 66–67 — controls and saved state:** Fields appear grey; pressing Enter to save a reserve does not refresh free-cash cards until leaving and re-entering the tab.
  - **Investigate:** Disabled/read-only styling versus actual editability; submit event parity between Enter and button; state invalidation after mutations.

### 2. Investments: calculations, allocation, holdings, and market data

**Source rows:** 46–48, 58–63

Users want investment analysis to be dependable, understandable, and easier to configure.

- **Rows 46, 48 — target allocation:** Explain when no allocation exists or targets total 0; if targets sum below 100%, normalize for calculation while warning the user; do not silently accept totals above 100%. The settings action currently navigates to an unexpected page.
  - **Investigate:** Allocation validation and planner math, zero/partial/over-100% cases, and route targets for settings links.
- **Row 58 — XIRR help:** The information tooltip is clipped.
  - **Investigate:** Tooltip anchoring, viewport collision handling, and mobile/desktop behavior.
- **Row 61 — XIRR calculation:** User reports that XIRR incorrectly requires a full year, despite irregular cash flows being the use case.
  - **Investigate:** Cash-flow signs/dates, solver bounds and convergence, short holding periods, and comparison with known reference cases. Verify the annualization convention and explain insufficient-data cases without imposing a full-year rule.
- **Rows 59–60 — holdings display:** Remove repeated holding detail/account text and abbreviate short-, medium-, and long-term labels to L/M/S with distinct accessible colors.
  - **Investigate:** Whether details are duplicated across the holding hierarchy; preserve enough context for users to identify the account and instrument.
- **Rows 62–63 — automated price and return data:** Request to retrieve prices and volume for funds/stocks, add new instruments, configure update timing (on open/daily/month-end), backfill missed month-end values or ask the user, show sources and allowlist sites, and cache reusable findings. “Fall from highest” is unclear.
  - **Investigate:** Current provider integrations and data model first. Assess source terms, coverage, accuracy, timestamps, stale/offline handling, user consent, and shared-cache isolation. Clarify or replace the “fall from highest” metric with a defined financial measure before changing it.

### 3. Overview, charts, and navigation semantics

**Source rows:** 38, 45, 49–57, 64

Users want charts and cards to answer clear questions and behave predictably.

- **Row 38 — expense breakdown:** Prefer a pie chart over blocks because it is easier to track; positive feedback on seeing exact numbers should be retained.
- **Row 45 — KPI cards:** Center and enlarge KPI numbers and align the visual treatment with the chart guideline.
- **Rows 49–50 — help and trend context:** Help text is clipped at the screen edge; trend tooltips should show change from the prior point as well as date/value.
- **Rows 51–52 — free cash and investment hierarchy:** Free-cash card repeats information; consider a more useful secondary detail such as upcoming bills. “If sold today” should show parent total before holdings, with children expandable.
- **Row 53 — positive signal:** User strongly likes the Sankey visualization; preserve its strengths during related work.
- **Rows 54–55 — card behavior and investment section:** Card clicks inconsistently navigate to a tab or transactions; prefer a consistent route to underlying transactions. Investment area feels uninformative.
  - **Investigate:** Define expected click destinations by card type; check whether investment summary offers useful holdings, performance, or actions before treating this as a redesign request.
- **Row 56 — selection control:** Place “Select all” beside the track rather than on a separate empty row.
- **Row 64 — expense heat map:** Replace net-cash-flow heatmap values with expense/outflow volume.
  - **Investigate:** Metric definition, date aggregation, and whether the chart label/legend communicates outflows clearly.

### 4. Responsiveness, state preservation, and feedback submission

**Source rows:** 36, 40, 57, 76

Users report slow navigation, lost context after actions, and slow multi-image feedback submission.

- **Row 36 — navigation latency:** App navigation and taps feel slow.
- **Row 57 — context after action:** Saving or acting refreshes the page and sends the user to the top; retain the current view and position.
- **Row 40 — feedback attachments:** Add issue screenshots to improve debugging.
- **Row 76 — multi-image submission latency:** Five images take about ten seconds to send. User suggests starting image processing/upload shortly after selection and cleaning up abandoned uploads.
  - **Investigate:** Measure navigation/save/upload phases separately; inspect request timing, rendering work, and image handling. For early uploads, ensure abandoned files are cleaned up, temporary storage is access-controlled, and submission still references the correct images.

### 5. Account and transaction workflows

**Source rows:** 32, 37

- **Row 32 — transfer fees:** Allow a transaction to be split into the investment transfer amount and a separate fee. The original example mixes EGP 1,000, a 1% fee and an EGP 1,001 debit. These numbers conflict: 1% implies EGP 10 and an EGP 1,010 debit; an EGP 1 fee implies 0.1%. Confirm the actual fee before building a reproduction.
  - **Investigate:** Import reconciliation, transfer pairing, fee accounting, and whether the split preserves the bank statement total without overstating invested principal.
- **Row 37 — payment settlement accounts:** Settlement only offers the payroll account; user expects other configured accounts such as Vodafone Cash, cash, and savings.
  - **Investigate:** Account eligibility/filtering for settlement and whether all profile accounts should be available.

### 6. Interface clarity, setup, and visual defects

**Source rows:** 33, 43–44, 47, 71–75

- **Rows 33, 43 — password policy:** Remove the fixed 12-character limit and show optional strong-password guidance instead. (Two submissions.)
  - **Investigate:** Current validation and security policy; preserve secure hashing and avoid weakening other protections.
- **Row 44 — stale demo label:** A screen still says “Omar’s test” although the profile is now Mohab.
  - **Investigate:** Whether the label is seeded demo copy or stale profile-derived state; remove hard-coded personal test content.
- **Row 47 — small settings icon:** Increase the icon’s usable hit target/readability.
- **Row 71 — mobile date bar:** Android date bar differs from the other bar and is clipped.
- **Row 72 — setup guide:** Add a completion/done action so the guide does not appear every time.
- **Row 73 — review queue expiry:** Give “needs review” items an expiry (suggested two days) so stale items do not accumulate indefinitely.
  - **Investigate:** Whether expiry means hide, archive, or delete; preserve user data and explain the behavior.
- **Row 74 — alignment:** Move the disclosure arrow to the right of the item, away from the number, so numbers align.
- **Row 75 — mobile top bar:** Top bar appears too white compared with the expected visual design.
  - **Investigate:** Compare against the phone guideline and verify contrast/theme behavior before styling changes.

### 7. Low-information submissions excluded from investigation

- **Excluded rows 68–70:** rows 68 and 70 are marked “test”; row 69 is explicitly marked diagnostic with a request to delete it after checking. Exclude all three from product investigation. Preserve diagnostic evidence only under the project’s data-retention rules.

## Prioritization signals

1. **Correctness and data integrity:** XIRR (row 61), dated cash forecasts (rows 34–35), transfer fee/principal separation (row 32), and reserve state refresh (row 67).
2. **Workflow blockers:** unusable selectors (row 39), settlement account availability (row 37), sluggish navigation/context loss (rows 36, 57), and multi-image feedback latency (row 76).
3. **Clarity and trust:** target allocation validation (rows 46, 48), current versus forecast semantics (rows 34–35), goal projections (row 65), and “fall from highest” (row 63).
4. **Visual and interaction refinements:** Overview cards/charts, clipped controls, setup completion, and alignment (rows 38, 45, 49–56, 71–75).

These are investigation signals, not committed priorities. Confirm reproduction and implementation context before selecting work.

## Traceability and batch status

The 42 included submissions are source rows 32–67 and 71–76 in the `App Feedback` tab. Rows 68 and 70 are test entries; row 69 is a diagnostic entry. Rows are cited rather than Ticket # values because those ticket numbers repeat across sessions/builds. The corresponding blank batch markers have been assigned `002 · reviewed`. Three attachment URLs that had landed in the Batch # column were moved to a dedicated source-sheet column, preserving two excluded test/diagnostic attachments and one mobile date-bar attachment. No URLs or personal identifiers are copied into this report.


## Current-code audit — 13 October 2026

Baseline: app main `98873c7`. Each included source row appears once below. “Existing” means the current implementation addresses the reported behavior; “Request” means an enhancement or product choice remains, rather than a reproduced defect. This audit changes no ledger history or private profile data.

| Source row | Topic | Outcome and evidence |
| --- | --- | --- |
| 32 | Split transfer principal and fee | **Request.** `TransactionService.update_expense_split` supports ordinary expenses only. Transfer/fee splitting during import remains unbuilt; correct the inconsistent fee example first. |
| 33 | Password limits | **Existing.** `security.keys._password_bytes` accepts any nonempty password within a resource bound; profile UI suggests strong passwords without a 12-character minimum. |
| 34 | Show only selected reserve matching field | **Existing.** `templates/reserves.html` enables only the chosen account/category/counterparty field; Ask remains a deliberate default. |
| 35 | Forecast date-aware cash availability | **Partly existing.** `CashForecaster.forecast/_safe_to_spend` combine scheduled income, budget, reserves and dated payments before the next income. A daily balance path pinpointing the first shortfall date is still a request. |
| 36 | Slow navigation | **Existing mitigations.** Request-scoped report/query caches and local fonts are documented under Architecture › Page speed; `test_reporting_performance.py` enforces query ceilings. The original latency is not a new measured current-build defect. |
| 37 | Settlement account choices | **Existing.** `planning._paying_accounts` offers active bank, cash/mobile-wallet and brokerage accounts. Locked certificate portfolios are intentionally excluded. |
| 38 | Pie chart and positive numeric-label feedback | **Design request.** Current Spending uses a treemap with exact values; switching to a pie is a preference requiring a chart decision. Retain the positive numeric-label signal. |
| 39 | Reserve picker requires clearing text/options hidden | **Existing.** Own-data pickers use empty placeholders, select current text on focus, and allow search across saved options. Initial five suggestions follow guideline A10.7; typing reaches the other options. |
| 40 | Feedback screenshots | **Existing, website.** `Lightning_website/app-feedback.html` and `js/current-status.js` allow up to five images per ticket. |
| 41 | Income categories and payment wording | **Existing.** Planning handles INCOME, inflow and both-direction categories; income settlement wording differs from money out. See `test_planning.py` and the 12 October income-category fix. |
| 42 | Remove redundant field definitions | **Existing redesign.** Current reserve form uses concise field labels and one selected matching control. No disabled-control defect reproduced. |
| 43 | Password 12-character limit | **Duplicate of row 33; existing.** No current 12-character minimum. |
| 44 | Stale demo name | **Existing redesign.** No hard-coded “Omar’s test” label remains in app source. User-entered profile names are not rewritten. |
| 45 | KPI number hierarchy | **Existing redesign.** Current PC/phone cards follow the separate guideline layouts and larger tabular values. Universal centering is a visual preference. |
| 46 | Empty/partial/over-100% target allocation | **Fixed.** Helper explains missing targets even before the first holding, accepts a positive total below 100%, displays the normalized targets used for suggestions, warns and preserves saved targets. Zero/negative/over-100% targets produce no split. `suggest_contributions`, planner route/template and regression tests. |
| 47 | Small settings icon | **Obsolete screen layout.** Old investment header settings buttons were removed in the 7 October audit; current actions use the guideline’s button geometry. |
| 48 | Allocation navigation | **Existing.** Planner links to `/settings?section=targets`; target controls live in that settings section. |
| 49 | Settings help clipping | **Fixed.** `info-tips.js` places a shared body tooltip inside viewport bounds, with keyboard/touch handling. Browser checks cover a button at the lower-right edge. |
| 50 | Trend change from prior point | **Request.** Shared trend dots currently report date and value, with plan status where applicable. Previous-point amount/percentage change remains unbuilt. |
| 51 | Duplicate free-cash content | **Existing redesign.** Free cash now has its component breakdown and due-payment details; upcoming obligations have their own actions. |
| 52 | Parent before children in sale estimate | **Fixed.** PC and phone lead with Holdings after sale, then expandable class details. Phone class rows now use `after_sale` rather than gross `value`, so they reconcile with sale factors. Regression checks use a 50% factor. |
| 53 | Sankey praise | **Positive signal.** No corrective change required; preserve the visualization. |
| 54 | Uniform card click destination | **Design request.** Current cards lead to transactions, plans or valuation details according to their figure. Routing every card to transactions would misrepresent plan/valuation figures; a universal interaction contract needs a product choice. |
| 55 | Investment overview is uninformative | **Existing redesign.** Current Overview contains investment gain/loss and class detail linked to the investment report. The original broad preference supplies no reproducible defect. |
| 56 | Select-all placement | **Layout request.** Category selection is supported; moving its label beside tracking controls remains a visual refinement. |
| 57 | Page refresh loses position | **Existing, strengthened for reserves.** Normal posts/popup saves preserve scroll in `app.js`. Reserve autosaves now refresh only read-only summaries and retain focus, edits and expanded forms. Browser-tested. |
| 58 | XIRR help clipped | **Fixed with row 49.** Shared viewport tooltip also applies to holding/XIRR help. |
| 59 | Repeated holding detail/account text | **Existing redesign.** Current holdings table removes repeated detail lines; account appears only when multiple accounts need disambiguation. |
| 60 | L/M/S colored horizon tags | **Request.** Current table supports full horizon names and horizon filtering; compact abbreviated tags remain a visual enhancement. |
| 61 | XIRR full-year prerequisite | **Fixed.** Removed screen-only 365-day gates. Solver remains ACT/365 and supports shorter dated flows; same-day flows and offsetting daily totals stay unavailable even with a later report date. Portfolio and holding screens now show valid short-period results. |
| 62 | Automatic prices/volume and shared cache | **Partly existing; later decisions govern.** Live sources, typed-price precedence, month-end backfill and shared price files exist. The 5 October source/licensing and month-end policy supersedes unrestricted shared scraping. Daily timing preferences and full trading-volume analysis remain requests. |
| 63 | “Fall from highest” unclear | **Defined metric, preference remains.** Holding view now says “Fall from its high” and explicitly measures below the highest month-end price, with worst drawdown. Replacing that measure is a product choice, not evidence of an incorrect number. |
| 64 | Expense heatmap should show outflows | **Existing.** Spending’s primary calendar is Total expenses (`day_calendar(..., 'spend')`); net cash flow is a separate secondary view. |
| 65 | Configurable emergency goal/progress | **Later owner decision.** The 5 October plan contract uses a six-month emergency target, with selectable income/spending basis and shared top-up calculations. Project goals already allow fixed amounts, progress and reach-date estimates. An independently configurable emergency target would revise that contract. |
| 66 | Grey fields | **Guideline treatment.** Grey/soft field wells are intentional; editability comes from enabled controls, not white backgrounds. No current disabled-field failure established from the submission alone. |
| 67 | Enter-save leaves free-cash figures stale | **Fixed.** Reserve fetch saves return fresh rendered summaries and `reserve-autosave.js` applies them without replacing inputs. Serial saves keep later edits. Service/screen regression and functional browser checks. |
| 71 | Mobile date bar clipped | **Existing 12 October fix.** Phone period controls and RTL dates were corrected in `phone.css`/RTL styles. Native Android/device appearance remains a device acceptance check. |
| 72 | Setup guide cannot be completed/dismissed | **Fixed.** Done with setup persists a profile preference; Settings › Show setup guide reopens it. PC and phone use the same action; account/ledger data is untouched. |
| 73 | Review queue should expire after two days | **Needs product decision.** Unposted imports and uncategorized transactions remain actionable until resolved/discarded. Automatic expiry could conceal unfinished financial work. Define whether only stale suggestions may be dismissed; do not delete ledger/import data by timeout. |
| 74 | Disclosure arrows disturb number alignment | **Fixed.** Phone Overview arrows sit beside the item label; numeric values keep their own aligned column, including the sale-estimate parent. |
| 75 | Mobile top bar is too white | **Device/design check.** Current phone chrome follows Part C; the submission does not distinguish native Android status bar from web app bar. Verify on the reported device before changing the theme. |
| 76 | Five-image feedback submission slow | **External website request.** `current-status.js` prepares/compresses selected images before submit, two at a time, then submits attachments together. Background Drive staging, cancellation cleanup and a new upload protocol are not built. The reported ten seconds is not a current measured benchmark. |

### Remaining requests for the next investigation

Highest-impact remaining implementation work is transfer principal/fee splitting (row 32) and a dated balance path that identifies the first cash shortfall (row 35). Smaller requests are trend deltas, selection placement and horizon tags (rows 50, 56, 60). Chart type, universal card behavior, emergency-target policy and review expiry need product choices (rows 38, 54, 65, 73). Extra price schedules/volume analytics and pre-submission image staging are separate data/website work (rows 62, 76).

The original feedback came from older builds. Do not reopen items marked Fixed or Existing solely because their historical text remains above; reproduce a regression first. Review the remaining device concerns on an ordinary Windows PC/Android phone before declaring release acceptance.

### Validation

Regression coverage exercises short and irregular XIRR cash flows, invalid/partial allocation targets, unchanged stored weights, fresh reserve summaries, setup dismissal/reopening, and phone sale-factor reconciliation. A Chromium browser exercise checks reserve totals after Enter, preserved focus/scroll, rapid consecutive saves, an edge-positioned help tooltip, and setup dismissal/reopening with no JavaScript errors. Full regression run: **1,381 passed, 9 skipped**. Final investment/XIRR/performance/Mohab follow-up: **158 passed**; final empty/partial-allocation and XIRR edge checks: **7 passed**. All four import contracts pass. Phone browser geometry also passes at **320, 360 and 390 pixels in English and Arabic**, including period controls, label-side arrows and bounded help tips.

Integration check: after merging the concurrent v1.1 changes, 208 regression checks passed. The only failure was the upstream Overview contents table; the subsequent documentation cleanup was incorporated and documentation checks rerun before publication.
