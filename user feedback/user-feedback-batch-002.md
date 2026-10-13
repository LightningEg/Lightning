# Lightning User Feedback — Batch 002

- **Source:** Google Drive → `Lightning Data` → `App Feedback`
- **Feedback dates:** 3–9 October 2026
- **Processed:** 13 October 2026
- **Builds represented:** 0.4.0-beta.1, 0.5.0-beta.1, 1.0.0-beta.1-android
- **Coverage:** 42 genuine submissions; excludes two test rows and one diagnostic row
- **Traceability:** Source worksheet row numbers are used below because the Ticket # field repeats across sessions/builds.
- **Privacy:** Submitter names, email addresses, session IDs, and attachment URLs are omitted.
- **Interpretation:** Polished summaries preserve user intent; they are not requirements or product decisions. Investigate current behavior before proposing a fix.

## Executive summary

Feedback clusters around cash planning semantics, investment accuracy and discoverability, Overview/report clarity, and stateful workflows that feel slow or lose context. The most consequential reported defects are incorrect XIRR behavior, missing/incorrect investment analysis, stale cash cards after saving, confusing or unusable form controls, clipped mobile/help UI, and navigation or save actions that reset context. Feature requests include date-aware cash forecasts, user-defined goals, automated investment price data, bulk edits, and richer charts.

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

- **Row 32 — transfer fees:** Allow a transaction to be split into the investment transfer amount and a separate fee. Example: EGP 1,000 invested with 1% fees appears as EGP 1,001 leaving the bank, which obscures the actual investment amount.
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
