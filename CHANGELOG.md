# Changelog

Every change to Lightning is recorded here — newest first. Dates are `yyyy-mm-dd`.

**How to log a change**

- Add one entry at the top of `## [Unreleased]`.
- Keep it to three lines at most: what changed for the user or the code, and where. The reasons and details belong in the doc that owns them (`AGENTS.md` lists which).
- To catch up, read only the first entries here, or `git log --oneline -20`. Entries further down are history, not the current specification.
- When a version is tagged, rename `Unreleased` to that version and start a new `Unreleased` above it.

## [Unreleased]

- 2026-10-25 · Claude: Guideline D01, D03, D09, D11 (coders.html, both repos): member pages and their scripts, the account chip and menu in the top bar, the wordmark hiding at 420px, and three paid themes (Moss, Garnet, Frost) beside the twelve free ones.
- 2026-10-25 · Claude: Tasks can carry Lightning Coins: contributors.yml records claims and the new rewards.yml pays the issues a merged pull request closes, through the website's database.
  Needs the SUPABASE_SERVICE_ROLE_KEY secret (without it both only print a notice); bots and the owner's account never earn. CONTRIBUTING.md says how to link GitHub.

- 2026-10-24 · Codex: 8J records the Mono-only free website palette policy, moderated stories and private website receipt uploads; syncs the Coders guideline.

- 2026-10-24 · Codex: 8J bundles two test appearance manifests and validates fixed parts and signed account ownership offline. Native claiming/rendering remains gated on integration and acceptance.

- 2026-10-24 · Codex: [7P, 7Q, 3AG] Make workbooks readable, add validated comprehensive onboarding, group data tools and move AI prompt editing into a popup.
  Clean investment rows and group via dropdown; let Needs you items be reviewed, snoozed or restored, with changed situations resurfacing.
  Update the existing journal HTTP parser override to undici 7.30.1 for the required security audit.

- 2026-10-23 · Codex: 5L attributes investment distributions, withholding and realized gains to their ledger owner, including changed ownership and closed holdings; owned reports no longer prorate another person's income.

- 2026-10-23 · Codex: 2Y validates scaled money against SQLite's signed integer limits; oversized converted values now show a validation error and roll back cleanly.

- 2026-10-23 · Codex: 2X serializes payment linking, preserves settled occurrences against stale confirmations, and makes identical confirmations and partial-loan top-up retries harmless.

- 2026-10-23 · Codex: 2W keeps confirmed reserve use and ledger rows when saving notes, descriptions or unchanged transaction details; financial changes still invalidate reserve links.

- 2026-10-23 · Codex: 2V protects confirmed loan repayments from edits that would leave stale debt; reopen first, or void and replace an extra repayment. Notes remain editable.

- 2026-10-23 · Codex: 4D discovers nearby devices automatically and pairs by selecting the home’s number from three choices.
  The PC still requires the profile password; signed commitment/challenge/reveal protects number matching. Recovery keys are unchanged.

- 2026-10-23 · Codex: record 2U, the phone's website APK download failure, for investigation after the v1.4.4 release at the owner's request.

## [1.4.4] — 2026-10-23

- 2026-10-23 · Claude: package version 1.4.4 (`pyproject.toml`, `lightning/__init__.py`, README, doc headers).
- 2026-10-23 · Codex: reconcile the open PR backlog against current main; preserve the contributor fixes and phone overhaul.
  Audit 5 is the older efficiency audit; its reused 2G–2K/3AC codes become 2P–2T/3AF. Dependency lock refresh remains deferred.

- 2026-10-23 · Codex: fix 2O/3AE: phone Delete asks with the selected count; Cancel keeps the selection.
  A refused mass edit names the blocking transaction and keeps the editor, inputs and selection; successful batches clear them. Add browser and rollback regressions.
  Keep Arabic counts/messages readable and show popup validation once on a full page.
- 2026-10-23 · Codex: fix 2N: optional budget warnings preserve a successful Save. Financial refusals still roll back.
  Protect popup, inline and split edits from stale overwrites (2M); retain unsaved input on conflict. Three other form fields await claim approval.

- 2026-10-23 · Codex: fix 2G/2H: all cash transitions and Undo/Redo refuse new or worse deficits; edits/removals validate previous owners too.
  Imports retain harmless history corrections; multi-delete checks its final state. Add 19 regression cases and promote the ownership workflow probes.

- 2026-10-23 · Codex: extend Audit 4 to button workflows: ownership, mass editing, cancellation, delete/restore, merge, split, bill payment and history.
  File 2M–2O and 3AE, extend 2H; add browser/route probes and screenshots. Full existing suite: 2,349 pass, 9 skip; no production fixes.

- 2026-10-23 · Codex: Audit 4 reproduces six backend defect groups (2G–2L) and files dependency/wiring improvements (1G).
  Report and disposable probes cover cash lifecycle, ownership, currency consistency, retry safety, instalment precision and rollback; no production fixes.


- 2026-10-23 · @yoreva-01: fix 2K/2O/3D/3E: roll back a refused converting buy, confirm phone Delete,
  keep the device banner visible, and translate its borrowed status into Arabic (PRs #105, #108–110).
- 2026-10-23 · Codex: review those fixes: count/Cancel/Undo/category browser checks, complete rollback snapshots,
  lent-status Arabic and literal, escaped names; keep device banners in flow and preserve their action after popup saves.
  Centre notices in both directions so Arabic Undo stays reachable; record the security review and validation.
- 2026-10-22 · Claude: Audit 4 rest. 2G3 held-for-others tagging posts through TransactionService; the ledger's owner is the one record
  of custody. 7N "Due before payday" shows one total (still owed, in EGP) on card, stat and Safe to spend; free cash has one formula.
- 2026-10-22 · Claude: 2I a new profile currency reaches the Currencies tab at once; 2K Integrity checks free cash against the ledger,
  four checks that could not fail removed; 7O import review reads past categories once per statement; 2J one unlock backup a day.
- 2026-10-22 · Claude: 9I writes and the reimbursements page stop growing with history (1,980 → 11 reads); migration
  `0068_drop_duplicate_indexes.sql` drops five duplicate indexes. 9J the Overview, Budget and investment entry stop computing figures.
- 2026-10-22 · Claude: 9K every module has an import layer, one row-id parser, one profile-open task list (month-end checkpoints on
  unlock); 9L 17 unused functions, an always-on flag and two unread settings removed.
- 2026-10-22 · Claude: 2G1–2 marking part of a line as held for someone keeps whole cents (`core/ledger.split_line_e6`), so undo
  works again; a voided sale no longer counts against the owner's next sale (`money_from_others.py`). 2G3 is left.
- 2026-10-22 · Claude: 2H every successful write is its own undo action (except Undo, demo, sample and exports); money held for
  others and the old Settings page were missing, so Undo reversed the action before them (`ui/web.py`).
- 2026-10-22 · Claude: 3AC pages keep their request cache: matching payments no longer opens an empty write, and four budget and
  cash-flow reads are cached (Overview 817 → 507 reads, Cash planning 536 → 274); the Arabic table loads once as `/static/ui-ar.js` (503 → 50 KB).
- 2026-10-22 · Claude: Audit 4 backend engine (`reports/audit-4.md`, written as Audit 3): custody lines, undo grouping and two
  formulas for one figure are wrong; pages redo work. Filed 2G–2K, 3AC, 7N, 7O, 9I–9L.
- 2026-10-21 · Claude: 3W done: the Overview's row is A08 cards (Savings rate on your usual, new figure `usual_savings_rate`; Investing rate on
  the period before; Safe to spend; Left in plan); the holdings table has five columns, units, average, price and account under the name. Where money in went and
  Month by month moved to Spending (owner).
- 2026-10-21 · Codex: 2D completed: v1.4.2 Windows ZIP and signed Android APK are published from the verified original artifacts, with SHA256SUMS and BUILD.json.
  The owner-generated certificate passed signing checks; publishing-only recovery used the current downloads repository address and verified every uploaded file by read-back.

## [1.4.3] — 2026-10-23

- 2026-10-22 · Claude: phone overhaul (3AC, owner PDF; guideline 3.34 Part C): tab bar Overview, Budget, Add, Transactions, More with words;
  every tab opens on one hero figure; month stepper with a Choose period sheet; worded tabs; arrow chips, day nets, no ".00";
  More with live figures; Budget ring, Cash planning due before payday, Investments, Accounts by type, Transactions filters. 3Z done.
- 2026-10-22 · Codex: 4A connects edit synchronization to normal profiles: explicit conversion, enrollment, local handoff, command review and Arabic, home automation, upgrades and signed recovery.
  Android schedules catch-up while unlocked; financial routes use journal commands. Cloud delivery remains an explicit unconfigured placeholder; Windows/Android review packages build and verify in #97.

- 2026-10-22 · Codex: 4A verifies a recovered journal backup against its signed cursor and ledger fingerprint; transaction merge joins the coverage gate.
  2B adds a dummy Windows phase-interruption/reboot drill; physical reboot and abrupt power-loss acceptance remain unverified.

- 2026-10-22 · Claude: guideline B09 copy: website theme is light by default, dark only when chosen (matches the website repo).
- 2026-10-22 · Claude: 3AA: `tools/site_shots.py` dismisses Get set up, parks the pointer, lifts the phone screens off the + button, adds the a-kpis and a-sankey crops, shows Budget for the
  month in progress and Expense analysis for August (a 14,200 holiday payment, spending up 21%); a plain run reproduces the live site screens pixel for pixel, English and Arabic (checked).
