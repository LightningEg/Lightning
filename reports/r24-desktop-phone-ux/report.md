# Lightning UX audit: desktop analysis and phone convenience

Code: r24 · Historical ID: desktop-phone-ux-2026-11-05

Date: 2026-11-05 · Author/reviewer: Codex
Repository: app · Reviewed commit: a7ff8d8b38e18410b5bf7e18f674f0ad85c2cb05
Version: 1.5.4 source, latest main at the start of this review; not a claim about the installed or published binaries.

## Assessment

Lightning has a strong financial model and a substantially improved daily phone experience. Its main UX weakness is now **consistency between answers and the actions taken from them**. Some screens compute related answers differently, some recommendations ignore constraints shown elsewhere, and secondary phone workflows still require reading and scrolling through desktop-sized tasks.

On desktop, the priority is an analysis workspace that carries the question, date range, selection and next action through the entire job. On phone, the priority is a small number of reliable decisions with an immediate action. These need different presentation, with the same financial definitions underneath.

Do not begin with a cosmetic redesign. Correct the five trust problems below, then improve the connections and simplify the secondary workflows. Preserve the existing phone capture, search and sorting interaction.

## Scope, evidence and limitations

- Read the product, journeys, current code, relevant brand guidance and the requested **[Users’ main questions](../r14-users-main-questions/report.md)**. That document is now in `reports/`, linked from `ai/PROJECT_OVERVIEW.md`; there is no user-question Markdown file under `docs/` at this commit.
- Ran the current app with disposable encrypted profiles and the built-in household. Primary captures use **2026-11-05**, desktop **1366 × 768**, phone **360 × 800**. Also checked desktop Overview at **1920 × 1080**, phone layouts at **320 px**, and Arabic phone layouts and core flows.
- Inspected the rendered core screens, then traced suspicious behavior into services and templates. Created separate car/loan probes and exercised the emergency refill through the browser.
- Evidence is categorized as **confirmed** (reproduced), **observed UX friction** (visible behavior with a design judgment), or **proposal** (a future improvement, not a defect).
- No production profile, native Windows application or physical Android device was used. Native keyboard occlusion, biometrics, notification delivery, pairing/offline conflict behavior, screen-reader usability and every paid theme are not certified by this review. Desktop Chromium and phone emulation are evidence about the shared UI, not native acceptance.
- No representative-user study or large-ledger performance benchmark was run. Suggested task targets below are acceptance proposals, not measured population outcomes.
- Screenshots and page metrics: [desktop](evidence/desktop/metrics.json), [phone](evidence/mobile/metrics.json), [focused flows](evidence/flows/flows.json), [financial reproductions](evidence/logic-probes.json). The guessed `/plan/payday` URL in the broad capture returned 404; the actual `/payday` route was subsequently checked. This is **not** filed as an application bug.

## Priority findings: logic and trust

### F1. Property/vehicle “Value now” uses the wrong source — confirmed, high

Open an Other asset with an opening value of 600,000 EGP, save a later dated value of 540,000, and set its purchase price to 600,000. The account header shows **540,000**, but the new details panel says **Value now 600,000**, **change 0**, and **equity 575,000** against a 25,000 loan. The correct change is **−60,000**, and value less remaining payments is **515,000**.

The same panel’s history already shows 540,000 and −60,000. This is a direct contradiction within one screen, on both devices. `_asset_view` reads `account_balance`, which is ledger cash quantity, rather than the dated valuation used for the account’s reported value. The existing test passes partly because it finds “−60,000” somewhere in the HTML—the history supplies it—even while the headline is wrong.

**Fix:** use a shared native-currency valuation result, with effective date, for header, change and linked-loan comparison. Do not merely replace the call with a base-currency figure and retain the account-currency label. Validate foreign-currency assets and base-currency loans explicitly. Test the actual headline and equity fields independently of the history.

Source: `lightning/ui/routes/register.py:465`, `lightning/ui/templates/partials/asset_details.html:7`, `tests/test_asset_details.py:48`.
Evidence: [desktop contradiction](evidence/details/pc-asset-600000.png). Fixed: **BT-2AF** (2026-11-06), `tests/test_asset_details.py::test_headline_change_and_equity_use_the_dated_value_not_cash`.