- 2026-10-22 · Claude: 2E6 (rest): a plan or reserve amount with more decimals than its currency allows (350.555 EGP, 12.345) is refused, not rounded or kept.
- 2026-10-22 · Claude: 2E6 (part): a crafted category direction says "Choose +, − or ±" instead of a 500, and a transaction id above 2^63 is "not found"
  instead of an OverflowError 500. Dates before an account opened stay open: history before opening is allowed on purpose.
- 2026-10-21 · Codex: 2D adds a publishing-only recovery for the verified v1.4.2 artifacts and uses LightningEg/Lightning-downloads after the repository transfer.
  Fixed artifact IDs, digests, successful jobs and the pinned source/certificate are checked before the protected publisher uploads and reads back the same files; no rebuild or re-signing.

- 2026-10-21 · Codex: Prepare v1.4.2 as the matched Windows and Android release, followed by the website download and archive refresh.

## [1.4.2] — 2026-10-21

- 2026-10-21 · Codex: 2D declares the four signing-secret names at the reusable workflow boundary, enabling the signing job to resolve its android-signing environment values.
  The caller passes only those names; key values remain environment-only, Gradle never reads secrets, and the signed APK must match the pinned certificate. Earlier failed tags stay unchanged.

## [1.4.1] — 2026-10-21

- 2026-10-21 · Codex: 2D pins the new Android signing certificate generated and retained by the owner after the old key was lost.
  Existing Lightning Test installations need an independent backup and reinstall; v1.4.0 was tagged but never published because signing secrets were unavailable.

## [1.4.0] — 2026-10-21

- 2026-10-21 · Codex: Release validation translates bundled price-file origins and source-cited help explicitly in Arabic, with a regression check that includes a bundled price file.
  The purchase browser check waits for the saved loan row, since closing a phone sheet can leave its URL unchanged while saving.

- 2026-10-21 · Codex: 3AB Budget YTD and All time count full saved monthly plans, excluding months before the plan; headlines and group rows agree, while Custom keeps prorated comparisons.
  Mohab's October plan is 38,428, spent 3,410, left 35,018. The pace label clears its line and actual marker; English and Arabic Budget screens recaptured for the website.

- 2026-10-21 · Codex: 3X batches account cash, custody and gold metadata; bill matching writes only when a payment can settle, preserving the request cache.
  Sample Overview: 766 → 364 queries (109 → 119 ms); Cash planning: 541 → 207 (71 → 62 ms). Financial outputs remain identical; tab query budgets tightened.

- 2026-10-21 · Claude: website recaptured from this app (3W site-recapture): net worth 910,304, safe to spend 112,288, nine accounts, new Overview rate crops; Budget screens kept old for 3AB; also filed 3Z, 3AA.
- 2026-10-21 · Codex: 3Y register selection survives edits, cancellation and message redirects; adds Edit selected, Clear selection and Shift-click ranges, plus phone Select all.
  Mass edits affect only selected rows and changed fields; amount/account edits stay on one row with an explicit choice. Browser checks cover both layouts, dialog closure and retries.
- 2026-10-21 · Claude: 4C Audit 3 of the edit journal, fixed: stale command and bulk edits wait for review, replicas verify their rows after
  catch-up, register cannot revert a command, a refused mailbox request is answered. Worker: wire stored apart, monthly allowance per profile.
- 2026-10-21 · Claude: [8H] Site Guides become a map of four topics, each with a pillar page (Budget your salary, See where it goes,
  Know what you own, Your data and devices); track-expenses merged into the expense tracker; one home per FAQ (site PR #47). 8E and 8H done; 8I asks the owner two checks.
- 2026-10-21 · Claude: [8E, 8G] Site: one download wording, version 1.3.0 in structured data, PC shown behind the sync veil,
  slim consent bar, Testing tab for testers only (`?testing`), Sample Profiles download (site PR #46). No comparisons.
- 2026-10-21 · Claude: [8E–8H] The owner's website audit becomes plan items: quick fixes (8E), Home and Features show the app (8F), three owner calls (8G), and the Guides redesign brief (8H).
- 2026-10-21 · Claude: For Geeks home greets with `$ welcome to lightning`, typed once with the caret, while the hero fades up;
  guideline D07 `.hello` and D08 (both repos). Reduced motion shows it still.
- 2026-10-21 · Claude: 8D For Geeks audit: recounted stats (`tools/geeks_stats.py`), keys.py proof, steady Ink hero word, quiet terminal replay, balanced
  mission, roadmap glow runs once, Arabic footer labels For Geeks English; D07 demo port 8766 (both repos). Ideas left for the owner: 8D.
  Contribute links the glossary and AGENTS.md instead of copying them (phone 16,795 → 14,466px).
- 2026-10-21 · Codex: 9G conversion rate updates refresh only affected dates/pairs, atomically with the posting; at 50 conversions, transaction reads fall from 51 to 2 (4.26 to 0.85 ms locally).
  9H removes eight unused backend helpers. Audit 2 and eight regression tests cover rate winners, edits, void/restore, bulk deletion, rollback and existing 2E validation fixes.

- 2026-10-21 · Claude: Mohab comprehensive: the sample gains goals, a gam'eya, zakat, a rule, a claim, Mom's money, a dollar account, a flat, a laptop on
  instalments, targets, a saved report and a waiting statement; the year test gains steps 33–36. Arabic gaps it exposed fixed. `samples/`, `test_mohab_sample.py`.
- 2026-10-21 · Claude: 3W8 phone: each section's title carries its status sentence and the seam (C04.1); Needs you bullets are the mark;
  Accounts leads with What you own ("Total balance" retired); Investments drops Biggest holdings; no Needs you row when nothing waits.
- 2026-10-21 · Claude: 3W5-3W7 answer first: Investments leads with Portfolio value (the waffle and Biggest holdings left; By currency only
  when needed), Accounts with What you own and four groups ("Total balance" retired), Financial health with Within your limits.
- 2026-10-21 · Claude: 3W1-3W4 answer first: Overview, Budget and Cash planning open on their Lead (Net worth, Left in plan, Safe to spend)
  with its working beside it, a status sentence under the title, Needs you rows with the mark, then KPIs. `ui/status.py`, `lead_card`, `needs_rows`.
- 2026-10-21 · Claude: guideline 3.33, answer first (3W): A09 Page order (header, Lead, Needs you, KPIs, details; one home per figure),
  status sentence and seam (A05, A02.3), the page's Lead spans its row (A07); phone C04, C06, C11; A16 gains two checks. Both repos.
- 2026-10-21 · Codex: Added 21 Lightning branding assets from Drive under `assets/logos/`; original filenames kept and active asset references unchanged.

- 2026-10-21 · Claude: 3S 1–2, 3C, 3A: Sale factors wraps its locked-holding note (no sideways scroll); trend and Budget pace end labels part instead of
  overlapping (`charts.end_labels`, `spread_labels`); Currencies rates show two decimals in one left-to-right run (Arabic-safe).
- 2026-10-21 · Claude: 3R: phone sheets show only their form (no undo pill or section tabs); Save without a category says so on the visible field
  and a counterparty fills its learned category; the raise offer is a Budget card that stays; the tab bar hides for the keyboard and sheets.
- 2026-10-21 · Claude: bill matching you can trust (7K). Review of a payment searches every cash account, not only the item's; last month's payment is no longer
  offered for this month; salary or a bill paid early is not counted twice in the forecast and Needs you offers Link (`PlanningService.early_payments`).

- 2026-10-21 · Claude: demo and sample stop showing false alarms (3V, 7L1). The demo certificate pays what its 22% says, on its payout day, so Match all clears
  its item; the demo adds an untracked gym for Looks recurring; `--sample` opens on 2026-10-02 (no late bill); "Your income went up" ignores yearly, quarterly and Bonus income.

- 2026-10-21 · Claude: 3U1–3U4: in Arabic a "·" beside a number becomes "،" (it read as a zero); one decimal "٫" and "%" everywhere, including
  figures in brackets or before a comma; the undo button and six more strings are translated. Test: `tests/test_arabic_separators.py`.
- 2026-10-21 · Claude: 5H: the Investments reconciliation moves into `investments/report.py::reconcile_portfolio` and counts the exchange-rate revaluation
  of dollar brokerage cash on its own, so Mohab's sample (YTD) no longer shows an unresolved +1,394.
- 2026-10-21 · Claude: 2E1–2E5: a split respects the account's decimals; money in or out is refused on a gold account (and not offered); an entry that takes a wallet or bank below zero is refused, with a data check; an unknown owner and a zero planner amount say so instead of a 500.
- 2026-10-21 · Claude: Audit 1, demo readiness (`reports/audit-1.md`): engine, smart logic, PC guideline, phone and Arabic. The math holds; found
  input-check gaps, bill-matching trust bugs, hidden suggestions, phone sheet bugs and an Arabic "·" that reads as zero. Filed 2E, 2F, 3R–3V, 5J, 5K,
  7K–7M; 5H's cause found; demo cut list first in `NOW.md`.

- 2026-10-20 · Claude: website page "Net worth, budget and expense tracker" in English and Arabic (site PR #41) so AI search finds Lightning for all three together;
  Overview decision, Competition section *How AI search finds us*, owner tasks in 8C (sitemap resubmit, Reddit post). The website home hero line now reads as the comprehensive planning app (site PR #42).

- 2026-10-19 · Claude: Budget and Cash planning open with KPI cards that compare (3Q step 2, `ui/kpis.py`). Budget's day rate counts
  everyday money only, with a pace chart and the month's bills in place of the waffle; Cash planning compares with last month-end,
  payday and today. "Bills and loan payments before next income" is now "Due before payday"; Glossary adds Everyday spending.

- 2026-10-19 · Claude: guideline 3.32 (both repos): KPI cards in five fixed slots with a compulsory comparison, rows of two to four, A08.4 micro-visuals,
  A08.5 zero and alone, thin-data chart forms, A16 adds two lines (3Q). Arabic body text is Noto Sans Arabic, not IBM Plex Sans Arabic (app fonts, CSS).
  Style, profile and font CSS carry new cache versions so installed apps load the new face.

- 2026-10-19 · Claude: visual audit of every tab's cards filed as 3Q: a five-slot KPI card with a compulsory comparison, rows that never
  leave a card alone, thin-data chart forms, and the guideline changes they need (owner answers first).

- 2026-10-19 · Codex: register selections stay visible and responsive during editing (3M); Savings shows saved or overspent with darker excess squares (3N).
  Forecast bars share a baseline (3O); reserve matching combines account, counterparty and category beside their controls, requiring all selected criteria (3P).

- 2026-10-19 · Claude: AGENTS.md: any guideline change lands in both repos; website copies of the field-well colours synced (website PR).

- 2026-10-19 · Claude: Budget "left" per category and group reads as the rounded figures beside it (671 − 634 = 37, not 38), matching the meters (3L).

- 2026-10-19 · Claude: Editable fields are green wells, calm yellow on focus, not blue (A10.3) (`style.css`, `style.rtl.css`).
- 2026-10-19 · Claude: guideline Part D D06: cells over the field fade from 94% to 30% at their edges (`--soft`), hairlines drawn by
  each cell; terminal and code stay solid wells. Matches the For Geeks site.
- 2026-10-19 · Claude: guideline Part D: panels over the field use `--veil` (94%), and a strike on a phone is two strokes with no
  full-screen glow or flash (D06, D08), matching the For Geeks site (site PR: smooth strikes on phones).
- 2026-10-19 · Claude: three backend good first issues for contributors who aren't on Arabic or screens: 7H CSV amount forms (#49), 7I public
  holidays in payment schedules (#50, was 7F1), 7J Arabic spelling variants in search (#51); each with the file, the test and a check command.

- 2026-10-19 · Claude: guideline Part D, **Coders** (`guideline/coders.html`, D01–D12) for the website's For Geeks pages; Part B is now **Normal**;
  `tools/guideline.py` reads D and the docs test checks four files. It matches the site after 1F (site PR #34): one contribute path in the
  top bar, the three steps said once, a section strip on phones, the shell from `tools/geeks_shell.py`.
- 2026-10-19 · Claude: `report/` and `docs/proposals/` merged into `issues/`: nine numbered milestones (1 Easy to contribute first), items coded `3C`
  (steps `3C1`), types bug/polish/feature/tech/owner; `tools/issues.py` builds `issues/INDEX.md` and gives the next free code. Overview's roadmap,
  `NOW.md` *Next*, AGENTS.md, skills and links now point at codes. Done: 1A (website contribute path, site PR #32), 1D (codes on GitHub).
- 2026-10-19 · Claude: collaboration audit: `requirements-dev.txt` adds the encrypted extras (the contributor setup failed 361 tests); reports
  older than 30 days are a stale-check warning, not a failing test; `/take` claims with an open PR stay; Dependabot groups; main no
  longer needs branches up to date, auto-merge is allowed (owner setup); CONTRIBUTING: one-file test, AI steps to merge a contributor PR.
- 2026-10-18 · Claude: one collaboration guide, `CONTRIBUTING.md` (MAINTAINERS.md and docs/COLLABORATION.md merged in); `tools/security_setup.py` is the one owner command and
  runs the no-bypass PR rule; old team/approval ruleset and `apply-settings.sh` removed; forks wait for approval on a first PR only. Contributing is GitHub-only (`/take`), with
  Codespace steps; the Discord route and claim-button proposal are dropped.
- 2026-10-18 · Codex: record completed collaboration work, the website-to-Discord contributor journey, and proposed numbered task roles/claim automation with pending decisions clearly marked.

- 2026-10-18 · Codex: document owner-account AI PR merges; add a previewable app/website ruleset setup that blocks direct main pushes and bypassing checks.

- 2026-10-18 · Claude: MAINTAINERS.md step 6 and apply-settings.sh name the environments the workflows use (android-signing, production-release, market-publishing), not `release`.

- 2026-10-18 · Claude: contributor onboarding in three steps: good first issues, `/take` bot (`.github/workflows/contributors.yml`), Codespaces demo (`.devcontainer/`); one-screen CONTRIBUTING.md, short PR template, Discord set-up in Collaboration §9.
- 2026-10-18 · Codex: require the phone workflow test to keep signing keys in the protected signing job and out of its caller.
- 2026-10-18 · Codex: document collaboration in docs/COLLABORATION.md; add a previewable admin setup script, environment-only signing inputs, and journal dependency CI.
- 2026-10-18 · Codex: patch journal development dependencies (Wrangler, Undici and Sharp); record the repository/website security review and pending deployment.
- 2026-10-18 · Codex: resolve PR #19 conflicts, retaining the owner-requested AI review and merge permissions.
- 2026-10-17 · Claude: collaboration and security setup: PR checks (tests, dependency review, CodeQL), SECURITY.md, PR/issue templates, Dependabot, importable owner-only-merge rulesets, `.github/MAINTAINERS.md` (settings only an admin can switch on); AGENTS §6: the owner, or an AI with a second approval on non-sensitive paths, merges to main.
- 2026-10-17 · ChatGPT: require PRs for internal, external, and AI-authored changes; only the owner may merge to main. Document AI review limits and CODEOWNERS safeguards.
- 2026-10-17 · Codex: give the Windows profile and UI test suite 20 minutes; the previous 10-minute cap expired before the suite finished.
- 2026-10-17 · Codex: regenerate the Arabic stylesheet mirror and update stale investment and overview acceptance checks.

## [1.3.0] — 2026-10-17
- 2026-10-17 · Codex: remove the stale 2026-10-09 handoff note after owner approval.
- 2026-10-16 · Claude: journal chunked large effects (≤1 MiB per action) and bank-statement import as commands; Mohab's year on a journal home now passes import.
- 2026-10-16 · Claude: journal areas for settings, people, investments, CDs, gam'eya and physical items (with Sonnet agents); write-coverage audit
  (`tools/journal_coverage.py`: 77 of 149 POST routes covered), graceful uncovered writes, `tools/journal_mohab.py` gauge; lab `--app` opens the real screens.
- 2026-10-16 · Claude: feedback batch 004 (tickets 96–112): mass edit applies (answering its question no longer re-submits the row); Undo/Redo are header icons with Ctrl+Z; one error page and a branded phone start; shares by ticker, funds apart from EGX; overspending shows a rose card; Net cash flow bars; months as one grid; the Cash planning budget shortfall links to Budget.
  A foreign account's register reads in its own currency; the Overview's one-line Investments row is removed.
  Open (reports filed): shared prices not published (owner action), website forms.
- 2026-10-16 · Claude: the plain app (`run.bat`, `python -m lightning`) starts again without `cryptography`: `journal/codec.py` imports
  signature checks only when verifying; `tests/test_plain_install.py` keeps it so.
- 2026-10-16 · Claude: journal areas for currencies, conversions, reserves, plans, bills, instalments and budgets (with two Sonnet agents); the app's own
  screens run on a journal profile via `proxy.JournalServices`: the home confirms at once, other devices rehearse, save and show "Saved on this device".
- 2026-10-16 · Claude: journal J6c started: command proposals run allowlisted service actions on the home with exact row effects and row-hash
  preconditions (`commands.py`, `areas/`); open/update/archive accounts and create/update categories from any device.
- 2026-10-16 · Claude: journal J6b: replicas (lab, tests) start from the home's verified checkpoint (`snapshots.checkpoint_replica`); `initialize` creates homes only.
- 2026-10-16 · Claude: journal J6a: generic exact row effects (`sync/journal/effects.py`) replace the cash-only schema: touched rows of synchronized tables replay
  exactly with UUID references, per-row fingerprints, generic checkpoint repair; a cash edit is 7,952 bytes in one round (was 12,284 in five).
- 2026-10-16 · Claude: journal transport and pairing: one combined sync round (20 offline edits: 64 → 3 mailbox wake cycles), downloads continue when upload is held;
  pairing shows matching digits before any password proof leaves the device. Confirmation now 102 SQL statements at any ledger size (was 33,100 at 1,500).
- 2026-10-16 · Claude: journal hardening: undo reverses only its own change and conflicts go to review; a recovered home answers resent prefix edits;
  one failing proposal waits alone (`home-error`); manual same-day repeats post; confirmation diffs and fingerprints only touched transactions.
- 2026-10-16 · Claude: reviewed the edit journal (J1–J5): 7 reports under `report/` (area journal): undo overwrites later edits, recovery replays
  the prefix and jams the successor, one service error halts all confirmation, review backlog stalls sync, offline-crackable first pairing, mailbox and confirmation cost.
- 2026-10-16 · Claude: **One row per broker, a cash pocket per currency** (`0067_broker_pockets.sql`, `accounts.parent_id`): a listing in another currency is held in that currency's pocket, made on demand; *Paid in another currency* converts then buys (two linked documents); no margin;
  the sidebar and Accounts show one row per broker, its page shows cash by currency and every holding, ⋯ › Add a currency.
- 2026-10-16 · Claude: investment events on a brokerage account's entry: Dividend gains an optional *Tax was taken* (gross income, tax its own cost, Net gain uses net), plus Fee, Interest and Move to another broker (average cost carries over, no cash, no gain);
  new category Investment › Tax withheld (`0066_investment_tax_category.sql`); `tests/test_investment_events.py`.
- 2026-10-16 · Claude: Investments: holdings grouped by class, account, currency, market or security (`?view=`, `investments/views.py`), a By currency card (holdings + brokerage cash), an EGP · USD lens (`?lens=usd`, display only) and "of your gain, X came from exchange rates".
- 2026-10-16 · Claude: visual round 2: register folds value updates (`?val=1`) and keeps saved views in one Views menu; holdings table fits 1366 px (units, share, horizon under their figures);
  Budget shows the raise prompt (Raise the plan / Save the difference); fewer explaining lines (Accounts, Add account, New investment, prices sources, Cash planning, Held for others when zero);
  7 more brokers (Al Rajhi, SNB Capital, Derayah, Sahm, Emirates NBD Securities, Schwab International, Trading 212) and IBKR lists the Gulf.
- 2026-10-16 · Codex: added verified, resumable first-replica enrollment, owner-wrapper/authority-chain transfer and crash-safe publication; sender-local keys and queues stay out of checkpoints.
  Home transitions resume after interruption, verify the pinned retirement signer and rotate transport keys atomically; offline peers verify consecutive authority certificates. Native cutover and full write coverage remain gated.
  Prepared the companion website guideline-copy fix on `codex/sync-app-guidelines`; its public main push awaits separate owner approval.
- 2026-10-16 · Codex: added experimental local-first journal routing, automatic paired-device discovery, free-only Worker/SQLite delivery and resumable snapshots without R2; no paid subscription or live deployment enabled.
  Added a Devices preview with named nearby discovery, six-digit pairing and automatic saved-device key updates; guarded owner transitions and encrypted queue recovery remain experimental, with native integration and full write coverage gated.
- 2026-10-16 · Codex: continued J2/J3 on the journal branch: real cash-service confirmation/replay, PC/phone pending/review screens, pinned local TLS, queue-preserving checkpoints and SMS/CSV review with duplicate linking, progress and undo.
  Added a persistent password-protected dummy launcher and bandwidth probe; production profiles remain on v1 and unsupported financial writes are blocked; phone amount fields retain their required 56px height.
- 2026-10-16 · Codex: started the authorized six-stage edit journal with an isolated encrypted J1 laboratory, signed proposals, atomic decisions/replay, conflict review and a runnable fault-tested simulator; live profiles remain on v1.
  Disk-full transaction cleanup now preserves SQLite's original failure, including when it automatically rolls back nested work.
- 2026-10-16 · Claude: currencies said out loud: a foreign holding's price, average cost and trades in its own currency (holdings table, holding page), a USD account's header in USD and ≈ EGP, Prices with currency and no trailing zeros; Foreign money counts foreign investments;
  held markets are followed automatically; exchanges without a rate source (ISK) are not offered and MIC codes are gone from pickers; a listing may trade in another currency than its exchange (USD fund, USD line in London); KWD/BHD/OMR/JOD keep 3 decimals.
- 2026-10-16 · Claude: **Kept apart**: brokerage and foreign-currency cash no longer count in Free cash, Safe to spend or the payday pool (still in what you own and If you sold today); ⋯ › Count its cash as spendable overrides it per account (`0065_account_spendable.sql`, `Position.kept_apart`). Mohab's Safe to spend 40,937 → 40,537 (THNDR's 400).
- 2026-10-16 · Claude: Add account asks the institution first (its kind sets the type, the name is suggested; Held for and Notes sit under More); owner pickers list people only (`counterparties.kind`, migration `0064_counterparty_kind.sql`, person/business toggle in Counterparties); plan Matching settings fold away; broker list gains 11 brokers with `markets` and `home_currency`.
- 2026-10-16 · Claude: Audit wording and display: locked certificates read "not counted until <date>" (muted, spaced); "Planned" replaces "Bill linked"; "Late · N days" chip, late first; Weekly review heading once; savings-rate period beside the figure.
  "Budget until payday" and "Bills due, loans apart" renamed; Health shows months in cash you own; the planner splits by your current mix without targets and takes the Overview's free cash; no "Aliases · 0".

- 2026-10-16 · Claude: certificate interest now matches the bank's fixed payout (payer = the portfolio's institution, amount within 5-15%, 31 days): one pre-ticked suggestion per expected payout, "Match all suggested" once, and Needs you shows one item per certificate, not per month (`deposits/receipts.py`, deposit and review templates).
- 2026-10-15 · Claude: two owner-requested reports, nothing fixed: an outside review of every tab (figures, wording, links, wiring, next steps) and a design for brokerages across exchanges and currencies (pockets, listings, workflows, analysis); `report/`.

- 2026-10-15 · Claude: Page jump stays bottom right and appears only near the corner or while scrolling; the PC loading note matches the phone (muted square, bottom right, 300 ms);
  Financial health figures have three bands (Good / Watch / Needs you, editable; `HealthService.band`); Needs you tints the card soft rose (U1, U14, U15).
- 2026-10-15 · Claude: Quiet forms: picker results are popovers, one line (name · ticker · exchange); investment entry is a segment + rows with a live "You pay" line (fee choice kept); fewer help lines (A14);
  same ticker on two exchanges stays two holdings; salary "arrives on day N"; compact recurring-item form (U8, U9, U3 layout, U12, U13).
- 2026-10-15 · Claude: Register: ticked rows survive opening a row to edit; saving with several ticked asks "Only this row / All N rows" and `POST /transactions/bulk-edit` applies only the changed fields
  (`TransactionService.bulk_update`; amounts never; unfit rows skipped and counted). U2, designs 005.
- 2026-10-15 · Claude: Account page: **Money actions** menu only for Cash and Bank (Convert currency, Change ownership, Bought in instalments); "Check against bank" is now **Adjust balance** on every cash-holding account (CDs and physical items say Update value);
  the brokerage asset-class table became a **What's in it** bar (U4-U6, designs 005).
- 2026-10-15 · Claude: import posts a day's money in before money out when the day ends at or above zero, so a newest-first statement no longer fails on overdrawn spending (T15, `bank_imports.py`).
- 2026-10-15 · Claude: Import review is one row per bank line with filter chips and a bulk edit bar; no per-name `group_*` choices; held for works on any row (T12-T14).
- 2026-10-15 · Claude: welcome page: the sample offer is four equal boxes (Mohab's year, Amr, Menna, Fatma) under one section header; the three-month button, long paragraphs and CSV links are gone; `welcome.html`, `style.css`.
- 2026-10-15 · Claude: page header: one `.topbar` CSS block and a `page_header` macro (tile, title, line, figure strip); the account page shows its bank's tile, a Balance strip, one Secondary (Import statement) and ⋯; guideline A05/C04.7.
- 2026-10-15 · Claude: date picker: the month title opens a 12-month grid and its year opens a 12-year grid (‹ › page by 12), Escape goes up a level; `app.js`, `style.css`, `phone.css`, guideline A10.3.
- 2026-10-15 · Claude: short fields sit side by side (`.form-grid`, A10.3): the account form, the CSV column-mapping page (amount model is now a two-choice segment) and the instalment and early-payment forms; starting balance is a soft section, not a card in a card.
- 2026-10-15 · Claude: field wells are a blue-tinted `#E8F1FA` (focus `#E3EEF9`), defined once as `--field` and `--field-focus`; guideline A10 tokens updated in the app and phone files. Contrast: Ink 14.22/13.81, Ink 2 8.14/7.91, Muted 4.68/4.55.
- 2026-10-15 · Claude: institutions: the account form's Institution is type-and-pick over 46 Egyptian banks, brokers and wallets (plus your own), with logo-or-monogram tiles in the picker, accounts list and sidebar; migration `0063_institutions.sql`.
  Logos could not be downloaded here (no network): run `tools/fetch_institution_logos.py` from a PC.
- 2026-10-15 · Claude: account form: the cash type reads Cash, More details and Last 4 digits are gone (a stored last 4 is kept), no Travel in new profiles' categories; the Mohab sample's Sahel weekend is Entertainment.
- 2026-10-15 · Claude: setup starts with your currencies (profile base plus others held, as chips); the account form's currency is a pick list of registered currencies only; welcome Add links wait for the save; `welcome.html`, `routes/dashboard.py`, `accounts/form.html`.
- 2026-10-15 · Codex: tested and repaired smarter workflows: redo validation, duplicate merge, linked reserve spending, goal review, month-end promotion and selected-account currency labels; regression coverage and browser checks added.
  Also fixed exact matching limits, wrong-currency payments, early-payment review, numeric CSV exports, Arabic text, profile-scoped reminder dedupe and batched reserve lookup performance.
  Migrations: `0056_checked_history.sql`, `0057_import_provenance.sql`, `0058_saved_views.sql`, `0059_reimbursements.sql`, `0060_plan_matching.sql`, `0061_deposit_receipts.sql`, `0062_cash_funding.sql`.

- 2026-10-15 · Claude: `tools/site_shots.py` adds the dollar brokerage (`account-usd`) and the holdings row with its price/FX split (`a-holdings-usd`) for the website's new dollar savings guide; one Arabic finding filed.
- 2026-10-15 · Codex: added session undo/redo, checked bank-history protection, multi-source import provenance, safe duplicate merge and combined activity review on PC/phone.
- 2026-10-15 · Codex: connected partial reserves, configurable bill matching and transaction-to-plan setup, certificate receipt reconciliation and explicit partial reimbursement claims.
- 2026-10-15 · Codex: added optional funded payday assignments, reusable saved views/report/export, rule correction offers, selected bulk preview, weekly review and opt-in native reminders. Local implementation; automated/native behavioural acceptance outstanding.

- 2026-10-15 · Codex: Cash planning and Needs you now flag dated scheduled-cash shortages, including an underfunded payment account when total cash is sufficient. PC and phone show account links and explicit FX/unassigned-account limits; monthly free-cash estimates remain separate.

- 2026-10-15 · Codex: refreshed Actual Budget comparison from current code/docs; recorded cash-timing, multi-source import and partial-reserve workflow findings. Measured 18 sample-data pages; runtime behaviour unchanged.

- 2026-10-15 · Claude: new skill site-recapture with `tools/site_shots.py` (the site's PC, phone and paired screens in English or Arabic, sizes as the site uses them); website-sync points at the site's new `tools/release.py` and `tools/site_check.py`.
- 2026-10-15 · Claude: website recaptured from main (Mohab to 2026-10-04): seven places with the dollar brokerage, a Pounds and dollars section, Download as the header button and the home page's main action, search titles under 60.
  Six findings from the capture filed in `report/` (device line, Currencies screen, the sample's reconciliation gap).
- 2026-10-15 · Claude: account page header: the type and bank line sits under the title, and the three figures (in this account, what you own, held for others) share one strip, the first largest; `register.html`, `style.css`.
- 2026-10-15 · Codex: Spending compares the same days across months; running comparisons stay neutral. Holdings gains include income and sales; PC/phone register rows keep signs and cents, account totals stay whole.
  Gam’eya shows every due instalment and payout, with atomic dated catch-up. Overview previews Needs you and shows portfolio KPIs together; Reserves and Health show separate emergency liquidity context. Phone list shells, alias action and comparison spacing now follow Part C; Arabic text and RTL mirrors updated.
- 2026-10-15 · Codex: Europe/GCC adapters now include Oman and Nasdaq Nordic, venue currencies and underscore tickers, with collector fixtures. Live requests are blocked here; public redistribution remains disabled pending source permission.

- 2026-10-15 · Claude: phone tabs are icons only, the tab bar and each section's tabs; the name stays as screen-reader label and long-press title. Guideline C01, C03, C12 text updated in both repos.
  The C03 drawings still show words; redraw them.
- 2026-10-15 · Claude: phone date fields open the calendar on tap with no keyboard, show the calendar button, and the calendar draws as a 7-column grid; `phone.css`, `phone-fields.js`.
- 2026-10-15 · Claude: phone tables show as stacked rows with each column's heading above its value (prices, counterparties, held-for-others, settings); `phone.css`, `phone-fields.js`.
- 2026-10-15 · Claude: phone type is 12px at least, Birdview's category treemap is full-width rows and its usual-month chart two a row, fields 48 and icons 44; `phone.css`, `profiles.css`.
  Tables on seven phone pages stay open in report `phone-c12-type-tables-and-cut-words`.
- 2026-10-15 · Claude: Investments no longer warns "reconciliation differs" when a certificate paid interest: the interest lands on the bank, so the check now subtracts it: `ui/routes/investments.py`; test 16 in `tests/test_audit_numbers.py`. Screen changed: Investments.
- 2026-10-15 · Claude: `tools/stale_check.py` reads only the first clause of a proposal's Status line, so "implementation started … when an item is built" no longer counts as built.
- 2026-10-15 · Claude: phone buttons and fields now follow C05 (48 page, 40 in a card); `phone.css` sets the control-height variables because `.phone .btn` lost to `style.css`'s `:not(#_)` rules.
  The rest of the phone audit is in report `phone-c12-type-tables-and-cut-words`.
- 2026-10-15 · Claude: feedback rows 32 to 76 settled by the owner: built 35 and 50; declined 38 (pie), 54 (one card destination), 60 (S/M/L tags), 62 (price volume), 63 (fall from high), 65 (free emergency target), 73 (review timeout), recorded in Architecture › UI contract; 76 was already built (ticket 88); 32 and 75 stay as reports. The combined request report is deleted.

- 2026-10-15 · Claude: feedback rows 32 to 76 settled by the owner: built 35 and 50; declined 38 (pie), 54 (one card destination), 60 (S/M/L tags), 62 (price volume), 63 (fall from high), 65 (free emergency target), 73 (review timeout), recorded in Architecture › UI contract; 76 was already built (ticket 88); 32 and 75 stay as reports. The combined request report is deleted.

- 2026-10-15 · Claude: trend dots say how much a line moved since its previous point ("+27,560 (+20%) since the last point"), in the tooltip and the screen-reader label: `charts.trend`, `partials/charts.html`; test in `tests/test_charts.py`. Feedback row 50 built.

- 2026-10-15 · Claude: Cash planning's Lowest point card names the first month that ends below your reserves ("Runs short in 2026-12"); the forecast is monthly, so a daily path stays unbuilt: `CashForecast.first_short_month`, `_plan_stats`; test `tests/test_first_shortfall.py`. Feedback row 35 built.

- 2026-10-15 · Claude: Overview 444 to 349 queries, no page over 150 ms or 400 queries: category and effect totals, money held for others, and typed item values read once per request or per item: `reporting/queries.py`, `money_from_others.py`; test in `tests/test_repeated_lookups.py`. Regenerated `style.rtl.css` (the register fix had left it stale). Report `overview-remaining-query-loops` closed; the per-row counterparty match (34 queries on a register) stays as it is.

- 2026-10-15 · Claude: searching a whole number finds the row whose amount the pages show rounded to it (3251 finds 3,250.75); exact cents already worked: `_TERM_SQL` in `lightning/transactions/repository.py`; test in `tests/test_transactions.py`. Report `transactions-search-ignores-amounts` closed (it was partly wrong).

- 2026-10-15 · Claude: the account register and Transactions no longer scroll sideways in a narrow window: the table's scroll box now clips the screen-reader-only links that widened the page (498 px at a 390 px window): `style.css`; test `tests/test_register_fits_narrow_window.py`. Report `accounts-register-overflows-sideways-at-390px` closed.

- 2026-10-15 · Claude: the CSV import review marks a future-dated row to fix at once, as typing it does, instead of failing at Post: `_date` in `lightning/bank_imports.py`; test in `tests/test_bank_imports.py`. Report `import-preview-does-not-flag-future-dates` closed.

- 2026-10-15 · Claude: a budget above 100,000,000 is refused; a blank budget field now says it cleared the limit (it never saved 0; the report was wrong): `MAX_BUDGET` in `budgeting/service.py`, `inline_rule`; test `tests/test_budget_rule_limits.py`. Reports `budget-blank-rule-saves-zero` and `huge-budget-amounts-accepted` closed (150% of income stays allowed: percent rules go to 10,000%).

- 2026-10-15 · Claude: `report/` folder: one file per unprocessed finding in `technical-bug`, `visual-bug`, `technical-improvement`, `visual-improvement`, with who/skills/version in front matter; a generated `INDEX.md`; a fixed report is deleted with its fix; capped at 20 reports and 30 days each (`tools/report_index.py`, `tests/test_reports.py`). All skills now file there; `docs/proposals/open_feedback.md` became one report.

- 2026-10-15 · Claude: fewer repeated reads per page: exchange rates, categories, counterparties and assets are read once per request, and each asset's prices once, not once per month end (Overview 642 to 444 queries, Investments 291 to 181; every page identical): `fx.py`, `reporting/queries.py`, `assets/repository.py`; test `tests/test_repeated_lookups.py`.

- 2026-10-15 · Claude: skills `release-check`, `guideline-audit`, `number-audit`, `perf-check`, `arabic-check`, `website-sync` (all in `skills/`), with `tools/release_check.py` and `tools/perf_check.py`; `AGENTS.md` points to `skills/README.md`.

- 2026-10-15 · Claude: skills `bug-hunt` and `stale-check` with `tools/bug_crawl.py` (crawls every page) and `tools/stale_check.py` (old messages, dead links, built proposals, merged branches, version and guideline drift); two dead OWNER.md links in proposals fixed.

- 2026-10-15 · Claude: skills live in a tool-neutral `skills/` folder (`feedback-review` moved there, neutral model wording); `.claude/skills/` holds one-line stubs so Claude Code finds them.

- 2026-10-15 · Claude: `feedback-review` skill now compiles into one report, investigates in the main session, then uses two agents at most (Opus designs, Sonnet builds) and deletes the reviewed files: `.claude/skills/feedback-review/SKILL.md`.

- 2026-10-15 · Claude: `user feedback/` retired (all three batches processed; 12 still-open requests kept in `docs/proposals/open_feedback.md`); new skill `.claude/skills/feedback-review` for compile, investigate, build, delete.

- 2026-10-15 · Claude: licence added: PolyForm Noncommercial 1.0.0 (`LICENSE`, README section, `CONTRIBUTING.md`, `pyproject.toml`); personal use and changes allowed, commercial use needs the owner.

- 2026-10-15 · Claude: month parsing is memoised (the Overview asked for the same months about 900 times a page): `parse_month` in `lightning/core/dates.py`. Pages already render in 20–100 ms with ten months of data.

- 2026-10-15 · Claude: settings are read once per request instead of about ninety times on the Overview (budget and zakat reads too): `raw_setting` in `lightning/database/settings.py`; test `tests/test_settings_memo.py`.

- 2026-10-15 · Claude: open-source cleanup: `OWNER.md` removed (owner questions go in GitHub issues), its links and checks dropped, `NOW.md` messages older than seven days deleted.

- 2026-10-15 · Claude: "Held 1 day" instead of "Held 1 days" on Investments (PC and phone, Arabic too): templates `investments/index`, `holding`, phone `index`; test in `tests/test_investments.py`.

- 2026-10-15 · Claude: saving a transaction past its budget says "N EGP over this month" instead of "-N EGP left": `_budget_feedback` in `lightning/ui/routes/register.py`; test `tests/test_budget_feedback.py`.

- 2026-10-15 · Claude: whole-number figures round half up everywhere (468.50 read 468 on the Spending comparison and day calendar but 469 elsewhere): `whole` filter, `_compact`, Spending compare and plan chart titles; test `tests/test_half_up_figures.py`.

- 2026-10-14 · Codex: Section 13 milestone 1: optional salary/payday setup, bank CSV presets, full financial Excel/CSV exports, instalment purchase plans and previewed early loan payments in existing screens.
  Migration `0055_loan_actions.sql` preserves short-month paydays, exact instalment totals and linked extra payments/fees; voids restore schedules. Dummy round-trip fixture rebuilt; owner-approved historical loan balances now follow cash receipt dates.
  Validation: financial regression, browser preview/edit/download flows, English/Arabic screens, Mohab, PC brand and phone checks; full suite 1,548 passed, 10 skipped after incorporating latest main.
- 2026-10-14 · Claude: a gold price reference (18K/21K/24K) can no longer be bought or added as a holding; it only supplies a price: `InvestmentService._validate_asset_account`; test in `tests/test_physical_items.py`.
- 2026-10-14 · Claude: a bill or income due date already paid or skipped cannot be recorded again (a second press made a second real payment): `PlanningService.record_payment`, `PlanningRepository.is_settled`; test in `tests/test_planning.py`.
- 2026-10-14 · Codex: tab-by-tab trust batch: plain returns before 365 days, annual XIRR afterward; separate locked-certificate values/dates and matching Sale factors; emergency coverage defaults to spending (income optional).
  Phone Needs you before Latest (C11.1 in both guideline copies); sidebar page-jump; Safe to spend says “on top of your plan”; recurring rows by due date; holding tones by sign; settings spacing and search category labels. English/Arabic checks and regression coverage updated.
  Validation: full suite passed; PC brand audit at 1366 × 768 and phone overflow check at 360/320 passed.
- 2026-10-14 · Claude: batch 003 finished (18 of 18): Investing rate = Money added ÷ Net flow (Saved and invested shows the savings rate only); Financial health leads with Over time, each limit one line that opens; the System group names its categories; the website's feedback form sends in the background.
- 2026-10-14 · Claude: feedback batch 003 built (15 of 18): Your position follows the period end; Free cash beside what it is made of, If you sold today beside Net flow; Sankey splits Invested from Kept and pairs a month with its six; Needs you grouped by kind; month calendar for net cash flow, daily expenses on Spending only.
- 2026-10-14 · Claude: batch 003 fixes: Plan to invest placement, lone key note on one line, styled file field, one row hover, Budget sub-lists (one chevron, Select all in the header), a one-row 30-day timeline, What you owe rows open. Outcome table in the batch file; open questions in `OWNER.md` › 19.
- 2026-10-14 · Claude: user feedback batch 003 (rows 79–96, 18 tickets) compiled for AI investigation in `user feedback/`; its 8 screenshots are copied to `user feedback/screenshots/batch-003/` and linked per ticket.
- 2026-10-14 · Claude: website analytics receiver 2026-10-14.4 rebuilds past Allow-all page views from Events, sets itself up on its first request (Cairo time, formats, key in a *Dashboard key* tab, remembered spreadsheet id) and answers failures in JSON; dashboard compares only with a fully covered earlier period, uses whole Cairo days, and drops guessed section order.
- 2026-10-14 · Claude: phone Categories open as one row per group (12,000px to about one screen; searching opens all); an odd last tile spans the row; Cash planning leads with Safe to spend and drops the two tiles it repeats. Settings' five tabs are an `OWNER.md` question (18).
- 2026-10-14 · Claude: website decision dashboard built (Lightning_website): verdict cards with confidence, key numbers against the previous period, path to a download per device, trends with release markers, channels, fix list, release effect; receiver script 2026-10-14.1 adds `From` and the per-day, per-page fields; Privacy Notice UX-2026.10.14.03. Owner: paste the receiver (OWNER.md).
- 2026-10-14 · Claude: phone fields open empty when tapped (`phone-fields.js`): the old text returns if the field is left empty, a sheet that focuses itself clears nothing. A lone tile spans the row; Data checks and Currencies figures are rows in one surface.
- 2026-10-14 · Claude: phone: Accounts shows the five latest transactions; tile chips sit above their label; zakat day field is a soft well; Arabic Part C updated (guideline 3.31). `tools/phone_check.py` also turns zakat on and adds a gam'eya.
- 2026-10-14 · Claude: phone key notes (Budget's "Categories over plan", Health, Cash) are white rows with a tone dot, not tinted cards with a big numeral (C01.1).
- 2026-10-14 · Claude: zakat is off by default; Settings › Your data › Zakat › *Show zakat* turns on its tab, page, search entry, Cash planning line and the worn box on gold pieces.
- 2026-10-14 · Claude: zakat: Accounts › Zakat estimates 2.5% above 85 g of 24K gold from your position (zakat day, Paid in the new Zakat category, Still to pay), a dated line in Cash planning, a worn flag on gold pieces; migration `0054_zakat.sql`; gam'eya counted in (paid in; instalments due now taken off with debts). Round-trip fixture rebuilt for schema 54.
- 2026-10-14 · Claude: gam'eya (savings circle) on the CD backbone: account type `GAMEYA`, terms and forecast (instalments, payout, optional interest) in `deposits/gameya.py`, figures **Gam'eya paid in** and **Gam'eya still to pay**, circle page on PC and phone. Net worth never moves with an instalment or the payout.
  Migration `0053_gameya.sql` adds `gameya_terms` and rebuilds `accounts` for the new type; roundtrip fixture rebuilt for schema 53.
- 2026-10-14 · Claude: phone tiles on Health, Cash planning and Investments lose their coloured edge, icon box and gradient (C01.1, quiet chrome).
- 2026-10-14 · Claude: phone redesign, money first (guideline 3.31): flat transaction list with a round initial and no balance except on an account; Overview leads with net worth and the latest transactions, analysis after; Expense analysis headline figures as a lead and rows; one Secondary on an account. Arabic copy of Part C still to follow.
- 2026-10-14 · Claude: owner chose fingerprint unlock (Android, optional), gam'eya (CD backbone, interest optional) and zakat; designs in `docs/proposals/gameya.md`, `zakat.md` and `multiple_devices.md` 18d.
- 2026-10-14 · Claude: proposal `docs/proposals/website_decision_dashboard.md`: a decision dashboard for the website (verdicts with confidence, trends, the path to a download, fix list, release effect); hand-off in `NOW.md`. Website repo: analytics tests committed.
- 2026-10-14 · Claude: website dashboard (website repo): page-view records are the single main source (GoatCounter only cross-checks); the Downloads page name is one constant in the receiver script, noted in the README.
- 2026-10-14 · Claude: website analytics, full structure (website repo): every page view sends an anonymous record (what was on screen or pressed, scroll, errors) even if GoatCounter is blocked; live findability, hesitation, error and speed views; GitHub download counts beside button clicks; Privacy Notice Version 2. Setup order in `OWNER.md`.
- 2026-10-14 · Claude: website footer (website repo): a Contact Us section (two emails, Reddit, Discord), then brand and links, on every page in English and Arabic; generated from `tools/footer.py`.
- 2026-10-14 · Claude: website analytics: every number is behind the dashboard key (website repo): GoatCounter totals go from the GitHub job to the private receiver, no analytics files are committed. Setup order in `OWNER.md`.
- 2026-10-14 · Claude: website analytics hardening (website repo): linked visits are no longer published (dashboard loads them privately with a key); Apps Script abuse caps and small-group merging; notice says storage works like a cookie. Owner steps in `OWNER.md`.
- 2026-10-14 · Claude: website Events sheet (Apps Script, website repo): "Received at" shows date and time; each visitor ID gets a sequential Visitor no. (Visitors tab, backfilled, purged after 90 days).
- 2026-10-14 · Claude: proposal `docs/proposals/tab_by_tab_review.md`: every section and tab walked on PC and phone with the sample household; 15 ranked fixes, about 150 items by tab, nine owner choices (OWNER 19), suggested order and Mohab steps.
- 2026-10-14 · Claude: optional fingerprint unlock on the phone (task 18d): an opt-in Keystore-bound key slot outside the profile (`keys.json` and the PC unchanged), unlocked through BiometricPrompt then the password's own open path; Settings › This phone and a Use fingerprint button on the unlock screen.
  Cancel counts nothing; changed fingerprints or a key that is not the profile's remove the slot and say to use the password. Java compiled against API 30 stubs only; on-device check in `OWNER.md`.
- 2026-10-13 · Codex: Project Overview sections and nested screen questions now use tiered numbers for clear handoffs; contents table matches.
- 2026-10-13 · Claude: website analytics in two tiers (website repo): a consent bar (Keep essential only / Allow all), a Privacy Notice in EN and AR, release-tagged GoatCounter events (`events.csv`) and opt-in linked visits through Apps Script (`journeys.csv`, 90-day purge). Setup in `OWNER.md`.
- 2026-10-13 · Codex: v1.1.0-beta.1 published as a matched Windows ZIP and signed Android APK; public checksums match the tested pair.
  Website downloads, release notes, archives and feedback choices updated in English and Arabic; v1.1 acceptance items cleared from NOW.md, larger features deferred.
- 2026-10-12 · Claude: `docs/COMPETITION.md` tests the owner's eight selling points against the evidence and the code (verdict, safe wording, top three); the Lightning row of the field table is current; owner questions in `OWNER.md` 13.
- 2026-10-12 · Claude: website pages made concise (website repo): Home has one phone-and-PC section, four helpers and four FAQs; Features puts phone and PC second and drops group intros; Current Status merges first run and feedback; every changed page has a new release ID and archive.
- 2026-10-12 · Claude: guideline 3.30: B06 gains Buttons (vivid, primary, secondary; heights 48/40/36) and "the signup band is the only gradient call-out"; its specimen now matches the live band. Website: one top bar and footer, one Arabic band wording, survey on the landing system (see the website repo).
- 2026-10-12 · Claude: guideline 3.29: Muted is `#566E7E` (4.5:1 on the canvas and tints) in the guideline and the six app stylesheets; B01 CTA, radius and rounding notes; website audit fixes live in the website repo.
- 2026-10-12 · Claude: guideline 3.28 after an audit: A02.2 files, A03.3 measured contrast and the link rule, A06.2 Arabic in English, B11 social and brand surfaces (Before it ships is now B12), `guideline/brand-voice.md`; A09 no longer shows "Monthly"; A05's phone paragraph points to C04. Copies kept identical in both repos.
- 2026-10-12 · Claude: `docs/proposals/temp-better-features.md` split into one file per design (undo, import matching, month lock, merge, investment events/lots/splits/checks/returns, price source order); built sections were already in Architecture.
- 2026-10-12 · Claude: Migrations 0051–0052 no longer collide on `EXP.SYSTEM.ADJUSTMENT` when a newer seed has it; screen tests name an icon button by its tooltip (the register Add button); roundtrip fixture rebuilt for schema 52 (`508597be…`). Suite: 145 failing → 13 (register/overview redesign tests, left for their author).
- 2026-10-12 · Claude: `AGENTS.md` points to `tools/claims.py` before pushing and to `CHANGELOG-archive.md` in the skip list.
- 2026-10-12 · Claude: workflow tooling: UI reads currencies through the container (import contract passes again); `tools/claims.py` warns on files claimed in `NOW.md`; older releases moved to `CHANGELOG-archive.md`; NOW.md tests reject expired messages to all.
  Logs migrations `0050_cash_at_hand.sql`, `0051_adjustment_category.sql`, `0052_system_categories.sql`, missing here.
- 2026-10-12 · Claude: `AGENTS.md` keeps every rule in 6.3 KB instead of 10.2 KB (cheaper start for every session); `CLAUDE.md` now only imports it.
- 2026-10-12 · Claude: Arabic layout now mirrors on every PC and phone screen: `style.rtl.css`, `phone.rtl.css` and `profiles.rtl.css` (built by `tools/build_rtl_css.js`, charts left as drawn) replace the English files in Arabic only; chevrons and written arrows point the way the eye moves, dates read `٢٠٢٦-١٠-١٢` left to right (they were flipping to `١٢-١٠-٢٠٢٦`), the phone period bar fits, paths and the AI prompt stay left to right, the timeline keeps its axis.
  Arabic text: periods say «لحد», `As of`/`x of y`/asset-class names in Settings/low-confidence and compare lines/forms and titles are Arabic, period words follow C04 (من بداية السنة، مخصص); `tests/test_arabic_no_english.py` now also covers period variants, settings sections, forms and detail pages, and two-letter English words.
- 2026-10-12 · Claude: the Arabic UI has no English system text on any PC or phone screen: an Arabic last pass over each page (`localize_html`) and ~1,500 new entries (system categories, asset kinds, currencies, months, sentences, errors) in `ui/i18n_system.py`, the glossary's Egyptian terms.
  Test: `tests/test_arabic_no_english.py`.

## [1.1.0b1] — 2026-10-13 — Windows and Android beta

- 2026-10-13 · Codex: v1.1 beta acceptance: conversion previews use the posting parser (invalid amounts stay blank; Arabic digits work), foreign-stock requirements are translated and use the dated FX lookup, Mohab’s dollar brokerage participates in cross-tab reconciliation, and EGP bank SMS cannot be assigned to foreign accounts.
  Validation: 1,447 passed, 10 skipped; four import contracts, encrypted profile self-check, PC brand and 320/360px phone layout checks passed.

- 2026-10-13 · Codex: Batch 002 audit (42 rows): short-period XIRR, partial-allocation warnings, fresh reserve summaries, bounded help tips, setup dismissal, correct sale-estimate hierarchy/phone values, and aligned phone arrows.
  Remaining requests and evidence: `user feedback/user-feedback-batch-002.md`. Full suite: 1,381 passed, 9 skipped; post-v1.1 checks: 208 passed; documentation checks rerun after the concurrent cleanup.

- 2026-10-13 · Claude: docs made lean and dated: Overview 68→26 KB, Architecture 116→65, Glossary 78→43, Competition 53→28; planned designs moved to `docs/proposals/` (search_matching, stored_figures); 1.0.0b1 entries moved to `CHANGELOG-archive.md`; `OWNER.md` dated.
- 2026-10-13 · Claude: v1.1 merged (brand, US stocks, FX, Arabic); Investments shows a foreign holding's gain with its Price part and FX part under it.
- 2026-10-13 · Claude: Arabic in the app: Settings › Language also sets the profile pages' language; month grid keeps time left to right with month numbers, not J F M; YTD reads `2026-01-01 to today` (A06.1); list keynotes and the phone category count translated; RTL CSS regenerated.
- 2026-10-13 · Claude: v1.1 US stocks: an investment is priced in its exchange's currency (USD for Nasdaq, NYSE, Arca; registered on creation); picker lists about 400 US stocks and 70 ETFs with their exchange; buys, sells, dividends and holdings post at the day's rate and refuse an account in another currency. The 2026 sample and Mohab get a dollar brokerage with a Nasdaq ETF.
- 2026-10-13 · Claude: v1.1 phone and Arabic pass: phone day headers and quiet links Ink; the hidden calendar button no longer squeezes dates in the register (English and Arabic); RTL CSS regenerated. `phone_check` is clean.
- 2026-10-13 · Claude: v1.1 brand pass (PC and phone): links Ink and underlined, register spending Ink and the table fits its card at 1440 px, off-palette text and H3 to A03, soft-well fields, profile and welcome currency are type-and-pick, one palette in `style.css`, no dark-mode gradients. New `tests/test_brand_audit.py` (browser) guards it.
- 2026-10-13 · Claude: v1.1 FX (package B), rates and conversion: one rate lookup (`fx.py`: direct, inverse, cross through EGP; MANUAL > TRADE > MARKET > ONLINE; "as of" after 10 days, missing after 45) filled from the `fx` price file and Yahoo `<CCY>EGP=X`. *Convert* (`CNV`) between two currencies with the executed rate, a fee in Fees & Charges, spread against the market rate, edit and delete; the transfer refusal now points to it.
- 2026-10-13 · Claude: v1.1 FX positions: the Currencies tab shows per currency what you hold, its value, Average rate, Unrealized and Realized FX gain, Spread paid and a value-against-cost chart (`reporting/fx_positions.py`; unrealized + realized = the revaluation journals + the change since, tested). Investments report splits a foreign holding's gain into Price part and FX part. Mohab buys dollars in his last step. Glossary and Architecture updated.
- 2026-10-13 · Claude: v1.1 review: brand audit of the post-beta screens, FX gaps (no conversion, typed rates only, no age limit, no FX cost or gains, foreign stocks booked in EGP) and the US-stock plan in `docs/proposals/v1_1_presentable.md`; packages A and B claimed.
- 2026-10-12 · Claude: red suite fixed. Code: income plan items offer ± categories (Internal transfers, Capital allocation, Adjustment); the section tabs show on `/accounts/currencies` and other non-numeric account pages.
  Tests follow the Codex 10-10 UI (spreadsheet register, System Categories, Settings currencies tab, collapsed investments row); the profile test reads the currency through a screen, not the app thread.
- 2026-10-12 · Claude: bank SMS reads are one transaction (staging, seen, cursor); inbox messages are known by text plus time, with a 10-minute overlap; phone hides Add transaction while lent, loads `session.js?v=4`, and the second PC's refusal names the PC.
- 2026-10-12 · Claude: workflow tooling: UI reads currencies through the container (import contract passes again); `tools/claims.py` warns on files claimed in `NOW.md`; older releases moved to `CHANGELOG-archive.md`; NOW.md tests reject expired messages to all.
  Logs migrations `0050_cash_at_hand.sql`, `0051_adjustment_category.sql`, `0052_system_categories.sql`, missing here.
- 2026-10-12 · Claude: Arabic type now follows A06.2: Readex Pro and IBM Plex Sans Arabic bundled (replace Tahoma), taller lines, no letter spacing or italics, charts unmirrored. Signed amounts keep the minus on the left of the digits.`, which is always the first section: `- yyyy-mm-dd · Claude:` or `· Codex:`, then what changed. Take the date from `date`, never a guess.
- 2026-10-12 · Claude: the Arabic guideline follows the English type again: Readex Pro and IBM Plex Sans Arabic at the English sizes and weights, no 600 cap. New A06.2: digits, yyyy-mm-dd dates in `bdo dir="ltr"`, currency, what mirrors. Sides, links, colour names and voice fixed; `tools/guideline.py --ar` reads it.
- 2026-10-12 · Claude: the website's Arabic pages use the English type scale and weights in the Arabic faces (IBM Plex Sans Arabic 700 added), the hero gradient starts green on the right, each hero keeps its lines whole, and full dates read yyyy-mm-dd; the website repo owns the details.
- 2026-10-10 · Codex: stress-audited all four sample stories through monthly cash-flow and spending reports; clarified each welcome-page question so it describes the scenario the ledger actually demonstrates.
- 2026-10-10 · Codex: deepen all four sample ledgers with locally grounded, categorized transactions; Abdelrahman now has CIB naming, varied conservative spending and a June cash-flow shortfall, while other stories show variable invoices, side-deal inventory and Fatma's repair.
- 2026-10-10 · Codex: empty profiles can now load four more fictional Egyptian stories—Amr, Abdelrahman, Menna and Fatma—alongside Mohab. They include irregular income, negative-cash-flow months, overspending and emergency-reserve cases for analysis.
- 2026-10-10 · Codex: the first-account welcome screen now lets a new profile choose its base currency before adding an account, rather than hiding that choice in Settings.
- 2026-10-10 · Codex: profile setup now lets you choose its starting currency, including EGP, USD, EUR, GBP, SAR and AED; the selected currency becomes the profile base before any money is recorded.
- 2026-10-10 · Codex: register edits now save on a click outside their row; aligned Notes with the other fields and tightened the loan popup. Income recurring items show only income categories; System Categories contains loans, held money, internal transfers, capital allocation and Adjustment.
- 2026-10-10 · Codex: add high priority coverage for Nasdaq, leading European and GCC equity markets to Project Overview and NOW.
- 2026-10-10 · Codex: make long register pages keep their edit position, remove the sticky header, add a quiet page-jump control, and keep date, notes and balance columns readable.
- 2026-10-10 · Codex: collapse Overview investments, center the investment-planning action, make expense intensity a day calendar, and retain net cash flow beside it.
- 2026-10-10 · Codex: give Currency settings an Overview-style page title, make full screen a compact Settings icon, and restructure FX rates and reevaluation history as focused sections.
- 2026-10-10 · Codex: rebuild Currency settings around the shared Nile tab bar and quiet currency list; live filtering now runs from the shared app script.
- 2026-10-10 · Codex: fix live currency filtering and restyle the currency tabs, current-currency marker and row actions to match the Nile selected state and quiet list controls.
- 2026-10-10 · Codex: move full screen into Settings and add a dedicated searchable currency page with active currency actions plus FX rates and reevaluation history in a second tab.
- 2026-10-10 · Codex: truncate register notes with a full-text hover tooltip, rebalance column widths and align compact add/save icon actions beside amounts.
- 2026-10-10 · Codex: add Cash at hand as an account type under Liquid Cash, preserving its subtype across edits and upgrades.
- 2026-10-10 · Codex: rebuild the transaction register as aligned spreadsheet columns for date, counterparty, category, notes, amount and balance, including add and edit rows.
- 2026-10-10 · Codex: move loading feedback from the pressed button to an animated, labelled status box in the top right.
- 2026-10-10 · Codex: keep the page header visible as an app top bar and add a working full-screen toggle.
- 2026-10-10 · Codex: sale factor estimates recalculate in place; date fields open the calendar directly and keep the ISO date legible.
- 2026-10-10 · Codex: register labels are clearer, POST saves preserve scroll position, success messages appear as readable top toasts, and negative amounts use rose.
- 2026-10-10 · Codex: compact single key notes on Cash planning and tighten the Sale factors settings table.
- 2026-10-10 · Claude: the 13 Arabic website pages are rebuilt for Egypt (Egyptian copy, order and examples, fewer sections) on the English design system; the website repo owns the details.
- 2026-10-10 · Claude: Arabic guideline type is Readex Pro (headings, figures) and IBM Plex Sans Arabic (text), never heavier than 600; `website-ar.html` B04/B10 now hold the Arabic type and Egyptian voice rules the Arabic website follows.
- 2026-10-10 · Claude: the Arabic guideline (`guideline/*-ar.html`) mirrors the English documents again: removed the unstyled summary over A and C, restored the full translated Part B in place of the separate compass, Alexandria for Arabic, layout flipped right to left. The website's `ar/` pages now mirror the English pages too.
- 2026-10-09 · Luna, for Codex: Arabic PC and phone screens localize visible digits and number separators, including charts and dynamic text; form values and identifiers stay intact. A06/C10 now record the Arabic numeral rule.
- 2026-10-09 · Codex and Luna: rebuilt the 13 Arabic website pages from the Arabic compass, with Egyptian copy, Arabic numerals, responsive layouts and preserved SEO/download links; desktop and mobile browser checks passed.
- 2026-10-09 · Codex and Luna: redesigned the Arabic website compass in `guideline/website-ar.html` with locally hosted Alexandria, Egyptian copy, Arabic numerals and RTL component examples; mirrored it in the website repository.
- 2026-10-09 · Codex: kept Arabic language switching compatible with the content security policy and updated screen tests for the translated shell.
- 2026-10-09 · Codex and Luna: `0049_currency_registry.sql` lets profiles register ISO or custom currencies and select a base before monetary history; foreign cash uses dated FX, keeps native balances, and shows month-end FX revaluation separately.
- 2026-10-09 · Codex and Luna: Currencies tab shows native and profile values; the main register shows profile and native amounts, with manual rate entry in Settings.
- 2026-10-09 · Codex: refreshed the encrypted dummy round-trip fixture for migration 0049 and its currency registry tables.
- 2026-10-09 · Luna, for Codex: completed Egyptian Arabic labels across app and profile screens, including SMS, devices, finance reports and specialist forms; the locked chooser remembers Arabic before unlock.
- 2026-10-09 · Codex and Luna: expanded the Arabic A/B/C guideline prose and specimens while preserving every original section and diagram; enriched the Arabic website guides, release log and homepage FAQ.
- 2026-10-09 · Codex: completed Arabic names for every registered figure and canonical glossary term, and documented the pre-unlock language choice.
- 2026-10-09 · Codex and Luna: added Egyptian Arabic website pages with RTL layout, language links and Arabic search metadata across the public site; the website repo owns page details.
- 2026-10-09 · Luna, for Codex: added a profile language switch, RTL PC/phone shells and Arabic labels for core figures and common app workflows; specialist copy remains to translate.
- 2026-10-09 · Luna, for Codex: expanded the Arabic glossary and added standalone A/B/C guideline HTML with Arabic section guidance and original examples; detailed English source remains in the bilingual guides.
- 2026-10-08 · Codex: the website app-feedback form can attach up to five screenshots per ticket, including paste, and losslessly optimize PNGs; screenshot storage needs the owner to deploy the Apps Script receiver update.
- 2026-10-07 · Codex and Luna: lightningeg.com now links the published 1.0 beta Windows and Android files, checksums and build record; guide and feedback copy matches the available beta.
- 2026-10-07 · Claude: Mohab's 2026 sample plans a yearly English course (7,800, 2026-11-15) and a year-end bonus (50,000, 2026-12-20), so the months ahead differ: 2026-11 −12,486, 2026-12 +45,254, lowest point 165,937 in 2026-11. Overview read budget 605 → 640.
- 2026-10-07 · Codex and Luna: published the tested Windows ZIP and signed Android APK together as [Version 1.0 beta 1](https://github.com/elfekimuhammed/Lightning-downloads/releases/tag/v1.0.0-beta.1), with checksums and a shared build record.
- 2026-10-07 · Codex: the beta phone signer uses the four Android repository secrets already configured; the signed CI build proved the key and its public certificate fingerprint is pinned.
- 2026-10-07 · Codex: a changed FX provider clears the retired provider's failure from the current pack health, so a healthy Banque Misr run can publish.

## [1.0.0b1] — 2026-10-07 — Windows and Android beta

The first paired Windows ZIP and signed Android APK, built from one tested commit. Its 222 entries (2026-10-03 to 2026-10-07) are in [CHANGELOG-archive.md](CHANGELOG-archive.md).