### F2. A zero-opening Other asset can disappear from reported wealth despite a saved estimate — confirmed, high

Create the same car with opening value zero, then enter a 540,000 valuation. The saved history contains the valuation, but its reported account value remains **zero**. The details panel additionally reports a **100% loss** and negative equity.

The reporting holdings loop skips a zero ledger quantity **before** checking for a manual Other asset valuation. The UI accepts a dated estimate, so this is not a clear unsupported workflow. Users can reasonably open an asset first and fill in its value afterward.

**Fix:** value eligible Other assets independently of a nonzero cash quantity. Preserve the distinction between a valuation and cash movement. Regress zero opening → nonzero estimate → revised estimate, both account and whole-wealth views, with no artificial cash transaction.

Source: `lightning/reporting/service.py:216–239`. Evidence: [phone zero-value car](evidence/details/phone-asset-0.png), [numeric probe](evidence/logic-probes.json). Fixed: **BT-2AG** (2026-11-06), `tests/test_asset_details.py::test_a_zero_opening_asset_counts_from_its_estimate_without_cash`.

### F3. “Refill” can recommend allocating money already needed by the plan — confirmed, high decision risk

In the untouched sample household:

| Figure | Before refill | After accepting the suggested refill |
|---|---:|---:|
| Emergency amount added | — | 67,368.36 EGP |
| Free cash | 67,368.36 | 0 |
| Safe to spend | 51,420.11 | **−15,948.25** |

The prompt uses `min(emergency gap, free cash)`. Free cash has not yet deducted all the future obligations, remaining budget and savings allowances used by Safe to spend. The prominent suggestion does not preview the resulting deficit. **No money actually leaves the bank**; this is a misleading allocation recommendation, not a cash transfer or data-loss finding.

**Fix:** preview the full forecast after the proposed allocation and recompute dependent savings allowances. Offer a recommended amount that protects upcoming commitments, and show “After this: … available until payday.” Allow an intentional larger allocation through an explicit choice. Do not assume subtracting today’s Safe to spend is sufficient: the allocation changes other forecast terms too.

Source: `lightning/ui/routes/reserves.py:65–70`, `lightning/ui/templates/reserves.html:43–44`. Evidence: [service before/after](evidence/logic-probes.json), [fresh-profile browser result](evidence/details/pc-refill-baseline.png), [browser text](evidence/details/refill-baseline.json). Fixed: **BT-2AH** (2026-11-06), `tests/test_refill_preview.py`.

### F4. “In your accounts” has two incompatible meanings — confirmed, medium

The phone’s More screen shows **275,671**, then Accounts shows **261,671**. Accounts also says it includes 10,000 held for others, “so you own **265,671**.” The ownership sentence is mathematically impossible against its displayed total.

The 14,000 difference is the sample’s remaining gam’eya obligation. More uses `what_you_own + held_for_others`, while Accounts sums account values, including the circle’s negative balance. The asset/liability model may be intentional; the labels and reconciliation are not adequate. The desktop Accounts explanation has the same unreconciled figures.

**Fix:** choose one canonical definition for each label, show the gam’eya liability separately where required, and reconcile displayed components. Do not change the wealth formula merely to force a subtotal to match. Check Accounts, sidebar, More and Overview together.

Source: `lightning/ui/routes/dashboard.py:520`, `lightning/ui/routes/accounts.py:110–140`, `lightning/planning/position.py:138`.
Evidence: [More](evidence/mobile/30-more.png), [Accounts](evidence/mobile/03-accounts.png), [reconciliation](evidence/logic-probes.json). Fixed: **BV-3AQ** (2026-11-05; In your accounts is what the rows add up to, owner decision), `tests/test_gameya_screens.py::test_accounts_sidebar_more_and_overview_agree_on_in_your_accounts`.

### F5. Phone pacing treats paid fixed commitments like discretionary spending — confirmed, medium

On November 5, the phone budget flags **Housing & Rent: 12,000 of 12,000**, **Loan payments: 2,500 of 2,500**, and the monthly gym expense as “Ahead of pace.” They rise above other categories even though early-month settlement is expected.

The phone’s category risk compares percentage used with percentage of the month elapsed, without using the fixed/variable distinction. The desktop’s main pace chart already distinguishes everyday spending. This undermines the phone’s “tell me what needs attention” job and makes rose warnings easier to ignore.

**Fix:** scheduled obligations should say “Paid for this month,” “Due,” or “Amount above expected.” Use time-based pace for appropriate variable spending; handle mixed categories at transaction/obligation level. Test rent paid on the 3rd, groceries spread through the month, and an actually excessive bill.

Source: `lightning/ui/routes/budget.py:466–502`. Evidence: [phone Budget](evidence/mobile/01-budget.png). Fixed: **BV-3AR** (2026-11-05), `tests/test_phone_budget.py::test_paid_bills_are_not_ahead_of_pace_variable_spending_is_and_an_excessive_bill_is_over`.

## Desktop: heavy analysis and bulk actions

### F6. The first screen still spends too much room explaining before exposing the work — observed friction

The desktop shell and ledger are substantially clearer than older audits suggest. Transactions exposes many rows immediately, and the sidebar gives useful cross-account context. However, at 1366 × 768 the Investments **Holdings** heading starts at **y=788**: the entire working list begins below the viewport. Cash planning’s **next 30 days** starts at **y=1103**. The large allocation/hero areas use room an analyst could use for comparison and selection.

**Recommendation:** preserve a compact answer and context, then place the working table or due list alongside the supporting visualization. On Investments, show value, period result and price coverage in a slim strip, with holdings visible immediately. On Cash planning, place the next obligations beside the bridge. At 1920 px use the width for comparable information, not larger cards alone.

Acceptance: at 1366 × 768, see the primary answer, relevant date, at least several working rows and the main action without scrolling. Follow-up: **IV-3AM, IV-3Q**.

### F7. Bulk tools are useful, but “Edit selected” overpromises — confirmed behavior, medium UX friction

Selection, shift-selection, selecting all matching rows, bulk categorization, export, merge and delete already exist. Do not rebuild them as missing features. But **Edit selected** opens the first eligible selected transaction; it is not a multi-field bulk editor. Find and replace is a separate route into text cleanup, while “Make a rule” uses the first selected counterparty.

**Recommendation:** distinguish **Edit one by one** from **Change category for N** and **Replace text in N**. Show scope, eligible count and excluded count before execution; preview old → new values for multi-field edits. Retain selection and filters afterward, report exactly what changed, and make the recovery path visible. Offer one consistent place to rename counterparties, categorize and make a rule from a reviewed selection.

Source: `lightning/ui/static/app.js:900–960,1050–1075`, `lightning/ui/templates/register.html:167–181`. Evidence: [selected ledger](evidence/details/pc-bulk-selection.png). Follow-up: **IV-3G** (bulk workflow and contextual actions).

### F8. Date and comparison context should survive a complete investigation — observed friction

The PC Spending page intentionally starts on the last completed month early in a month; the phone starts on current spending. That can suit the two jobs. The risk is not the different default itself, but users comparing two amounts without noticing the scope switch. In the sample PC Spending shows October’s 25,654 while phone Spending shows November-to-date 18,651.

The app supports period controls, saved views, comparisons and exports. Make those feel like one investigation: selecting a category, merchant or chart segment should open transactions with the same period and comparison context. Returning should restore scroll, selection and grouping. Clearly separate historical values, today’s balances and forward-looking projections when they coexist.

Acceptance: explain one category’s increase, inspect its rows, save the view and export the exact scope without re-entering filters. Follow-up: **IV-3G, IV-3AM**.

### F9. Analysis sometimes exposes tools before the answer — observed friction

On Spending, the AI prompt’s explanatory text and Copy/Edit buttons appear before the main category breakdown. On Counterparties, the AI alias handoff is prominent before the saved names. These are optional expert aids, but they consume the first screen needed to answer “where did it go?” or correct a merchant.

**Recommendation:** lead with native ranked results and actionable exceptions. Put external-AI handoff behind “Get another analysis” or an overflow action. Keep its explicit data scope and user-controlled copy behavior; do not introduce automatic uploading. Follow-up: **IV-3G, IV-3AM**.

## Phone: quick decisions and convenient actions

### What already works well

| Task | Current observed interaction | Qualification |
|---|---|---|
| Record a common expense | **3 taps**: Add → category → Save, plus amount entry | Existing account/category; native keyboard not tested |
| Search transactions | **1 tap** to Search, plus typing | Results appear live and payments come first |
| Paste a known bank SMS | Add → Paste SMS → review and Save | Two taps reach a populated form; saving is still required |
| Sort a transaction | **3 taps**: To sort → row → category | The next unsorted row opens automatically |
| Check grocery allowance from Budget | **1 tap** to its sheet | Sample row at y=589; route to Budget is additional |

The prominent Add button, remembered account, category chips, pinned Save, transaction sheets, visible currency and Arabic mirroring are strengths. Preserve them. “Three taps” is not a claim about total task duration or every first-use case.

### F10. Secondary phone screens still behave like lengthy reports/forms — observed friction

The first screen of Investments is almost entirely value and chart: **Holdings begins at y=753**, at the bottom navigation boundary. The page is **2473 px** tall. Financial health is **2358 px**; Settings is **3354 px**. Length alone is not a defect, but immediate jobs are displaced by explanations or broad overviews.

Cash planning also inserts Compare scenarios and Forecast inputs above Coming up. Scenarios opens with approximately a full screen of scope and unchanged comparison results: the first **Income delay** control begins at **y=858**. That is excessive setup for a quick “what if?” check.

**Recommendation:** keep current holdings, next due item or exception on the first screen. Charts and secondary ratios should open from rows. On scenarios, start with **Buy something / Income arrives late / Bill changes**, then show the result for the selected action. Keep assumptions accessible beside that result. Leave full model editing to an advanced view rather than removing it from the phone altogether.

Follow-up: **IV-3AN, IV-3T, IV-3Q**. Evidence: [Investments](evidence/mobile/14-investments.png), [Scenarios](evidence/mobile/12-plan-scenarios.png).

### F11. Following Safe to spend does not land on its explanation — confirmed navigation friction

The phone Overview’s 51,420 hero links to `/plan`. The destination leads with **Due before payday 1,480**, while **Safe to spend** itself starts at **y=843**. Both figures have legitimate purposes, but the user tapped a specific amount and should immediately find its explanation.

**Recommendation:** make this link open the Safe-to-spend breakdown sheet or `/plan#safe-section` with a reliable target; keep ordinary Cash planning navigation focused on the next payments. Use the same pattern for other KPI drill-downs. Follow-up: **IV-3AN, IV-3G**.

### F12. Payday allocation is too complicated for its moment — observed friction plus confirmed visual defects

The phone payday screen begins with a paragraph about cash assignment, an enable button, a separate before-payday card, then another figure called Cash available to assign. It subsequently lists disabled funding fields even before the feature is enabled. Labels run together, e.g. **“Eating OutFunded spending left”**, and the reserve suggestion renders **60420.110000** rather than a usable money input.

The distinctions between budget limit, actual cash, funded cash and reserves are important. Asking the user to learn all of them before accepting a useful payday proposal is not.

**Recommendation:** present one proposed allocation: **Bills protected / Everyday spending / Emergency and goals / Left unassigned**, each expandable. Explain “No bank transfer will be made” next to confirmation. Show the post-allocation Safe-to-spend result and undo. Only show detailed editable category fields when the user chooses to customize. Format entry amounts to their currency’s precision and separate labels visually.

Source: `lightning/ui/templates/phone/planning/payday.html`. Evidence: [phone payday](evidence/details/phone-payday.png). Rendering fixed: **BV-3AS** (#331), `tests/test_phone_payday_browser.py`; **IV-3G, IV-3AN** for simplification.

### F13. Property/vehicle pages expose irrelevant complexity — observed friction and brand violations

After the valuation and purchase details, a car account displays a full **Buy / Sell / Dividend** investment form, followed by a cash-style transaction register. The phone page is several screens long. “Import statement” is also offered prominently on the PC car account. These controls reflect the underlying generic account implementation more than the user’s job.

The new shared details partial also reintroduces **cards inside a card**, cents on headline figures, and an ordinary select of the user’s loans. This contradicts A16 and the established phone-specific pattern; the existing brand test’s sample does not contain this new asset detail state.

**Recommendation:** lead with current dated estimate, change since purchase and linked debt. Primary action: **Update value**. Secondary actions: **Edit purchase details / View loan / Record sale** where supported. Show investment-unit and cash-import tools only where genuinely applicable. Use flat phone rows and a searchable loan picker. Fixed: **BV-3AT** (#331), `tests/test_asset_details.py::test_the_account_page_shows_the_change_since_purchase_the_history_and_the_loan`.

## Visual and accessibility assessment

The mint/blue surfaces, dark-ink hierarchy, typography and consistent navigation give the core product a recognizable identity. The latest phone budget and register are far more scannable than a scaled-down table. The improvement needed is **selective density and hierarchy**, not more decoration.

| Area | Finding | Change to make |
|---|---|---|
| Information hierarchy | Desktop holdings below the fold; phone scenarios start with caveats and an unchanged comparison | Answer + working rows on PC; one question + one action on phone |
| Visual warnings | Fully paid rent appears risky on phone | Fix classification before changing warning colors |
| Numeric formatting | New asset heroes show decimals; payday suggestion exposes six decimals | Whole-pound summary, exact currency precision in fields, explicit units |
| Components | New asset details use nested tiles; secondary forms do not consistently use phone composition | Reuse the current shared semantics with dedicated phone rows/sheets |
| Touch | Capture category chips measured **40 px** tall in the flow evidence | Increase or provide at least the guideline’s 48 px effective target; verify close/overflow controls too |
| Date editing | Compare-period date fields are narrow enough to truncate the visible date in phone Chromium | One legible date-range row opening a dedicated picker |
| Text | “Eating OutFunded spending left” visually merges label and explanation | Separate name, state and editable value; do not rely on inline `<small>` for layout |
| Scope/freshness | Historical comparison, today’s balance and future projection coexist | Put the relevant date and estimate/source status beside each decision figure |
| Arabic | Core Overview, capture and transactions render mirrored with readable digits in inspected screenshots | Add new asset, scenario and allocation states to parity checks; keep dates/currencies isolated |
| Accessibility | Layout and brand automation pass, but that is not a complete accessibility audit | Verify focus trapping/return, keyboard-only flows, announced validation, reduced motion, 200% zoom and screen-reader output on the release platforms |

The phone overflow checks pass in English and Arabic at 320/360 px. They do **not** detect all internal truncation, semantic warning errors or a task buried below the fold. Small controls are an ergonomic concern here; this report does not claim a particular WCAG failure without checking the applicable target-size exceptions and effective hit area.

## Smarter connections: extend what exists

Many links already exist: recurring recognition, salary matching, certificate receipts, reimbursements, reserve-backed bills, cash funding, saved reports, early loan repayment and the new asset-to-loan link. The opportunity is to make the next action appear at the moment of need, with one shared preview and explicit confirmation.

| Trigger and connected features | Smarter next step | Guardrail / completion criterion |
|---|---|---|
| Salary posted → recurring income → payday → budget → reserves → investment planner | Show one reviewed proposal: bills, everyday money, emergency/goals, then investable remainder | Use posted cash; never assume salary received or execute investments automatically; preview resulting availability |
| Bank SMS → quick capture → later statement import → existing transaction | Preserve provenance and offer to link the statement row to the recorded payment | One economic event, one posting; ambiguous matches remain questions |
| Repeated category correction → counterparty alias → rule → historical matches | Suggest “Apply this to these 8 past entries and future matches” with before/after examples | User chooses scope; conflicts and exclusions visible; reversible action |
| Bill becomes due → matched bank payment → reserve → budget | One bill sheet: already paid? link receipt; otherwise record payment and show reserve effect | Do not add another expense when a matching payment exists |
| Emergency drawdown → reserve target → refill → cash forecast | Recommend a refill schedule affordable after upcoming needs | Correct F3 first; recompute after-state and keep a manual alternative |
| Reimbursable expense → claim → incoming payment → category/net spending | Offer Create claim on the transaction; offer Match reimbursement on the receipt | Claim outstanding and cash received remain distinct; partial matches reduce once |
| Car/property → dated valuation → linked loan → wealth change | One detail view for value, liability and value less remaining payments, with dated history | Correct F1/F2 first; label remaining instalments honestly; handle FX explicitly |
| Certificate nearing maturity → expected event → actual receipt → payday/investment planner | Show “Expected on date,” then allocation choices only after receipt is recorded | Forecast is not received cash; preserve explicit receipt matching |
| Purchase check → budget category → selected payment account → forecast | Show both “fits your plan” and “this account has enough on that date” | Separate liquid cash from net worth; carry assumptions and record only on confirmation |
| Investment result → valuation freshness → holdings → transaction history | Explain what changed from contributions, prices, FX and income, with affected rows | Missing/stale values remain visible; allocation suggestions are not affordability advice |
| Needs you → weekly review → underlying task | Group by job and consequence: money at risk, unreconciled events, optional cleanup | Reviewed/snoozed must not silently mean financially resolved |
| Phone capture → PC review → phone confirmation | Keep task state, source and pending/confirmed status consistent across devices | Existing journal/native acceptance remains open; no silent duplicate writes |

These proposals belong primarily to **IV-3G** (smart wiring), **IV-3H** (weekly friction and trust), **IV-3AM** (desktop), **IV-3AN** (phone), and **NF-4A/4B** for cross-device completion. They are extensions, not claims that the listed modules are absent.

## What to simplify

1. **Financial vocabulary at the point of decision.** Keep Net worth, Free cash, Safe to spend, Left in plan and Cash available to assign because they mean different things. Show only the one needed for the task, with a short “How calculated” breakdown. Do not collapse them into an inaccurate universal “Available.”
2. **Planning layers.** Budget limits, recurring obligations, cash assignments, reserves, forecasts and investment targets should feel like successive choices in a payday job, not six independent setup projects.
3. **Duplicate review entry points.** Overview, Needs you, Weekly review and feature-specific warnings should lead to the same task detail and resolution state. Keep the broad lists where useful, but avoid asking the same question repeatedly.
4. **Generic asset/account tools.** A cash wallet, brokerage, certificate, gam’eya and car should not expose identical entry controls. Use the account type to choose the default task, with advanced controls available deliberately.
5. **Read views that look like forms.** Use read-first summaries and deliberate edit modes in Settings, planning and asset details. Keep direct editing for desktop bulk work where it actually saves time.
6. **Expert explanation in everyday paths.** Put methodology, model scope and optional AI handoff behind concise disclosure. Preserve warnings that change the decision; remove text that merely repeats the heading.

## Review of the user-question document

The document remains a good **question inventory**, but it is not a trustworthy current feature-status list. Its historical date should stay intact; add a current linked coverage matrix rather than rewriting the original audit.

| User question | Current evidence | Remaining UX task |
|---|---|---|
| Where do I stand, and what needs me? | Desktop wealth lead and Needs you; phone Safe-to-spend hero and review summary | Reconcile account/wealth totals; make urgency lead to a specific action |
| Where did my money go? | Spending, ranked categories, comparison and drill-downs | Maintain date context; move optional AI controls below the main answer |
| Am I on plan? | Budget limit, remaining amount, everyday pace, category sheets and cover actions | Correct fixed-payment pace; distinguish plan allowance from cash available |
| What do I hold, and how did it do? | Holdings, allocation, returns, investment reports and price controls | Bring holdings forward; show freshness and result decomposition in context |
| How much can I actually spend? | Safe-to-spend bridge, purchase check and scenarios exist | Contextual drill-down and account/date-specific affordability; safe refill proposal |
| Am I safe if something goes wrong? | Emergency cover, targets, refill and liquidity context exist | Fix refill decision; tie proposed amounts to upcoming commitments |
| How do my figures compare with my limits? | Financial health evaluates configured limits | Lead with exceptions, then supporting ratios; distinguish unassessed figures |
| What happened in this account? | Register, search, imports, ownership, balance and history | Asset-specific view; consistent dated value; stronger bulk action scope |
| Whose money am I holding? | Cash and investment ownership and history exist | Keep “held” distinct in all totals; link actions from the account/transaction |
| Is my data right? | Integrity checks, activity and review workflows exist | Keep mathematical integrity separate from categorization/reconciliation completeness |
| Why did net worth change? | Wealth bridge exists and Mohab verifies its reconciliation | Surface it from the change figure; do not list the bridge as missing |
| Can I afford a purchase? | Current Cash planning includes “Can I afford this?”; scenarios include a purchase | Clarify scheduled-only scenario vs budget-inclusive affordability |
| What about a refund? | Refund reduces Money out; current Mohab assertions verify it | Cross-month attribution is a product policy, not proof of broken arithmetic; explain the basis |
| What does work owe me? | Claims and explicit partial receipt/refund links exist | Add contextual start/match actions to transactions |
| Where should income go? | Optional funded payday preview exists | Simplify it and correct formatting; do not describe it as absent |
| Refill emergency / pay a loan early | Refill and early-payment workflows exist; Mohab covers early payoff | Refill forecast impact and discoverability remain the issues |
| Certificates, FX and overseas investments | Certificate events/reconciliation, FX and investment return services exist | Native data/source limitations and freshness remain separate from UI availability |
| No-pay month, early salary, raise, future budget and month-end recurrence | Current tests cover several early-pay and averaging cases; the old prose is insufficient to judge all remaining cases | Reconcile each old gap with its dedicated regression before carrying it forward; unverified residual cases are not asserted fixed here |

`docs/product.md` also describes investment lots/ROI as planned while the current plan marks the investment milestone complete. Documentation drift can cause new work to duplicate features already present. Done: **IT-1Q** (2026-11-06): the matrix above is the current coverage, linked from [r14](../r14-users-main-questions/report.md#dated-follow-ups); `docs/product.md` corrected.

## Recommended implementation order and acceptance

| Order | Scope | Evidence needed to call it done |
|---|---|---|
| 1 | F1/F2 asset value and zero-opening handling | Header, detail, history, equity and wealth agree; zero opening and FX cases; no fabricated cash |
| 2 | F3 refill and F4 cross-screen totals | Before/after forecast preview; common total definitions with negative gam’eya and held funds |
| 3 | F5 false pacing and F12 numeric/label rendering | Paid fixed bills are not “ahead”; variable overspend is flagged; clean phone fields |
| 4 | PC analysis/bulk continuity | Trace a change to its rows; select all matching; preview/edit/export the same scope; recover a mistaken action |
| 5 | Phone secondary flows and specific KPI drill-downs | Safe-to-spend explanation at destination; holdings/next task in first viewport; one-purpose scenarios |
| 6 | Smart links and documentation | Complete salary-to-allocation and receipt-to-obligation loops with explicit confirmation; current question matrix |

Suggested usability tasks for the next release review: log a cash expense; link an SMS and later bank statement without duplication; pay a bill from its reserve; explain a spending increase; correct 50 matching transactions; find a historical payment; assess a purchase on a particular account/date; refill emergency without starving the plan; explain a car’s value and remaining payments. Measure completion, wrong actions, backtracking and whether the user can state the answer—not tap count alone.

## Validation results

| Check | Result | What this does and does not prove |
|---|---|---|
| `tests/test_brand_audit.py` | **24 passed** | Sample desktop styling/interaction checks; does not cover the new car detail state |
| `tools/phone_check.py` | **Passed** at 360/320 | Main sampled English pages do not scroll sideways or clip past viewport |
| `tools/phone_check.py --arabic` | **Passed** at 360/320 | Same bounded Arabic layout check |
| `tests/test_asset_details.py`, `test_audit_numbers.py`, `test_audit_wording_display.py` | **27 passed** | Existing assertions pass despite the uncovered state-specific defects |
| `tests/test_mohab_year.py` | **112 passed** | Current reference financial journey; not every device/edge case |
| Current quick-action flow harness | Capture, live search, SMS prefill and sorting exercised | Uses working scoped profile setup; bill-payment branch absent from this date’s Overview, so no claimed measured payment completion |
| Additional financial probes | F1–F4 reproduced | Dummy data only; source and browser evidence as described above |
| `tests/test_docs_structure.py` after filing this report | **14 passed, 1 skipped** | Report/plan structure passes; sibling website guideline-copy comparison skipped because that repository is not present |

The first sandboxed server/test attempts could not use local sockets; the successful checks ran with authorized local-server access. The historical flow harness’s unscoped profile-submit helper failed; the retained copy uses the working scoped helper and preserves the task steps. Test dependencies available in this environment were used, not a complete reproduction of the Windows/Android lockfiles.

Evidence scripts run from the repository root: `python reports/r24-desktop-phone-ux/evidence/probes.py`, `capture.py`, `detail-capture.py`, and `refill.py` at the same path. `flows-current.py <output-folder> ar` reproduces the daily flows. `detail-capture.py` creates additional loans/assets before its after-refill capture; the **isolated refill evidence is `refill.py` / `refill-baseline.json`**, which is the evidence for the exact 51,420 → −15,948 result.

This deliverable changes audit documentation and local follow-up items only. It does not change app behavior or claim that the identified problems are fixed.

## Dated follow-ups

- **2026-11-06:** F1, F2, F3 fixed (BT-2AF, BT-2AG, BT-2AH; tests named in each finding). F4 and F5 were fixed on 2026-11-05.
- **2026-11-06, F7 (partly):** the selection bar now says what each tool touches before it runs: **Edit one by one**, **Set category for N**, **Export N**, **Delete N**, and a line naming how many selected rows a category cannot apply to. `tests/test_bulk_action_safety.py::test_selection_tools_say_what_they_will_touch_before_they_run`. Still open: a multi-field preview (old → new), replace-text scoped to the selection, one place for rename, categorize and rule (IV-3G).
- **2026-11-06, F9 (done for Spending and Counterparties):** the AI handoff sits behind **Get another analysis**, below the category breakdown on Spending and collapsed on Counterparties. `tests/test_ai_prompt_buttons.py::test_the_ai_handoff_waits_below_the_answer_on_spending_and_counterparties`.
- **2026-11-06, F6 (PC done; phone Investments waits for the owner):** Cash planning on the PC lists the next 30 days before the secondary cash tiles (y=688, was 970 at 1366 × 768); the PC Investments page was already at y=676. The phone Investments order (hero, stepper, chart, holdings) is the owner's phone-overhaul design pinned by `tests/test_phone_investments.py`; moving holdings above the chart (y=413 instead of 753) was tried, found to contradict it, and reverted pending the owner's choice. `tests/test_phone_frame.py::test_cash_planning_lists_the_next_payments_before_the_secondary_cash_figures`.
- **2026-11-06, F7 (done to the extent the finding asked):** the selection bar names its scope, and **Replace text in selected** previews the count and old → new examples, then changes only the selected rows that contain the text (`tests/test_bulk_action_safety.py::test_replace_in_selected_rows_previews_then_changes_only_those`). Category, replace and rule now sit together in that bar. Not built: a multi-field old → new editor; the remaining bulk work stays in IV-3AM.
- **2026-11-06, F8 (done):** a transactions list opened from an analysis page shows **Back to Spending** with the same period, and **Export all N matching** exports the whole filtered scope in one click (`test_a_list_opened_from_spending_keeps_the_way_back_and_exports_its_whole_scope`). Scroll position on return is left to the browser.
- **2026-11-06, F10 (scenarios done) and F11 (done):** scenarios ask one question at a time (Buy something, Income arrives late, Bill changes) with the first control at y=226 (was 984) and the caveats behind **How this is worked out** (`test_scenarios_ask_one_question_at_a_time`); the Safe to spend card opens `/plan#safe-section` (`test_the_safe_to_spend_card_opens_its_own_explanation`).
- **2026-11-06, F12 (done):** the phone payday page opens on a four-line proposal (Bills protected, Everyday spending, Emergency and goals, Left unassigned) with "No bank transfer will be made" and the unchanged Safe to spend beside it; the editable fields are behind **Customize amounts**, and **Turn on cash funding** is a visible button when it is off. `tests/test_phone_payday_browser.py`. Not built: a Safe to spend figure that changes after the allocation (assigning cash does not change it) and an Undo button on the phone; every assignment is already one undoable action.
- **2026-11-06, visual table:** the compare-period dates stack one per row so the whole date shows beside its picker button (`tests/test_phone_compare_dates_browser.py`). The 40 px category chips are not a defect: the guideline (C05.1) sets chips in a card at 40 px on the phone, so they were left alone; this report's 48 px target applies to primary buttons and fields.
- **2026-11-06, smarter connections:** these are extensions, filed as one split item with their guardrails: [IV-3AY](../../issues/3-polish-and-arabic/3AY-next-step-at-the-moment-of-need.md).
- **2026-11-06, IT-1Q (done):** the user-question matrix above is the current coverage; see [r14](../r14-users-main-questions/report.md#dated-follow-ups).
- Not checked: native keyboard, biometrics and screen-reader behaviour, and the accessibility list in the visual table, which need real devices.
