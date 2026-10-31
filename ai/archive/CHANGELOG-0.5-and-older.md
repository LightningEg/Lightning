# Changelog archive

Released versions moved out of the changelog (now [ai/changelog/](../changelog/)) to keep it cheap to read. Same format; history, not the current specification.

## [1.0.0b1] — 2026-10-07 — Windows and Android beta

- 2026-10-07 · Codex: Version 1.0 beta pairs one tested Windows ZIP and signed Android APK in one permanent release, with shared checksums and build identity. Testers may use sample or real data with an independent backup.
- 2026-10-07 · Luna, for Codex: certificate prices retain principal until manually valued; dated valuations post one noncash value line per certificate and owner.
- 2026-10-07 · Codex: rewrote the planned edit journal around local edits, a stable home and encrypted deltas; specified conflict, replay and recovery rules. Updated decisions, terms and handoff; recorded unrelated baseline test failures. Not built or scheduled (`docs/proposals/edit_journal.md`).
- 2026-10-07 · Codex: FX prices now use Banque Misr's dated transfer-rate midpoint after CBE blocked the collector; source labels, checks and tests updated.
- 2026-10-07 · Luna, for Codex: register rows follow A11; sparse Spending and Plan screens show clearer numbers and spaced timeline labels.
- 2026-10-07 · Claude: owner answered the edit journal's Q1–Q7: move the home with two of three keys, review on the home only, one week for turned-down edits, history kept 30 days, a compatibility table with the home's version deciding; building later (`docs/proposals/edit_journal.md` section 11).
- 2026-10-07 · Claude: build cleanup: the never-shipped LightningProbe is gone (its entry, module, legacy server, spec, packaging and CI steps; the shipped app's checks cover it), about 20 s less per Windows build (measured); `ci_scope.py` rewritten in order with the same decisions; Architecture › Build and release reads as one schedule.
- 2026-10-07 · Claude: owner confirmed the phone keeps the profile key under the Android Keystore; the edit journal's open questions become Q1–Q7, each with a recommendation (`docs/proposals/edit_journal.md` section 11).
- 2026-10-07 · Claude: owner chose a Cloudflare mailbox with Firebase push for sync away from home; the design adds its budget and seven layers of limits against abuse (`docs/proposals/edit_journal.md` section 8).
- 2026-10-07 · Claude: owner decided trust pairing: one strong pairing (code, check digits, the profile password on the PC), then writing rights with no tap or phone unlock (`docs/proposals/edit_journal.md` section 8; Project Overview).
- 2026-10-07 · Claude: owner decided: writing rights from the home or pending edits seen locally, and sync not tied to the same Wi-Fi (Project Overview; `docs/proposals/edit_journal.md` sections 1, 7, 8). The internet channel waits on the owner.
- 2026-10-07 · Claude: proposal `docs/proposals/edit_journal.md`: every paired device writes through an edit journal, the device holding the ledger decides; guarantees, rollout J1–J6 and acceptance cases. Waits on the owner (`OWNER.md` › To decide 11).
- 2026-10-07 · Claude: CI optimisation: the suite runs one worker per core (5 min to about 2 here; Windows' own tests too), and a push that changes only documents since the last full suite runs just the tests that read them; `pytest-xdist` joins the dev and CI locks, no other pin moved.
- 2026-10-07 · Claude: phone and PC hand-overs: a save on a lent phone answers a phone page naming the PC (was bare text); a returned copy going in shows One moment, not the chooser; an open page reloads in place on a hand-over instead of jumping to Profile settings; a taken-back PC copy says Close this copy, not Hand back.
- 2026-10-07 · Claude: `tests/test_two_devices.py` walks a user's PC and phone journey through the screens (move, edit, hand over, forget, take back, locked phone, second PC). Fixed: Take back and Keep this copy on the phone showed an error page (the request cache read the closed ledger).
- 2026-10-07 · Claude: the packaged self-check needs no HTTP client again (Windows builds pass; the phone probe too); the test key lives in its own sign job; the daily run checks the phone when its files changed; the phone's Settings shows the exact build; every workflow pins current Node 24 actions, one commit each.
- 2026-10-07 · Claude: build wiring audit: re-runs replace their own uploads, a push no longer cancels the daily Windows build, phone-only changes no longer rebuild Windows, a manual run says at once what it can make, a pasted key tolerates stray spaces, install README covers first install, updates and SmartScreen; two tests guard shipped imports and PC/phone library versions.
- 2026-10-07 · Claude: a manual run of **PC and phone app** on `main` now gives the matched test builds: the Windows ZIP and the Lightning Test APK of one commit, two seven-day downloads, reusing a ZIP already built for that commit; it waits on the owner's test key (`OWNER.md`). Architecture › Build and release replaces the proposal.
- 2026-10-07 · Claude: the phone app builds only from `requirements/android.lock` (every package one file by hash, natives from release `android-wheels-r37449625570`, no index) as **Lightning Test** (`org.lightning.app.test`, version code = commits); `packaging/phone_build.py` checks each APK; `tools/android_test_key.py` makes the test key. The daily Windows run now finds its last build.
- 2026-10-07 · Claude: the native wheel workflow can publish an earlier run's four arm64 wheels, unchanged and checked, as a permanent prerelease `android-wheels-r<run>` (the artifacts the phone build uses expire on 2027-01-04).
- 2026-10-07 · Claude: the matched PC and phone test builds, rewritten at the owner's request (`docs/proposals/milestone_builds.md`): one manual workflow on `main` that reuses a built Windows ZIP, hash-pinned phone libraries kept as a release, and a stable test key so each APK updates the last; about 4 to 31 CI minutes a run.
- 2026-10-07 · Codex: Reworked the Android page self-check to use standard ASGI transport; added HTTPX2 for Starlette’s supported TestClient while keeping HTTPX for direct client tests.
- 2026-10-07 · Codex: Proposed one matched PC development ZIP and Android test APK for milestone review, with shared build identity, stable test updates and separate public release gates.
- 2026-10-07 · Claude: guideline 3.27 (owner: "fix the guideline"). Part C: a word beside every icon, tabs are words (four as two rows of two), Cash's icon a banknote, the add button on every section, an As-of chip, the Overview in one screen; contradictions removed. Part A: A10.7 Search and Hide amounts; A10.2 without "Monthly".
- 2026-10-07 · Claude: the phone follows 3.27: Overview folds the rest into rows that open in place, word tabs, the + on Overview, Budget, Cash and Investments with 18px corners, As-of chips on Health and Data checks; the PC sidebar's Cash planning icon is the banknote too.
- 2026-10-07 · Claude: UX plan 8 and 9: reserves as two-line rows with a meter, the emergency fund's "left of · used · Refill"; whole EGP on headline totals, no internal codes on Prices, plain words on Data checks, Repeat as a segment.
- 2026-10-06 · Claude: Settings › Rules: when the counterparty, notes, amount, account or direction fit, set a category, add tags or split money out; the most specific rule decides, imports and the register ask it first, and the past changes only when asked, with one undo (`0048_rules.sql`).
- 2026-10-06 · Claude: UX plan 5 and most of 10: one Free cash breakdown, no Overview waterfall, loans once on Plan, Recurring's one share of income, empty Investments sections hidden, dashed forecast key, "Rest of" this month, Azure balances, locked certificates said, no Investment planner header button.
- 2026-10-06 · Claude: due dates that know the Egyptian weekend: a planned item's *On a weekend* (keep, day before, day after) moves a Friday or Saturday payment to Thursday or Sunday; every item keeps its date until you choose (`0047_weekend_move.sql`).
- 2026-10-06 · Claude: online prices: a held fund without its Mubasher number is found by its name, or its Mubasher page is pasted on Edit investment; gold (18K, 21K, 24K references and gold by the gram) is priced as an estimate from the world price and the dollar's rate (`workflows/live_prices.py`).
- 2026-10-06 · Claude: audit leftovers: the old Budget settings page (its tracking-suggestion fields saved to nothing) is gone, errors return to Settings › Budget; a new account says "Shown under Bank Balance" (no ›); account types lose "e.g. THNDR"; the USD refusals no longer say "M4".
- 2026-10-06 · Claude: phone audit. Mohab's year now runs on the phone (`tests/test_mohab_phone.py`); its dead ends are fixed: View CDs, buy and sell, a refund, a first plan, typed budget limits, Delete in the sheet, Select or press and hold for several rows, bills to pay on the Overview, ⋯ for account actions.
- 2026-10-06 · Claude: phone look: Day by day calendars keep seven days across (they had become 31 rows), Categories reflow, Health rows and chart, chips and labels never cut, no FAB over the last row, no file path, whole-EGP big figures (PC too), Needs you and Get set up say their action in words.
- 2026-10-06 · Claude: Competition › Phone flow, words and icons (how the best apps use tabs, words and icons); three guideline questions in OWNER.md. `tests/screens.py` no longer clashes with Python's HTML parser.
- 2026-10-06 · Claude: duplicates flagged: the import review now also flags a row whose date and amount wait in another review of the account; an SMS transfer between your own banks goes to review once as a transfer, its other side kept on From SMS.
- 2026-10-06 · Claude: owner's test: the phone had no way to Devices (pairing). Settings on the phone now opens with *This phone*: Pair a PC, Bank SMS, Profile and lock.
- 2026-10-06 · Claude: the phone reads bank SMS by itself: From SMS explains what is read and asks for `READ_SMS`; Overview and From SMS then read new bank messages (not people's numbers) into review. Share a message from the SMS app to Lightning. Needs you lists SMS waiting for an account or unreadable.
- 2026-10-06 · Claude: test suite 405 s → 246 s: tests lock profile keys at the key file's cheapest Argon2 cost (`tests/conftest.py`; one `real_kdf` test keeps the shipped 128/256 MiB), `tests/screens.py` parses a page only when read, and the migrator splits SQL from `;` to `;` and caches it (every database open is faster).
- 2026-10-06 · Claude: SMS that no bank pattern knows: a general rule reads amount, ending and direction and marks the row *Check this*; money nothing reads stays on From SMS until entered or dismissed. Phone and PC each have their own From SMS layout.
- 2026-10-06 · Claude: milestone 3 starts: bank SMS (`lightning/sms_imports.py`, CIB and NBE in Arabic; samples in `tests/fixtures/bank_sms.json`). From SMS (`/sms`, on Accounts) takes pasted messages, asks once which account an ending is, and sends rows to the bank import's review.
- 2026-10-06 · Claude: deleted the stale `Claude outputs/lightning-update.zip` (owner's call) and the `app.js` handlers for `data-owner-filter`/`data-option-filter`, which no page uses.
- 2026-10-06 · Claude: test audit: removed `test_sync_write_inventory.py` (it checked only its own constants), merged six one-off files into their siblings, renamed task-named files; new tests for sync edge cases, transaction edits, CD certificates and the app guard. `0046_unused_settings.sql` deletes two settings nothing reads (`app_name`, `investment_liquidation_factor`); the code stops writing them; roundtrip fixture rebuilt (schema 46).
- 2026-10-06 · Claude: the Android workflow's `wheel_run` defaults to the run with the sqlcipher3 arm64 wheel (37449625570), so a build started by hand no longer stops at pip.
- 2026-10-06 · Claude: phone designs for Budget (Left in plan with its meter, groups as rows opening their categories), Cash planning (safe to spend as rows, next 30 days as a list, months as rows) and Investments (two tiles, allocation, holdings as rows by class). Charts' *Show the numbers* are rows on a phone.
- 2026-10-06 · Claude: a PC handing back to a phone that no longer knows it (revoked, or its record kept anew) now says to pair again, not "did not answer". `android/README.md` names the current fixture fingerprint.
- 2026-10-06 · Claude: phone layout notes: account rows drop picker hints and repeated names; one title on Add transaction; ‹ month › inside the period row (C04.2); a transfer once in every-account lists; green "Nothing needs you"; tabs never squeeze; Devices in the phone frame.
- 2026-10-06 · Claude: hand-over review fixed (`tests/test_sync_review.py`): a lost lending record opens read only (Keep this copy); restore refused while lent; two-phase move; take back/borrow wait for a copy going in; PC can borrow again after a take back; listener limits per address; space check.
- 2026-10-06 · Claude: brand guideline 3.26 split into three documents in `guideline/` (`app.html` A01–A16, `website.html` B01–B11, `phone.html` C01–C12), each with a note naming the other two; same folder in the website repo. `tools/guideline.py` reads all three (`--dir`); `docs/BRAND_GUIDELINE.html` and `brand-guidelines.html` are gone.
- 2026-10-06 · Claude: tab-by-tab UX audit (Project Overview › UX plan 10). Health redesigned: four KPI cards, every figure on a meter against its limit, trends that draw. Header settings buttons removed (gear only; old `?section=investments` redirects); Settings › Your data lists every tab's settings.
- 2026-10-06 · Claude: fixed squashed icons in page headers (icon buttons and date pickers kept 20px padding) and the Holdings table cut off at 1,366px.
- 2026-10-06 · Claude: owner's phone test: creating a profile failed on Android (hard links refused; `session.publish_new` now renames when the name is free). The recovery key is confirmed with a press, not typed back. Pairing sends the locked key file, so a PC opens a profile with its own password: no second password. A code from the wrong screen says which screen to use.
- 2026-10-06 · Claude: milestone 2 built (daily use on the phone): KPI tiles two by two without sparklines on every page; Architecture › UI contract › The phone; review steps for milestones 1 and 2 in `OWNER.md`.
- 2026-10-06 · Claude: milestone 2, step 4 (task 17): move a PC profile's home to the phone. The phone shows Bring a profile from your PC and a code; the PC's Profile settings › Move to your phone sends it (same password); the PC keeps its old file as a backup and borrows from the phone. `tests/test_move_to_phone.py`.
- 2026-10-06 · Claude: milestone 2, step 3: on the phone an account is its balance, search, a month chip and a list grouped by day (C08, C11.2); the add button opens the entry sheet (C09: Out, In, Transfer; amount first; Save full width); Accounts lists rows and asks which account; profile pages show no folders (C09.6).
- 2026-10-06 · Claude: milestone 2, step 2: the Overview on the phone (C11.1): four KPI tiles two by two, lead then support cards, Free cash and net flow as bars with the name above, where money in went as two bars and rows, the year as twelve month tiles (`templates/phone/`).
- 2026-10-06 · Claude: milestone 2, step 1: on the phone app every page renders in the phone frame (guideline C02–C05): app bar with Search, Hide amounts and Settings; five sections in a tab bar at the bottom; full-width period and tabs; no sideways scroll at 360 or 320 (`tools/phone_check.py`, `tests/test_phone_frame.py`).
- 2026-10-06 · Claude: CI minutes (owner): a push to main runs only the Linux suite; the Windows app builds daily when the app changed, on a tag or by hand (`packaging/ci_scope.py`). AGENTS.md: run Windows or Android builds by hand only when needed.
- 2026-10-06 · Claude: milestone 1 built: the Android app is Lightning itself (`org.lightning.app`) and the phone's home for the ledger; a Windows PC pairs, borrows, edits and hands back over the local network. Architecture › Multiple devices; review steps in `OWNER.md`.
- 2026-10-06 · Claude: devices in the app (`lightning/runtime/devices.py`): the phone's Profile settings › Devices pairs a PC and can take the ledger back; the PC's profile list has From your phone and Connect to your phone; a line under the header says Borrowed from… (Hand back) or Lent to… · read only. Closing the PC hands back or seals. `tests/test_devices_app.py`.
- 2026-10-06 · Claude: 09/10: pairing and the encrypted local link (`lightning/sync/identity.py`, `transport.py`): the phone shows a one-time code and its address; both screens show the same six check digits; TLS 1.3 pinned to the phone's certificate; every request signed by the PC. `tests/test_sync_transport.py` runs the whole cycle over real sockets.
- 2026-10-06 · Claude: 07/08: lend and hand back with real encrypted files (`lightning/sync/service.py`): the phone checkpoints, refuses a stale copy, goes read-only while lent, verifies and promotes the returned copy (or waits for unlock), keeps its copy from before; the PC seals when the phone is away. `tests/test_sync_lend.py`.
- 2026-10-06 · Claude: brand guideline 3.25 in `docs/BRAND_GUIDELINE.html`, the same file as the website's: new Part C · Phone (C01–C12: frame, tab bar, KPIs, charts, lists, sheets). AGENTS.md, README, Project Overview, OWNER.md and `tools/guideline.py` name Part C.
- 2026-10-06 · Claude: 05b: device-local control store per profile (`lightning/sync/control.py`): authority, paired devices and the promotion journal in one file; P4 records the hand-back receipt in the same transaction. `0045_profile_identity.sql` adds the table; round-trip fixture rebuilt.
- 2026-10-06 · Claude: 05a: protocol v1 complete and frozen (`tests/fixtures/sync_v1.json`): pairing, status, prefetch, checkpoint, return status and error messages; home and borrower authority survive restarts as records; take back and revoke (`lightning/sync/state.py`).
- 2026-10-06 · Claude: owner decisions: sync before Google Play; three milestones (connected, daily phone use, bank SMS) reviewed by the owner; the phone gets its own brand guideline (Project Overview).
- 2026-10-06 · Claude: 04c on the owner's phone: the shared pages render and work (profile chooser, unlock, Overview, an account). Owner: the phone needs its own layout (Project Overview). The probe now keeps pages clear of the status bar, navigation bar and keyboard.
- 2026-10-06 · Claude: 04c: the Android probe renders every finance page of the dummy profile, then serves Lightning's own runtime on 127.0.0.1 to a locked-down WebView (no file, foreign-site or debugger access) and reports server guards, owning-thread shutdown and 16 KB alignment (`tests/test_android_probe.py`). Phone run pending.

- 2026-10-06 · Claude: a certificate's interest counts in Net gain and its XIRR: interest from the CD portfolio's bank, paid into a bank or cash account, is that certificate's (`ReportingService.certificate_interest`). Mohab's year: +23,550, not +1,550.
- 2026-10-06 · Claude: the level-1 group "System" is now "Loans & held money" (migration `0044_loans_group_name.sql`; a renamed group keeps its name); samples and the round-trip fixture rebuilt (only its schema lines changed).
- 2026-10-06 · Claude: 04b passed: on the owner's arm64 phone the encrypted round-trip (open, write, close, reopen, recovery key) gives the same figures, row counts and key checks as Linux and Windows (`android/README.md`). 04c is next.
- 2026-10-06 · Claude: an account added as already owned is no longer read as growth: the net worth chart names the month and amount of opening balances, and the Investments line's change since six months ago leaves them out.
- 2026-10-06 · Claude: Looks recurring leaves out everyday spending and investment income, and *Not recurring* hides a suggestion (`PlanningService.suggestions`, `POST /plan/suggestions/{id}/not-recurring`).
- 2026-10-06 · Claude: Mohab review fixes. Budget and Reserves meters say left/over as the two rounded figures read (80 of 68 is 12 over, not 13); budget suggestions are whole EGP; Reserves shows whole EGP like the other Cash planning tabs; Overview Bills due reads 0, not 0.00; Spending's change reads 0%, never +0% or −0%.
- 2026-10-06 · Claude: 04b: `lightning/runtime/roundtrip.py` opens a committed encrypted dummy profile (`tests/fixtures/roundtrip`), writes, reopens and recovers its key; Linux, Windows CI and the Android probe must give the same report (`expected.json`). Phone run pending.
- 2026-10-06 · Claude: 04a passed: on the owner's arm64 phone, Python 3.13 loads cryptography 50 (Argon2id, AES-GCM), SQLCipher 4.12.0, cffi, pydantic-core, fastapi, jinja2 and uvicorn from our own Android wheels (`android/README.md`).
- 2026-10-06 · Claude: 04a: the four native wheels (cryptography 50, sqlcipher3 0.6.2, cffi 2.0, pydantic-core) now build for Android arm64 and the probe APK builds with them; a real-phone launch remains (`android/README.md`).
- 2026-10-06 · Claude: brand guideline 3.24 (owner): the tab bar with its gear replaces the tab header; an icon stands alone when its tooltip names it; row actions are icons; one choice, one field; A16 adds "A line that repeats its label". Website copy updated with it.
- 2026-10-06 · Claude: the two-level layout is built: its rules moved to Architecture › UI contract (*Two levels*) and the proposal is deleted.
- 2026-10-06 · Claude: icons for row actions: Reserves' Complete and deleted transactions' Restore are icon buttons with their names as tooltips; a reserve's payments open in the dialog over Reserves. A holding stays a full page inside the Holdings tab (its page does not fit the dialog).
- 2026-10-06 · Claude: one choice, one field: Reserves' Match by is a segment and only its field shows (all three showed before: a CSS rule beat `hidden`). Defaults for settings: tracking suggestions at 20% of income (the shown 20% never applied unless saved once), carryover from the month you turn it on.
- 2026-10-06 · Claude: fewer words (owner: "if it's intuitive, we don't need to describe it"): slogans under page titles and lines that restate a label or a sort order are gone; figure definitions, first-run help and field instructions stay.
- 2026-10-06 · Claude: Holdings table (owner): one column each for units, average cost, price, cost, value, share, gain, return and XIRR (account only when there are several); no lines or fold-outs under names. Fixed a stray CSS line from the layout change that drew the Plan timeline over the page.
- 2026-10-06 · Claude: two levels (owner): six sections (Overview: Summary, Spending, Health; Budget; Cash planning; Investments: Holdings, Planner, Prices; Accounts: Accounts, Transactions, Held for others; Settings: Your data, Categories, Counterparties, Data checks); each tab's settings behind its gear; no tab descriptions (`ui/sections.py`, `tests/test_two_levels.py`).
- 2026-10-06 · Claude: proposal `docs/proposals/two_level_layout.md` (owner request): two levels only, six sections and five tabs at most, each tab's settings behind its gear, icons for row actions, one choice one field; where Expense analysis, Financial health, Held for others and FX go. Not built; OWNER.md item 13.
- 2026-10-06 · Claude: Working, not stuck (guideline A10.6, owner's choice): a pressed button becomes unavailable and shows a small Muted turning square; slow pages and the background month-end fetch show it in a note at the bottom right (`app.js`, `/investments/prices/online/status`).
- 2026-10-06 · Claude: Financial health says a month with far more out than in in words, as the Overview does ("21,582 more went out than the 1,833 that came in", still below your limit), in the card and the six-month table, instead of −1177.2% (`CashFlow.rate_says_nothing`).
- 2026-10-06 · Claude: Mohab meets the smarter plan (steps 20, 22, 24, 29–31): the raise offer, loans and rent planned below their bills, Safe to spend's rest of target, a late laptop goal, moving room to Food. Fixed what he found: "move 0", a −1,177% short month, a move offer that stayed, editing a reserve crashed.
- 2026-10-06 · Claude: Online prices never in the way: the month-end fetch on opening runs in the background and the next page saves it and says so; Get prices on missing month-ends, Use shared prices after two failed tries; Settings › Price files › Test price sources (`tests/test_live_prices.py`).
- 2026-10-06 · Codex: Documented promotion's unverified power-loss risk, the ordinary Windows drill, and the explicit real-data release decision.
- 2026-10-06 · Codex: Added 02d process-kill drills at every durable promotion phase and POSIX full-disk/flush fault tests; recorded the remaining physical reboot evidence separately.
- 2026-10-06 · Codex: Fixed nine Mohab checks: dividend amounts, emergency-target warning, today position snapshot, long-period monthly spending, category sign key, persistent investing goal, total fund valuation, dated Other asset values, and multiple CSV selection.
- 2026-10-05 · Claude: the smarter plan, all of it (owner): Safe to spend keeps back the rest of the savings target; Needs you names a goal the plan cannot reach in time (and when it can), a raise in Recurring (plan with it, save it, or keep the average), a month that saved less than the target, and a category over plan two months running with a one-step move of room (`tests/test_connected_plan.py`).
- 2026-10-05 · Claude: A counterparty's usual category is now a habit (3 of its last 5 in 180 days, or all of 2–4), so one odd filing no longer pre-fills or files later payments; proposal 1.1 built, 1.4 left to the owner.
- 2026-10-05 · Claude: more of the plan connected (owner: "make things smart"): Safe to spend and the forecast keep back the emergency top-up; Recurring income stands in for Average monthly income until a month has income; saving the savings target or a goal states the new Most you can plan; Needs you names a category planned below its bills (`tests/test_connected_plan.py`).
- 2026-10-05 · Claude: Added the temporary proposal `docs/proposals/temp-better-features.md`: how to build lots, bonus shares, an event table and checks (from GnuCash) and rules, undo, import match, weekend dates and arithmetic (from Actual) in our code.
- 2026-10-05 · Claude: Each app fetches its own prices (`workflows/live_prices.py`, source `ONLINE`): by itself on the first open after a month ends, for missing month-end closes; anything on Update prices. The shared price files become the opt-in backup (Download shared prices). Adapters moved to `lightning/market/sources/`.
- 2026-10-05 · Claude: The price data repository is `Lightning_Market_Data` (the owner's name): the collector publishes there and the app downloads from it.
- 2026-10-05 · Claude: Price data rights (owner decision): only packs whose source allows republishing are published and shipped (today CBE exchange rates); every pack cites its source in its files and on the price pages; the others are collected only to check sources (`tests/test_market_prices.py`).
- 2026-10-05 · Claude: CI fix: Codex's other-asset valuations above add migration `0043_other_asset_valuations.sql`; the 0042 upgrade test no longer assumes it is the newest migration (`tests/test_connected_plan.py`).
- 2026-10-05 · Claude: Price files, phase 2: the release ZIP carries the default packs (`market.zip`; a tagged release needs them); prices fill by themselves on first run, a newer file, each new month and after a brokerage statement import; Needs you lists missing month-ends; the per-user Yahoo fetch is removed (`tests/test_market_prices.py`).
- 2026-10-05 · Claude: scheduled price collector (`.github/workflows/market-data.yml`): one run per market close, the collector's tests first, publishing to the open data repository only after the owner turns it on; a source failing twice in a row opens an issue (`tools/market/alarm.py`).
- 2026-10-05 · Claude: price packs (owner request): Egyptian stocks, Egyptian funds, exchange rates, US, Gulf and European stocks, each its own folder, schedule and whitelist, listed in `index.json`; Settings › Price files chooses which to download and keep; the collector adds Gulf and European boards (`market/packs.py`, `tests/test_market_prices.py`, `tests/test_market_collector.py`).
- 2026-10-05 · Claude: more of the plan connected (owner said all four): bills and subscriptions plan their budget category like loans; an emergency fund under six months adds a top-up (its gap over two years) to what a month must leave; Fill this month stops at Most you can plan; saving a bill or loan says where Fixed costs and Loan payments to income stand against your limits.
- 2026-10-05 · Claude: the plan's parts talk to each other (owner request): a month's budget must leave your savings target (Financial health) and what dated goals need. Budget, Needs you and Financial health's new Planned savings rate say how much to cut; Reserves shows each goal's monthly need. The separate spending ceiling is gone (`0042_savings_target_from_ceiling.sql` keeps a custom one as the savings target).
- 2026-10-05 · Claude: brand guideline 3.23 (from the website): a Features link in the top bar and a features.html page, with a new B06 Feature list block. Part A is unchanged. Website: ten groups, 79 features, one bullet each, no screens.
- 2026-10-05 · Claude: Investment prices has a Price file card: Fill my prices (every month-end held and the latest close, typed prices still win), Update prices (downloads only changed files, checked before any is kept) and Import a market.zip; a 40 MB upload limit for it in the desktop window (`workflows/market_prices.py`, `market/update.py`, `tests/test_market_prices.py`).
- 2026-10-05 · Codex: Transferred promotion/recovery to Luna first; Android feasibility and sync protocol are queued in order in `NOW.md`, with package exit evidence and closeout checks.
- 2026-10-05 · Claude: financial assets say where they trade: exchange as an ISO 10383 MIC (shown as EGX, Nasdaq, NYSE), ISO 3166 country and a checked ISIN (migration `0041_asset_venue.sql`); a Financial assets page lists them and the form edits name, ticker, ISIN, exchange, type and shown (`tests/test_market_assets.py`).
- 2026-10-05 · Claude: price collector (`tools/market/`, runs in CI, never in the app): adapters for TradingView (EGX, US), Mubasher funds and fund history, CBE rates and Yahoo history (put back to traded prices after splits); checks for size, jumps and source agreement; append-only merge and `health.json` (`tests/test_market_collector.py`, recorded-format samples).
- 2026-10-05 · Claude: the market file format (`lightning/market/`): instruments with ISO names (ISIN, MIC, ISO 4217, ISO 3166), daily and month-end closes, a manifest of checksums that reading enforces, and a packed zip for releases (`tests/test_market_file.py`; design in `docs/proposals/market_data.md`).
- 2026-10-05 · Codex: Added read-only Financial health with profile limits, the shared Reserves target, dated figures and six completed-month trends; added its Settings controls, architecture and glossary contract.
- 2026-10-05 · Claude: Ctrl-K command bar (also Search in the sidebar): one ranked search for pages, actions, records, refs and #tags, grouped by type; privacy mode (the eye beside Search) blurs every amount, remembered in the profile. Static file versions raised (`search.py`, `app.js`; `tests/test_entry_helpers.py`, Mohab's search).
- 2026-10-05 · Claude: #tags in notes (#eid, #عيد): a note shows them as links to every tagged transaction, headed with their count, Money in and Money out; a register search of `#eid` is the same exact filter (`transactions/tags.py`, `tests/test_tags.py`, Mohab's Eid).
- 2026-10-05 · Codex: Added Budget fill review for prior-month base limits and scheduled Bills/Subscriptions, with reserve goals kept separate and selected edits saved for one month atomically.
- 2026-10-05 · Codex: Defined Budget fill proposal rules in Architecture: month-only base limits, scheduled Bills/Subscriptions, separate reserve goals, and explicit existing-limit/parent-ceiling conflicts.
- 2026-10-05 · Claude: Project Overview › *Compared with the best budgeting apps* now names the Egyptian apps and links Competition; rows 1, 2, 3, 6 and 11 point to the Upcoming projects that answer them.
- 2026-10-05 · Claude: added to *Upcoming projects* at the owner's ask: #15 multi-currency and FX revaluation, #16 US stocks, #17 reading PDF and Excel files; the M4 and M7 roadmap rows name them.
- 2026-10-05 · Claude: debt and fixed-cost ratios, each its own KPI card: Debt to net worth, Debt to cash and Loan payments to income lead Cash planning › Loans; Fixed costs to income leads Recurring. Computed in `planning/health.py` with the amounts they divide (six new registry figures); `per_year` moved from the route to `planning.domain` (`tests/test_health_ratios.py`, Mohab on 2026-09-30).
- 2026-10-05 · Claude: leaner hand-off (owner request): `NOW.md` is a *Claimed* table, *Messages* and *Next*, each step with a **Read:** line; no per-AI lanes or "last done". Owner steps and questions moved to the new `OWNER.md`. `tests/test_docs_structure.py` checks this, and that the app's and website's brand guidelines are one file.
- 2026-10-05 · Claude: the emergency fund counts months of income (default) or months of spending, chosen in Settings › Budget; Reserves links to it. New figure Average monthly spending (budget spending without one-offs, same 3 or 6 months); the fund's months and target moved from the route to `BudgetService.emergency_fund` (`tests/test_emergency_basis.py`, Mohab's last month).
- 2026-10-05 · Claude: sums in every amount field: `120+35*2` saves 190; + - * / ^ and brackets, `2(3+5)` multiplies; brackets, then ^, then * /, then + -. Unclear sums (`-2^2`, `2^3^2`, `8/2(2+2)`, a sign too many, an uneven division, a date) are refused with the reason. The window shows the result before Save sends it (`core/money.py`, `/amount-sum`, `app.js`; `tests/test_amount_sums.py`).
- 2026-10-05 · Claude: added *Upcoming projects* to `docs/PROJECT_OVERVIEW.md`: the owner's three asks (return against the risk-free rate, Arabic, financial health ratios) and 11 more from `docs/COMPETITION.md`, each naming the app the idea came from.
- 2026-10-05 · Claude: owner decision: the website never mentions other apps, not even in comparison pages for search (Project Overview › Product decisions).
- 2026-10-05 · Claude: brand guideline 3.21, the same file as the website's `brand-guidelines.html` again (this copy was 3.16). Website only: B01 lists the home page and the Money guides; B02's label examples are sentence case, as A16 says. Part A is unchanged.
- 2026-10-05 · Claude: website search: canonicals, Open Graph card, `sitemap.xml`, `robots.txt`, noindex on internal and archived pages, structured data, the home title and label "Free personal finance for Egypt", and seven Egypt guide pages (website README › Search).
- 2026-10-05 · Claude: added the *Actual Budget code analysis* section to `docs/COMPETITION.md`: ten things Actual's code does better (rules, undo, import match, weekend schedules, budget templates, i18n and more), what not to copy, and where Lightning is ahead.
- 2026-10-05 · Claude: New passwords and recovery (owner decision): any-length password with a suggested four-word one; a 12-digit recovery key typed back at setup; a security question. Key + answer reset the password; an open profile plus the answer or key changes it; wrong tries wait 1 min to 1 hour, never lock. `keys.json` v2 with a copy in `backups/` (`tests/test_profile_keys.py`).
- 2026-10-05 · Claude: Multiple devices, task 06 done: `SessionGate.change_role` switches an open profile between home and reader after the request in flight finishes, with no password and no old form able to save; borrowed profiles get their own folder in local app data, refusing Documents, synced folders, links and hard links (`tests/test_session_roles.py`).
- 2026-10-05 · Claude: Multiple devices, task 06a: a profile can open as a **reader**: a real read-only connection with no backup, migration, seed or payment matching, a refused upgrade, and every finance form answered "read-only copy". Every linked page of the demo opens and leaves the file byte-identical (`tests/test_session_roles.py`).
- 2026-10-05 · Claude: Fixed the routine audit's last seven wrong numbers: Investments now counts deposits and balance-only items in Money added, Flows and start values (a flat recorded this month is no longer growth); horizons cover every item; −0.0% shows as 0.0%; an inactive brokerage account's cash is still yours; one-off spending stays out of carryover; and refunds count in the usual month, the average payment and the money-flow chart (`tests/test_audit_numbers.py`).
- 2026-10-05 · Claude: Fixed three loan and schedule numbers from the routine audit: a partial loan instalment counted as paid in full (7,500 still to pay for 9,000); a skipped payment vanished from a loan set by its last date (now moved to the end, as for counted loans); and "Already paid" added payments to a fixed-count plan (6 became 8). It still moves a 31st-of-the-month schedule to the 30th after a short month: see NOW.md.
- 2026-10-05 · Claude: Fixed five wrong numbers from the routine audit (`tests/test_audit_numbers.py`): your share of a holding shared with someone else showed their share (600 for your 1,400); your cost blended their purchase prices (gain 0 for +500), so each owner now keeps an average-cost pool; the forecast counted every old unmarked payday as this month's income (100,000 for 20,000); it left background estimates out of Left in plan; and it saved again for a goal already funded and partly spent.
- 2026-10-05 · Claude: One review inbox. Needs you now comes from `workflows.review.ReviewInbox`: every statement left in import review (with its waiting rows and the row's own date, not the upload day) and every payment or incoming amount still Unaccounted, beside what it listed before. A register filtered to one category says so and offers Clear.
- 2026-10-05 · Claude: Import review: a statement row you already recorded can be **linked** to that entry (same account and signed amount, within 3 days), with *Post as new* and *Skip* beside it. A link moves no money and leaves the entry unchanged; one row per account per entry (`0040_import_links.sql`). A row whose earlier import was voided is flagged, not posted again. Multiple devices task 20.
- 2026-10-05 · Claude: Fixed: a restore that stopped before its first journal step could still lock the profile for good. A folder the Windows file adapter refuses (OneDrive or another reparse point) is now checked before any record is written, and a protected source copy made just before a failure is removed. Two regressions in `tests/test_profile_session.py`.
- 2026-10-05 · Claude: Fixed: a crash inside a restore's control-store transaction left a hot journal that resume opened read-only, so the profile stayed locked for good. Resume now opens it read-write under the profile lock, which rolls it back (`tests/test_profile_session.py`).
- 2026-10-05 · Codex: GitHub run 37244657944 passed Linux tests, Windows profile and UI tests, packaged-app self-check and WebView2 smoke after the restore process-exit tests landed.
- 2026-10-05 · Codex: Android wheel run 37244107860 reached the native toolchains but neither package built: cryptography still missed target Python headers; SQLCipher's Conan OpenSSL graph needs an explicit compiler profile. Recorded the next build checks.
- 2026-10-05 · Codex: Added Luna's real process-exit restore tests at P1–P4; a fresh process resumes each journaled operation and verifies that all protected encrypted copies retain their hashes.
- 2026-10-05 · Codex: Fixed the Android wheel probe's target-header lookup after GitHub run 37240415999 showed cibuildwheel passes shell globs literally in its environment command; both compiler jobs stopped before testing the native fixes.
- 2026-10-05 · Codex: Added Luna's password-gated forward resume for a single journaled P1–P4 interrupted restore, plus a confirmation screen. Fixed Windows manifest cleanup after write-through replacement and platform-specific P3 tests; CI acceptance pending.
- 2026-10-05 · Codex: Reviewed Luna's durable restore manifest: P0 records bind the source and recovery copies to the promotion journal; unlock checks retained encrypted copies, and Windows uses write-through marker publication. Repair remains a separate acceptance gate.
- 2026-10-05 · Codex: Android native-wheel probe now supplies target Python headers and SQLCipher's Conan Android API level in a disposable source build; results remain to be measured.
- 2026-10-05 · Codex: A replayed original BorrowRequest now rejects once return starts or finishes, so a stale grant cannot be reissued after its lend; added Received and Accepted regressions.
- 2026-10-05 · Codex: Rejected checkout/activation/cancel/return attempts no longer reserve an operation ID in the in-memory sync model; corrected retries can reuse it. Added focused protocol regressions.
- 2026-10-05 · Codex: Claimed Luna's next 03a restore-safety slice after GitHub run 37239350883 passed Linux and Windows package gates: durable operation/source evidence, Windows marker durability, then explicit repair.
- 2026-10-05 · Codex: Made the fake GitHub upload corruption deterministic by flipping a payload bit; the random ZIP's last byte could already be `X`, causing a false CI pass in the release guard test.
- 2026-10-05 · Codex: Fixed restore screen tests to create backups and read encrypted settings on the profile's owning ASGI thread; the first GitHub Linux gate exposed the test-thread mistake.
- 2026-10-05 · Codex: Added Luna's encrypted backup restore backend and a locked-profile chooser/confirmation screen. Successful restores retain both source and prior database; ambiguous operations block unlock. Repair flow and ordinary Windows acceptance remain.
- 2026-10-05 · Codex: Claimed the restore chooser and confirmation UI while Luna builds the locked-profile backend; the screen is not yet available.
- 2026-10-05 · Codex: Promotion now refuses unresolved SQLite WAL, shared-memory and rollback-journal sidecars before preparing or resuming publication, preserving existing files for repair.
- 2026-10-05 · Codex: Claimed the encrypted backup restore backend after the promotion integration reached Windows CI tests; restoration remains in progress and unavailable in the UI.
- 2026-10-05 · Codex: Reviewed Luna's P0–P5 promotion service and SQLite control store, fixed a P3 rollback retry, and added real encrypted-file, process-kill, corrupt-control and lost-reply tests. Windows CI and reboot drills remain.
- 2026-10-05 · Codex: Rejected a delayed borrower cancellation after return reception or acceptance, including when activation acknowledgement was lost; regression tests keep the home read-only.
- 2026-10-05 · Codex: Android source-wheel experiments reached native builds, then failed on missing cross-build Python headers (cryptography) and Conan Android API-level settings (SQLCipher). Recorded the build gates; no APK was produced.
- 2026-10-05 · Codex: Added the first bounded, versioned checkout/return message contract and in-memory single-grant model, with replay, cancellation and receipt tests. It is a protocol foundation only; durable authority and real writer gates remain.
- 2026-10-05 · Codex: Added Luna's Windows promotion file adapter, with fixed-drive and link checks, flushed copies, write-through sibling moves and post-publish hashes. Windows CI passed; journal integration remains.
- 2026-10-05 · Codex: Added the POSIX promotion file adapter with exclusive copy, same-directory replace, file/directory flushes and fail-closed path checks. Injected flush/rename tests pass; journal integration and Windows durability remain.
- 2026-10-05 · Codex: GitHub's Android probe independently found no Android distributions for pinned `sqlcipher3==0.6.2` or `cryptography==50.0.2`; recorded the native-wheel gate. No APK was produced.
- 2026-10-05 · Codex: Added the P0–P5 promotion journal model and restart decisions for database replacement. The model blocks ambiguous files and authority state; filesystem adapters and restore remain to build.
- 2026-10-05 · Codex: Started the multi-device build with Luna: mapped the current writer paths and added a two-node read-only fixture. Added an isolated Android arm64 dependency probe and manual GitHub build workflow; pinned crypto/SQLCipher packaging remains an open gate.
- 2026-10-04 · Claude: brand guideline updated to 3.16 from the website copy. Only B08 (the website calculator) changed, so Part A and the app's CSS are unchanged.
- 2026-10-04 · Claude: Multiple-devices plan, at the owner's request: task 05 split into 05a/05b so the protocol starts before Windows durability finishes; "View saved copy" builds after task 06; a killed-app lend test; a "what you will see" summary in the Project Overview.
- 2026-10-04 · Codex: applied the multi-device follow-up review: dependency-based parallel tracks, task reading guides and smaller steps, early restore/matching releases, offline PC analysis and explicit locked-lend checks. Linked the existing Windows updater decision; recorded fingerprint/interim-PC choices without changing the defaults.
- 2026-10-04 · Claude: Roadmap: in-app updates for Windows (an Update button with signed downloads and rollback), planned for later, at the owner's request.
- 2026-10-04 · Codex: combined the multi-device proposal and Claude's review into one complete cycle design with 24 ordered implementation tasks, durable state/promotion rules, Android and SMS gates, recovery tests and release acceptance; updated its roadmap and handoff. Planning only, no sync implementation.
- 2026-10-04 · Claude: recorded the owner's licence decision in the Project Overview: 7 days free, then a reminder, never a lock; Competition and NOW.md point to it.
- 2026-10-04 · Codex: Revised the multi-device proposal for the owner's phone-home, PC-borrowing workflow, including safe prefetch, locked-phone return verification, offline close, recovery copies and SMS after hand-back. Added the requested supersession note above Claude's preserved review and recorded the product decisions in the Project Overview.
- 2026-10-04 · Claude: added `docs/COMPETITION.md`, the compass: Say, Qershnat, Masarifi, Masareef, Money Manager, Wallet, bank apps, Actual Budget, YNAB, Monarch, Copilot and others, with what their users love and hate (Google Play reviews read directly). Listed in AGENTS.md; the docs-structure test allows it.
- 2026-10-04 · Claude: Multiple-devices review: one name for every device, role, copy, action and state (Review 7), keeping Codex's terms; a PC holding the temporary file is the *borrower*, and the file is its *working copy*.
- 2026-10-04 · Claude: Multiple-devices review: closing the PC with the phone away keeps a sealed copy on the PC; the phone reminds the owner after about 8 hours, then daily, and offers Take back after a few days.
- 2026-10-04 · Claude: Multiple-devices review: the phone app runs in the background only during a lend (one tap starts it, a notification shows it); five further suggestions for Codex (Review 6).
- 2026-10-04 · Claude: Multiple-devices review: the owner opens the phone app when using the PC (no background service); bank SMS formats will be logged bank by bank later.
- 2026-10-04 · Claude: The multiple-devices review records the owner's answers: the PC fetches the phone's copy while the password is typed; it sends a recovery copy every 3 minutes while lent; the phone reads bank SMS once it holds the ledger again; everything stays local.
- 2026-10-04 · Claude: Reviewed the multiple-devices proposal for the owner. The review is appended at the end of `docs/proposals/multiple_devices.md`, clearly marked; the proposal itself is unchanged. Revised the same day after the owner's feedback: the phone lends the database to a PC (one short Wi-Fi exchange, then the PC works alone) and captures bank SMS while it is lent. Measured: a sample profile copies and checks in milliseconds.
- 2026-10-04 · Claude: The docs are cheaper to read. The hand-off moved to `NOW.md` with a lane for each AI and a size limit; `AGENTS.md` adds reading rules, a token-efficiency rule and the A16 checklist; the long docs start with a contents list; `tools/guideline.py` prints one brand guideline section as text (a few hundred tokens instead of about 95,000); the sync proposal moved to `docs/proposals/`; `Unreleased` is first again; `tests/test_docs_structure.py` checks all of this.
- 2026-10-04 · Claude: Brand guideline 3.15, the same file as the website's `brand-guidelines.html`. Website only: phones first (one-line hero sentences, full-width buttons, one-column screens, 54px fields).
- 2026-10-04 · Codex: Renamed the proposed permanent coordinator from authority node to home node; the temporary role remains writer node and read-only copies remain reader nodes.
- 2026-10-04 · Codex: Drafted the multi-device authority, single-writer checkout/check-in protocol and downside audit in `docs/temp_multiple_sync_devices.md`. This is a proposal, with no sync code yet.
- 2026-10-04 · Claude: Fixed: the remembered period kept a month that was "this month" after the calendar moved on. It now moves to the new current month; a past month picked on purpose stays. Test `tests/test_remembered_period.py`.
- 2026-10-04 · Claude: Fixes from an AI review of Mohab's year:
  - *Get set up › Bring in your history* ticked on the CD purchase alone and while the CIB statement still waited for review. It now needs posted income or spending and no statement in review; while one waits, the step says so and links to it.
  - Expense analysis: shares are of Money out (Housing 12,000 of October's 32,701 is 37%, not 35%). A category whose refunds outweigh its spending is its own row in "Show the numbers", with a Money out total, and a line names the refunds, so the rows add up. This closes the known gap.
  - The sidebar's account rows always keep two decimals (guideline A06.1, "rows keep two decimals"). They showed whole pounds on reporting pages and cents elsewhere.
  - Reserves: leftover goal money reads "spent · still set aside" (800.00 for the Sahel trip), not "unpaid remainder"; the status words are Spent in full, Partly spent and Not spent yet.
  - The emergency fund's "Amount set aside" box shows what the fund holds now (13,500 after the 6,500 repair, with a note). Saving it adds back what payments used, so re-saving changes nothing.
  - Units read as written: "75 shares", "1 piece" (new `units_of` filter; the register no longer writes "1 pieces").
- 2026-10-04 · Claude: Brand guideline 3.14, the same file as the website's `brand-guidelines.html`. Website only: white fields (never grey), a dark Take the survey button, a sign-off at the end of each page, and one calculator chip. The app's soft field wells (A10) are unchanged.
- 2026-10-04 · Claude: Brand guideline 3.13, the same file as the website's `brand-guidelines.html`. Website only: the small-change calculator is a split card with its answer on the vivid gradient, the one card allowed there.
- 2026-10-04 · Claude: Brand guideline 3.12, the same file as the website's `brand-guidelines.html`. Website words only: show what Lightning does well and never compare it with other apps.
- 2026-10-04 · Claude: Brand guideline 3.11, the same file as the website's `brand-guidelines.html`. 3.10: the vivid gradient ends on the brand azure #0B6DD6, the logo's own blue, instead of #0066FF; the Investment planner button follows (`--vivid` in `style.css`). 3.11 changes the website only (the small-change calculator shows the capital that pays what you keep; no explanation notes).
- 2026-10-04 · Claude: Guard tests for the figures layer: `tests/test_figures_layer.py` fails if the drawing code or a route reads the ledger directly, or if a money path stops using the one rule.
- 2026-10-04 · Claude: Figures layer: the calculations left in the drawing code moved into services, and every figure on a screen is now in the registry and the Glossary. Expense analysis reads `reporting/spending.py` (new registry figures Per month, Usual month, Usual range); a holding's page reads `investments/journey.py` (Typical move, Fall from its high); 31 pages are byte-identical after the move. Fixed: on Cash planning, the "Due before your next income" card counted overdue bills that Free cash had already taken off, and looked only 30 days ahead, so between jobs it left out bills before the next pay. It now shows the figure Safe to spend uses, under its registry name *Bills and loan payments before next income*; test in `tests/test_planning.py`.
- 2026-10-04 · Claude: One rule for Money in and Money out (`reporting.service.flow_of`), used by every card, month chart, calendar, Expense analysis view and Budget. Fixed: a refund entered as "Money in" on an expense category (possible from the account form) gave three or four different Money out figures across the screens. `cash_flow` added it to spending, the month charts counted it as income, the per-category view ignored it, and only the category breakdown took it off. All paths now agree, the account form records it as a refund, and the month charts' separate query is gone. Test `tests/test_one_money_rule.py` (every path, by day, month and period). Architecture › Figures layer records why there is no stored calculations table yet and when to build one.
- 2026-10-04 · Claude: Brand guideline 3.9, the same file as the website's `brand-guidelines.html`. The website has two landing pages: A · Product (`index.html`, UX-2026.10.04.01) and B · Philosophy (`version-b.html`, UX-2026.10.04.02); B01 lists both and B02 gives each hero its trio (product screens on A; plan, reality and habit on B). Nothing in Part A, the app, changed.
- 2026-10-04 · Claude: Owner decision: Holdings value and Portfolio value are the same figure, and everything that is not cash sits under one roof. Certificates and deposits now count in Holdings value (Mohab: 472,052 → 572,052, the same on the Overview, the Investments tab, its donut and its holdings table). The Overview's separate Deposits row folds into Holdings value. *Investments if sold (estimate)* is retired into *Holdings after sale (estimate)*. Cash left in an older deposit account is reported as a holding. The Investments holdings table now lists assets known only by their balance (a share of a flat), linked to their account, so its total equals Portfolio value; "Money and value by class" counts them at both ends of the period. Glossary regenerated; tests updated.
- 2026-10-04 · Claude: Fixed: Investments › All time started at the oldest latest-price date of what you hold now, not at your first record. After a price update it could say "No money in this period" while the Overview showed every month's income. All time now starts at your first record on every tab; test `tests/test_all_time_same_start.py`.
- 2026-10-04 · Claude: Fixed: a custom range that ends before it starts showed this month on Budget and Investments without saying why; Overview and Expense analysis already explained it. All four tabs now show the same message ("The end month must be the same as or after the start month."); test in `tests/test_budget_period_months.py`.
- 2026-10-04 · Claude: Speed: register pages check reserve suggestions cheaply first. Only a funded reserve whose unpaid amount equals the spending can match, so most rows stop after two reads instead of seven. Account and All transactions pages run about 85 SELECT statements instead of 360 on three years of Mohab. The suggestions are unchanged (`tests/test_reserve_matching.py`).
- 2026-10-04 · Claude: Fixed: the Investments tab's Portfolio value tile and its six-month line counted certificates of deposit, so it read 100,000 more than the Overview's Portfolio value and the allocation donut beside it. It now reads `PositionService.portfolio_value_at` (Holdings value, deposits apart), as the registry says. The never-shown portfolio trend that built the investment report six more times per visit is removed: Investments takes 25 ms instead of 38. Mohab's cross-tab test now compares Portfolio value too.
- 2026-10-04 · Claude: Speed: settled bill payments, planned items, prices, trade prices, gold-item rows, category look-ups by code and active reserves are read once per request, and the register reads every row's owner in one query. SELECT statements per tab fell 35–60% (Overview 824 → 465, Investments 408 → 179, Expense analysis 448 → 174 on three years of Mohab), and the Overview's server time from about 76 to 52 ms. The read ceilings in `tests/test_reporting_performance.py` are tightened to match; pages stay byte-identical with and without the cache.
- 2026-10-04 · Claude: Fixed: when everything was sold in a period, the Investments tab showed only "No holdings yet" and hid the period's gain. It now shows the period tiles and an empty holdings table whenever the period has a result, realized gain or dividends. The Portfolio value tile no longer says "Holdings and brokerage cash" (it is holdings only). Test `tests/test_investments_sold_out.py`.
- 2026-10-04 · Claude: Fixed: Safe to spend took off only this month's budget, even when the next income was weeks away (between jobs, or a payday late in the next month). It now takes off Budget left to spend and Saving for goals for every month until the next income, counting only the days before it in the month it lands (`CashForecaster._safe_to_spend`); test in `tests/test_planning.py`. Bills due on payday itself stay out: that income pays them.
- 2026-10-04 · Claude: Fixed: recording money or an asset you already had (an opening balance or an existing holding) counted as Change in what you own and Change in net worth. All time showed a change larger than net worth itself. Both figures now subtract the new figure *Opening balances in the period* (`ReportingService.opening_balances_between`); test `tests/test_opening_not_a_change.py`.
- 2026-10-04 · Claude: Fixed: on YTD, a year or All time, Budget compared the months with a plan against spending from the whole period. Spent now counts from the first month with a plan, and the page says so ("Planned and spent from …"); test `tests/test_budget_period_months.py`.
- 2026-10-04 · Claude: Mohab's test checks that a figure reads the same on every tab (Overview, Expense analysis, Budget, Investments) for six periods; the savings rate now shows the same precision everywhere, and "—" when spending is more than double income.
- 2026-10-04 · Claude: Owner decision: Portfolio value is holdings only; brokerage cash counts in Cash you own. A balance in an Other or Physical asset account is a holding, never brokerage cash (it used to show as brokerage cash on the Investments tab); test `tests/test_other_asset_figures.py`.
- 2026-10-03 · Codex: Owner release policy: permanently retain at least the three newest app versions as separate immutable downloads; append each version to the website archive without replacing older entries, and do not delete versions without the owner's decision. Current seven-day private Actions artifacts do not satisfy permanent hosting.
- 2026-10-03 · Codex: Add **Export for AI** under Settings › Your data. It prepares one local `.xlsx` workbook for All time, YTD, Monthly or Custom, with Lightning-calculated totals, all owned period ledger lines, investment checkpoints and category hierarchy. The period and record counts update immediately; the editable companion prompt is copied when possible, with a visible copy fallback. User text is stored as spreadsheet text, exports are not capped at 1,000 lines or silently truncated, and Lightning does not upload the workbook. Mohab's screen-driven acceptance flow covers the download.
- 2026-10-03 · Claude: Architecture › Page speed opens with why pages were slow and which fix answered each cause (the speed audit now lives only there), and notes the bundled fonts.
- 2026-10-03 · Claude: The Investment planner button uses guideline 3.8's vivid gradient (`--vivid`: #00995C to #0066FF at 135°).
- 2026-10-03 · Claude: Out-of-date prices are flagged (UX plan item 7, guideline A01 honest numbers). `ReportingService.stale_prices` lists holdings valued from a price more than about two months old (cash, at-cost holdings and certificates are left out). The Overview's Needs you shows "Prices are out of date" with the oldest ones and "Update prices"; a holding page says "out of date, update it" beside its price. Mohab sees it a year on, not on his first evening.
- 2026-10-03 · Claude: Brand guideline 3.8, the owner's file, the same as the website's `brand-guidelines.html`. The vivid gradient is two stops, green #00995C to blue #0066FF (dark #3FE0A3 to #5AA9FF), no teal middle; on the website a breakdown shows EGP once on the big figure with bare numbers in its rows, a count in a money list carries ×, and a section about a count shows every item it counts. The website's Version D follows it (UX-2026.10.03.03). The app's Investment planner button still uses the old gradient (see Now and next).
- 2026-10-03 · Claude: Bulk edit (UX plan item 4, user feedback ticket 20). With rows selected in a register, the selection bar offers "Set a category…" and "Set category" beside Export and Delete. `TransactionService.set_category` changes every selected money-in or money-out row in one save, keeping each row's date, amount, counterparty, notes and owner, and leaves transfers, investment and opening rows, split expenses and rows going the other way as they were (the message says how many). Money held for others and system categories are never set in bulk. Mohab searches CIB Payroll for Talabat and moves every order to Food & Groceries at once (10 known gaps left).
- 2026-10-03 · Claude: Import review asks once per name (UX plan item 2). Rows with the same imported name are one block with one Counterparty, Save as, Category, Moved to or from and Held for choice; each row keeps its date, amount, note and skip as a compact 30px line, and its own category only when the statement gave it a different one. Mohab answers 17 names instead of 43 rows; Mohab's 300-row Vodafone statement renders 287 KB and 1,036 options instead of 2.2 MB and 34,800. "Discard this import" (the app's own dialog) removes a statement still in review; Import CSV shows a waiting review first ("… is waiting for you · Continue the review · Discard it"); "Cancel" is "Finish later". The duplicate error message is gone. Mohab's two import gaps are now checks (11 known gaps left).
- 2026-10-03 · Claude: The account register and All transactions read only the 50 rows shown. SQL counts the rows and sums the older movement for the running balance, so a page deep in five years of history costs the same as the first. On a 2,239-transaction encrypted profile the register takes 37 ms instead of 80 ms and All transactions 39 ms instead of 73 ms. Rows now break ties by account, so the two rows of a transfer keep one order across pages. A test checks every page and running balance against the full register.
- 2026-10-03 · Claude: The app uses the guideline's own fonts and logo (A02, A06). Bricolage Grotesque and Manrope are bundled in `lightning/ui/static/fonts/` (latin and latin-ext, SIL OFL), so the PC app no longer falls back to Inter and Plus Jakarta Sans, and browser mode no longer waits on Google Fonts. The two-leaf mark (`lightning/ui/static/lightning-mark.svg`, from the website's `assets/brand/`) replaces the ribbon in the sidebar, the favicon and the profile screen; `lightning.ico` is rebuilt from the two-leaf app icon (16–256px). The old `lightning-logo.png` is removed.
- 2026-10-03 · Claude: First run (UX plan item 1). The Overview shows a "Get set up" card until five steps are done (accounts, history, salary and bills, an emergency fund, a budget); each step is read from the data, ticks itself and links to its page, and the card disappears when all are done. The welcome lists Bank account, Cash, Certificates, Brokerage and Gold and other things with Lucide icons instead of text symbols. A new bank account's next step is "Import a statement" (primary) or "Add a transaction". With no income planned, Cash planning shows "Add your salary and bills to see where your cash is heading" instead of a forecast built from nothing, and the Lowest point card waits for it. Mohab now checks the setup card halfway through his first evening (2 of 5 done) and that it is gone by October.
- 2026-10-03 · Claude: Owner decision: SQLCipher no longer wipes freed memory (`cipher_memory_security = OFF`). Encrypted ledger reads are about 3× faster: on a 2,239-transaction encrypted profile the account register takes 80 ms instead of 239 ms, All transactions 73 ms instead of 305 ms, and the Overview 139 ms instead of 237 ms. The key is still wiped; Architecture's threat model records what freed memory may hold. `tests/test_encrypted_database.py` checks it stays off.
- 2026-10-03 · Claude: Category pickers follow guideline 3.6 (A10.3, A11). The import review starts each unanswered row on an empty "Choose a category" (Uncategorized stays a choice; posting is unchanged). Clicking a picker lists every choice under its L1 as a bold header, never "L1 › L2", and selects the current text so typing replaces it; typing filters by group and name ("transp" shows Transportation under Personal and Work). The register's picker no longer filters by the row's own category. Mohab's two picker gaps are now checks (13 known gaps left). The Planned and Left in plan definitions moved into the figure registry (`lightning/core/figures.py`), which generates the Glossary; the previous hand edit had failed `tests/test_figures.py`.
- 2026-10-03 · Claude: Faster pages. Each request now computes a repeated figure once (`lightning/core/memo.py`, wired in `ui/web.py`): holdings, net worth, custody, money out by category, the position, the investment report and the category, asset and account look-ups. Any write, and any open transaction, bypasses or empties it, and nothing outlasts the request, so no figure can be stale. On a 2,239-transaction ledger, Budget › All time drops from 4.6 s to 0.33 s (7.0 s to 0.41 s encrypted), the Overview from 0.51 s to 0.16 s (0.96 s to 0.24 s encrypted) and Expense analysis › All time from 0.46 s to 0.30 s, with identical pages. The PC window now keeps `/static/` files for the session instead of re-fetching them on every click, and the logo is 5.8 KB instead of 513 KB. `tests/test_reporting_performance.py` caps SELECT statements per main tab and checks the pages match with the cache off.
- 2026-10-03 · Claude: Brand guideline 3.7, Part B (website) only, at the owner's request: hero and section headers centred, a short label above each section, and the hero's punch line in the gradient. Part A is unchanged. On lightningeg.com the two-leaf mark replaces the old ribbon mark everywhere, and Version D (`version-d.html`) is the landing page built from the guideline; the audit is in the website repository under `audit/`.
- 2026-10-03 · Claude: Owner decisions. (1) Budget's background estimates count in Left in plan, and a small "!" says when one is low confidence and why ("Includes 14,200 for Travel: an estimate from one month of spending…"). The month's plan comes from one service method, `BudgetService.plan_summary`, so the Overview and Budget now show the same figure (Mohab's September: 11,853 left of 38,898, where the Overview said −2,317 of 24,698). (2) The Overview's Investments section is one row (Portfolio value, Holdings value, Money added, Net gain or loss) with "See investments"; its donut, class bars and movers are gone, and the page no longer computes them.
- 2026-10-03 · Claude: `AGENTS.md` makes the brand guideline strict for every visual: check A16 before pushing, the guideline wins over CSS, and nothing outside it is invented.
- 2026-10-03 · Claude: `AGENTS.md` rewritten as the one set of instructions for every AI: which files carry the project and when to update each, the six steps of every task (pull, claim, small pushes, test with Mohab, write it down, hand off), what to do when a push is rejected, product rules and the git rule. `CLAUDE.md` points to it. The owner's decisions on budget estimates and the Overview's Investments section are recorded in the Project Overview.
- 2026-10-03 · Claude: UX batch 1 against Brand guideline 3.6 (ranked plan for the rest in Project Overview › UX plan). KPI cards are coloured by meaning (`surface-in|hold|out|over`) with an icon tile, and the label sits under the icon and chip; Needs you says "Personal over plan" and "Sahel trip is past its date"; the plan card reads "Over plan · 2,317" instead of "Left in plan −2,317"; a savings rate below −100% shows "—" with the gap in words; rates use a true minus and separators; Safe to spend gives a per-day figure only for a week or more. Four, then Other in donuts, the Sankey ("Other", "Kept" in green), treemaps, bars, small multiples and the loans list. Section headers carry only the title and dates. Trend month labels thin out and no longer overlap. Registers show money out in ink and transfers without a sign, and no longer clip the balance at 1,366px. Fields are soft wells, Cash planning sub-tabs are Nile, no all caps, budget spent is soft rose. Transaction, holding, planner and prices pages get a Back route from the page that opened them; the bank check's review link returns to the check. Accounts calls its total What you own. Mohab's expectations follow the new words.
- 2026-10-03 · Claude: Speed audit of the PC app from source (nothing packaged), recorded under **Page speed** in `docs/ARCHITECTURE.md`. On a 2,239-transaction encrypted profile the Overview takes about 0.9 s on the server and Budget › All time about 6.3 s (remembered, so every later Budget visit). Main causes: the same figures recalculated many times per page (14 positions and 94 ledger scans per Overview; 3,860 month-spending queries per All-time Budget), SQLCipher `cipher_memory_security = ON` (ledger scans about 3× slower), and registers that summarise every row to show 50. A request-scoped cache prototype gave identical pages, with the Overview about 2.7× and the All-time Budget about 17× faster. No code changed yet; the plan is in Architecture and the two owner decisions are under **Now and next**.
- 2026-10-03 · Claude: The brand guideline is now one file, `docs/BRAND_GUIDELINE.html` (3.6: Part A the app, Part B the website), the same file as the website's `brand-guidelines.html`. Removed `docs/APPLICATION_BRAND_GUIDE.md`, `docs/APPLICATION_BRAND_GUIDE.html` and the 2.10 generator in `tools/brand_guide/`. `AGENTS.md` gains the two-AI working rules (pull first, small pushes, dated and signed changelog entries, a **Now and next** hand-off at the top of the Project Overview).
- Fixed two tests that failed on `main`: the profile-gate test now awaits Starlette's `request.form()` wrapper, and the picker test allows set-up calls between inserting popup content and enhancing its pickers. With the hash-locked Linux dependencies (including `sqlcipher3`), the full suite passes.
- Add account-level **Change ownership**: move cash between the user's share and a saved person while keeping the account's gross balance unchanged. The posting goes through `TransactionService`, validates each owner's dated cash position, and appears as a readable ownership event.
- Add **Someone paid an expense for you**: record the owned expense against its category and attribute the matching in-account cash share to the payer. It counts in spending and budgets, preserves gross account cash, and can be linked to a reserve or planned payment.
- Keep new cash ownership history in the ledger. Legacy unlinked custody records remain readable for compatibility; edits, voids and restores validate resulting owner balances.
- Extend Mohab's screen-driven year to assign cash to a saved person and record an expense they paid, confirming that the account's gross cash does not change.
- Replaced line-by-line bank reconciliation with **Check against bank**: type the balance the bank shows on a date. A difference up to 1% of that balance or 100 (whichever is larger) is settled with one "Balance adjustment" row, counted as Other Personal spending or Other Income; a bigger one cannot be adjusted and links to that month's register or Import CSV. Mohab's October check is now one typed balance instead of 62 Clear clicks.
- Mohab's test and the Project Overview now state what the test focuses on: right answers, usability, efficiency, speed, simplicity, clarity and UI, in the Windows WebView2 app.
- Mohab's year now walks through user feedback batch 001: 11 fixed points are checked and 13 open pain points are strict expected failures in `tests/test_mohab_year.py`.
- Removed `tests/test_mohab_matching.py`; `tests/test_mohab_year.py` remains the single Mohab acceptance test.
- Added the owner's git workflow rule to `AGENTS.md` and a `CLAUDE.md` that loads it: work on `main`, push every branch, and merge finished branch work into `main`.
- Improve protected-profile CSV imports: accept source CSVs up to 5 MiB, with separately bounded mapping and review requests; keep unrelated forms at 512 KiB and uploaded bytes in memory (no plaintext temp-file spill). The importer remains CSV-only; PDFs are not supported.
- Make success/status messages accessible and temporary (five seconds); keep errors visible with ink-on-rose styling. Register balance clipping was not reproduced; the existing horizontally scrollable layout remains unchanged.
- Batch-load account/asset/class metadata in holdings and investment reports. In the 319-transfer synthetic report, SQL stayed at 6 reads instead of 641 per-row asset lookups; this service-level improvement does not yet establish the <500 ms full-tab goal.
- Corrected Batch 001 feedback traceability: App Feedback now attributes the 27 existing tickets to El Feki, records unavailable sender emails explicitly, and uses unique sequential Ticket # values 1–27.
- Added `user feedback/user-feedback-batch-001.md`, a polished and grouped compilation of the 27 current App Feedback submissions, with source-ticket traceability and prioritisation.
- Replace the app's former bolt mark with the supplied blue-and-teal ribbon logo in the main and profile headers and favicon; use its ICO conversion for the Windows executable. Package workflow artifacts now contain the named distributable ZIP and its SHA-256 file rather than only the loose app folder.
- Update Mohab's demo CD to use a real portfolio purchase rather than a cash opening balance, keeping the sample aligned with the no-cash CD rule.
### Export selected records · 2026-10-02
- Transaction registers, Categories, and the reevaluation ledger now offer **Export selected** after checking rows.
- Downloads are CSV files containing only the chosen records. Transactions include their ledger lines; categories include hierarchy and flags; reevaluations include checkpoint detail and the main-journal link.
- CSV text is protected from spreadsheet formulas, amounts keep their stored precision, and exports are capped at 1,000 selected records.
### CD purchase, maturity term and account navigation · 2026-10-02
- CD purchases now validate available user-owned cash in the selected bank/cash account on the recorded purchase date, then replay later posted cash movements so the CD cannot make a later balance negative. Unrelated negative history before the purchase date no longer blocks the purchase; a real shortage reports its date and amount.
- Maturity can be entered as a date or as a term in years (three-month increments). The two fields stay in sync, and a term calculates a calendar maturity date from the purchase date.
- **View CDs** sits in the account page's right-side actions, alongside other account actions.
### Settings: start fresh · 2026-10-02
- Settings › Your data has a **Start fresh** card.
- **Desktop app:** **Start a new profile** locks the current profile and opens the new-profile setup, with its own password and recovery key. The old profile stays exactly as it is and can be opened again from Profiles.
- **Browser mode:** **Start a fresh database** asks first, then:
  - backs up the current database;
  - sets it aside next to itself as `<name>_before-fresh_<date-time>.db`;
  - opens an empty database at the usual path.
  Nothing is deleted. If the file can't be moved (another program has it open), nothing changes.
### Budget: saved and invested, for the period · 2026-10-02
- The Budget's Savings rate card becomes **Saved and invested**, the same card as on Investments:
  - money in as 100 squares: invested in blue, kept in green, spent in rose;
  - the savings rate and the investing rate, which is part of it.
  It always covers the period chosen in the header.
- The split is worked out once in `investments.report.saved_and_invested()`, so Budget and Investments always agree. Before, it was calculated in the Investments page code.
### CD portfolios grouped by bank · 2026-10-02
- A `DEPOSIT` account is a bank-specific CD portfolio identified by its Institution field; it cannot hold cash.
- Each certificate is a separate non-cash `DEPOSIT.CD` asset with its own name and terms. Buying it creates a `BUY` ledger transaction funded from a bank/cash account the user selects.
- Interest and maturity proceeds remain forecast estimates. Interest is never posted automatically; users record it manually from bank statements. Actual redemption records the principal proceeds entered by the user.
- Migration `0039_cd_portfolios.sql` preserves old account-level `cd_terms` as legacy without destroying or automatically converting them. Cash left in old `DEPOSIT` accounts must be moved out; legacy terms remain until a history-safe conversion workflow exists.
### Our own calendar on every date field · 2026-10-02
- The calendar button on every date field (register rows, forms, popups) now opens Lightning's calendar instead of the browser's:
  - weeks run Monday to Sunday;
  - today is ringed and the chosen day filled;
  - Today and Clear sit at the bottom.
  It works from the keyboard and opens inside popups.
- The button shows a calendar icon instead of ▦.
### Calendar heatmaps, even range bars, every stat card fuller, the planner restyled · 2026-10-02
- Expense analysis ends with **Day by day**: the period as a calendar, total expenses on the left and net
  cash flow on the right (green kept, rose short). One month shows each day's date and amount; a longer
  period shows a small month per month, the last twelve at most. Weeks start on Saturday, the biggest day is
  darkest, and every day opens its transactions. It replaces the category-by-month table and the money in /
  money out / net table, and the outlined month is gone.
- The Overview ends with **Month by month**: the same calendar by month, a row per year since the first
  record, total expenses beside net cash flow; each month opens Expense analysis for that month.
- Inside its usual range?: every bar is now the same size. The pill runs from the lowest month (its value on
  the left) to the highest (on the right), and the status and now sit on the right.
- New `flows_by_date` in reporting: money in, money out and net per day or month, counted exactly like
  `cash_flow`, from one grouped query.
- Every stat card's number now grows with its card (smaller past seven characters), the sparkline sits
  above the number instead of behind it, and chips such as "until 2026-11-01" no longer clip.
- Investment planner: "How to split it" is the app's pill segment, the suggested split uses asset class
  colours instead of a rotating palette, and the labels match the guideline.
- Cash planning's tab bar scrolls on one line on phones instead of widening the page.
- App guideline 2.10 · Juniper.
### Dropdowns open inside popups again · 2026-10-02
- Select boxes in a popup, such as Account type when adding an account, opened their list behind the popup, where it couldn't be seen or clicked. The list now opens inside the popup.
### CD terms, interest projections and Mohab workflow fixes · 2026-10-02
- `0038_cd_terms.sql` — store certificate terms separately from ledger balances and preserve the estimated schedule across restarts.
- Add terms for each funded certificate account: principal, start, separate earliest-withdrawal and maturity dates, annual percentage rate, simple or compound interest, simple payout and compound capitalization frequency, and a bank/cash destination. Terms never create ledger entries; actual interest and principal transfers are recorded separately.
- Project simple-interest payouts and compounded maturity proceeds into Cash planning using actual days/365. Show CD proceeds separately from income, and do not add future proceeds to today's Free cash or Safe to spend. Suppress projections for unfunded CDs and replace a maturity projection when a future transfer is already recorded.
- Treat a CD as unavailable in *If you sold today* before its earliest withdrawal date. Use the CD class sale factor as an early-redemption estimate until maturity, then full remaining principal; Net worth and Free cash do not change. Bank fees and payout figures remain estimates, not bank quotes.
- Suggest early or changed recurring payments for explicit confirmation, store the transaction's actual paid amount, attribute linked recurring salary to its scheduled month in the income average, and prompt a later-plan and reserve review after a changed amount. No plan or reserve amount changes automatically.
- Bring Investments holdings down to five table columns with secondary details in an expandable row, and add progressively enhanced type-and-pick controls for reviewed own-data fields, retaining native form fallback.
### Release-readiness and finance audit · 2026-10-01
- Verified UI fixes: Budget overlap near 941px; Cash planning's tab strip and the shared period pill at 390px; Settings data-card overflow; account and all-transactions registers scrolling inside their cards.
- Updated Project Overview for the live net-worth history and income audit: Bonus is excluded from the average by default; early January salary booked in December drives the step 17 inflation. Four finance xfails remain open, and no-pay-month averaging has no dedicated assertion. Investments' nine holdings columns versus the guide's five and the own-data dropdown mismatch await owner choices.
- The profile selfcheck passed all six checks on synthetic data, and the full suite passed with four xfails and two skips. Ordinary Windows PC acceptance is still outstanding; no ZIP has been released. These results do not establish every finance case or an interactive click-through of every control.
### Shared Codex project context · 2026-10-01
- Add a short root `AGENTS.md` that routes repository tasks to the current
  product, architecture, visual, glossary and changelog sources without
  copying full documents into every task.
### Investments: calmer holdings, the waffle back, fuller cards; the month stepper · 2026-10-01
- Holdings: the total and class rows lose their bands; a thin hairline separates each class instead. Names are
  ink, only the gain percentage carries a colour, and the horizon is a quiet word (Short, Medium, Long, or Set)
  that opens its choice when clicked, in place of the coloured letters. Units read on one line with more room.
- Saved and invested is a waffle again: 100 squares of this period's money in, invested first, then kept, then
  spent, with the savings and investing rates beside it.
- The top cards' numbers grow with the card, so no card looks empty; the six-month line sits above the value,
  and Net gain or loss shows Growth and XIRR as two small figures at the bottom.
- The month stepper is one pill like the period buttons beside it: round chevrons and the month in a white
  pill. The month picker's year arrows match.
- App guideline 2.9 · Yarrow: grouped tables, the split waffle, numbers that fill their card, the month stepper.
### The period you pick stays picked · 2026-10-01
- The period chosen in a page header (All time, YTD, a month, or a custom range) now carries over to Overview, Budget, Expense analysis and Investments as you move between them.
- It stays until you pick another. A pick that shows an error is not remembered.
### Cash planning, tab headers and the Ask dialog · 2026-10-01
- Cash planning's Plan tab opens with four stat cards: Safe to spend (with about how much a day until your next
  income), Free cash, Due before your next income and Lowest point ahead. Then three questions: How is safe to
  spend worked out? (a waterfall from free cash, beside a 30-day timeline and its payment list), Where is my cash
  heading? (five month-ends of free cash, then the forecast dashed, beside money in and out per forecast month)
  and What is promised? (what you owe, beside the five biggest loans still to pay, then Others). The forecast
  table moved under Show the numbers. Add bill and Add loan left the page header; adding stays on Recurring and
  Loans.
- Every Cash planning tab (Plan, Recurring, Loans, Reserves) sits in a pill bar with icons and opens with its
  own header: an icon tile, the tab's name and one line on what it answers, in the tab's own accent.
- The browser's confirm and alert boxes are gone. Discarding unsaved changes in a popup, deleting a
  transaction, category or counterparty, applying budgets in bulk and the "select a category first" notice
  all use the app's own dialog: a white card with an icon in its tone, the question, one line on what happens,
  and buttons that say what they do. Escape and Cancel answer no; focus starts on Cancel before a delete.
- The App guideline is 2.8 · Clover: the timeline, forecast trend and flow columns are now in the app, with
  rules for tab headers and the Ask dialog. Its visual page is also written to
  `docs/APPLICATION_BRAND_GUIDE.html` by `tools/brand_guide/build.py`.
### Investment planner: biggest gaps first · 2026-10-01
- The planner has two ways to split new money: **Spread across gaps** (as before: every class below target
  gets the same share of its gap) and **Biggest gaps first** (the class furthest below its target, in
  percentage points, is filled until it is level with the next, then both together, and so on). When the
  money covers every gap both give the same split. The choice is remembered.
- Rounding cents now go to the largest suggestion, so a split always adds up and never shows a negative amount.
- One split function (`suggest_contributions`) serves the planner; the unused copy on the Investments page is gone.
### Investments and report pages, lighter · 2026-10-01
- Saved and invested is one light bar of money in: invested inside saved, then kept, then spent. Investing rate
  now counts only what came out of this period's savings, so it is never more than the savings rate; money
  moved in from earlier savings is noted.
- Report tabs carry no add buttons: Add holding, Target allocation and More actions are gone from Investments
  (holdings are recorded from their account; prices, the reevaluation ledger, new investments and targets are
  linked from Settings › Valuations). The Investment planner stays, now in the Meadow green gradient.
- Holdings open with an All holdings total row; class rows are soft bands and rows have no hairlines.
- The Reconcile portfolio value card is gone from the middle of the page.
- In the net cash flow heatmap only Net flow is coloured (green kept, rose short); money in and out are grey.
- Unit prices round to the unit too, except prices under 10.
### Expense analysis: five then Others · 2026-10-01
- Every item chart shows the five biggest categories, then everything else as one "Others".
- Small multiples sit beside the treemap. Month by month is two heatmaps side by side: money out by category,
  and net cash flow (money in, money out, what was left); the second needs no category filter.
- Each visual keeps a "Show the numbers" table.
### Whole units on reporting pages · 2026-10-01
- Overview, Budget, Expense analysis, Investments (with each holding and Target allocation), Cash planning's
  Plan and the Settings tables show money rounded to the nearest unit, key notes included. Values are still
  stored with their decimals, and registers, entry fields and their messages keep cents.
- Clustered columns put each value on top of its bar, the name right under the bars and the change against
  usual under the name.
### Counterparties learn their category and their spellings · 2026-10-01
- **Usual category:** each counterparty is filed under the category picked most often in its last 20 transactions, or the most recent one on a tie. Aliases count with their counterparty.
  - It fills in as soon as you pick the counterparty in the register, and when you save with no category.
  - It also applies in bank imports.
  - A default set on the Counterparties page still wins. That page shows the learned one as "Learned: Groceries", with "7 of the last 9" under it.
- **Learned aliases:**
  - The register's counterparty list now also offers close spellings under "Did you mean".
  - If you type "Talabaat", then press Enter or pick "Talabat", the typed spelling is saved as Talabat's alias, so it matches straight away next time.
  - Only close spellings that match nothing yet are learned. Picking a different name ("Uber" → Careem) is not.
  - A full alias list never stops the save.
- A counterparty can now hold **20 aliases** (was 10).
### Expense analysis cards · 2026-10-01
- Money out and the comparisons are one wider card: the amount and a six-month sparkline, then against the
  period before and against your usual month underneath.
- New card: Average payment, with how many payments and how many in the period before.
- Largest payment says how many times the average it is. Stat cards get depth: a top light, a lift on hover.
- Where did it go is half treemap, half ranked list of the big categories with each one's change against
  its usual month.
### Our dropdowns, percent steppers and table rows · 2026-10-01
- Every select box opens our own list: group headers, details indented, the current choice marked and a search
  on long lists (phones keep their native picker).
- Every % field has our own up and down chevrons, one whole percent a step; sale factors step by 1.
- Sale factors drop the "a factor here applies…" line under each class.
- Counterparties is a table of rows: inline row fields, the name takes the room, Delete is an icon.
- Cards stacked on a page keep a 20px gap.
- Target allocation can set a target on every class it lists, deposits included.
### Target allocation adds up to 100% · 2026-10-01
- A target that would take the total past 100% is refused, and the message says how much is left.
- Value to adjust is how much to buy (or sell) of that one class to reach its share with every other class
  left as it is: (target × total − value) ÷ (1 − target), because buying grows the total too.
### Categories, two by two · 2026-10-01
- Two categories side by side, each always editable: name, + / − / ±, Recurring and One-off as on/off pills,
  and add detail, archive and delete always visible. Changes save as you make them.
- An empty top-level group other than Personal, Work, Investment and System no longer shows.
- The "?" tips on Target allocation open to the right of the "?" and are no longer cut off.
### Docs: back to four files · 2026-10-01
- `docs/` holds only Project Overview (the story), Architecture (the technical side), the App brand guideline (the visual side) and the Glossary.
- The desktop build spec, review and plan, build status, work log and profile preview are folded into Architecture › Desktop app and encrypted profiles, describing what is built today. The milestone is now on the Overview roadmap.
- The research prototypes in `docs/desktop/reference/` (`encryption_prototype.patch`, `keyvault_sketch.py`) are removed: `lightning/security` and `lightning/database` now implement them. They remain in Git history.
- The brand guide's visual page and its generator moved to `tools/brand_guide/` (`python tools/brand_guide/build.py`).
### Expense analysis · 2026-10-01
- Four KPI cards give the gist of the period: money out against the period before, against your usual
  month, the biggest category with its share, and the largest payment.
- Then five questions, big categories only (anything under 1% of money out folds into "Smaller
  categories"): a treemap of where it went; now against your usual month as clustered columns beside each
  category's usual range; small multiples on one scale; and a category-by-month heatmap that ends with
  every month of the period you chose.
### Investments · 2026-10-01
- The page opens with three tiles: a waffle of what you kept and invested in the period, the period's
  Net gain or loss with Growth and XIRR, and Portfolio value with a sparkline that always covers the last
  six months.
- Allocation by class beside the biggest holdings; holdings grouped by class, both sorted by weight, with
  Units, Average cost, Cost, Current price, Current value, Unrealized gain %, XIRR (after a full year) and
  Horizon. An assigned horizon shows a letter badge (S, M, L); click it to change.
- Year-to-date dividends per holding beside the period's money in and out and each class's change in value.
  The horizon bar is always open, at the end.
- Each holding opens a page that answers: is it making money (price against average cost, where the return
  came from), how bumpy has it been (monthly moves, best and worst month, typical move, fall from its high)
  and its journey (value against cost, every trade and payout).
- New figures: Average cost and Growth.
### Category lists without breadcrumbs · 2026-10-01
- Every category picker (counterparties, bills and loans, bank imports, reserves, splits, the transaction
  form and the register's type-to-pick list) groups categories under their L1 as a header, each by its
  own name; an L2 with L3 detail reads as a header with its details indented under it. "Personal › Food"
  no longer appears anywhere, including tooltips and messages ("Added Groceries under Food & Groceries").
### Budget · 2026-10-01
- The top is a savings-rate waffle beside one plan bar: spent in azure, what is left in green, over plan in
  strong rose past the plan. The three cards are gone; their figures sit under the bar.
- Spent of plan is a bullet per category: the plan as a soft band ending in a tick, spent inside it,
  anything over carried past the tick in rose, with what is left or over on the right.
- Investment categories are never budget spending (fees and moves into investments stay in cash flow).
  One-off categories are left out of the budget's totals.
- The first-plan form groups categories under their L1 with compact row fields; the bulk-rules toolbar and
  rule fields match the row style; select boxes use the app's own style everywhere.
### Page width · 2026-10-01
- Every screen uses 90% of the space beside the sidebar, centred, and never less than the 1,120px content
  width (or the whole space on smaller screens).
### Valuations and target allocation · 2026-10-01
- Sale factors are grouped by asset class and compact. A factor on a class (Funds) applies to every
  kind left empty (Equity Fund, Gold Fund…); a kind's own factor overrides it, and clearing it goes back
  to the class's. Migration `0037_sale_factor_inheritance.sql` clears factors that only repeated their
  parent's, so every estimate stays the same.
- Target allocation lists every class, heaviest first; the Add a class chooser is gone. Difference reads
  in %, not pts. Each class has a "?" with a one-line definition. An empty field clears the target.
- Fields inside table rows use one inline style: a light green shade of the row, no border until you
  are in it.
### Categories overhaul · 2026-10-01
- Categories go one level deeper: an L2 can hold L3 detail (Food & Groceries › Groceries). L3 can be chosen
  on a transaction and rolls up into its L2 everywhere.
- A fourth top-level group, **System**, holds Money Held for Others and Loan payments (migration
  `0036_category_direction_and_system.sql`). Both keep their ids, so every transaction keeps its category.
- Every category shows **+** (income), **−** (expense) or **±** (both). You can change it; inside each group
  categories are soft-grouped by it, then sorted by name.
- Income categories are **Recurring** (counted in the income average and the forecast) or **Irregular**
  (bonuses). Bonus starts irregular, which fixes Mohab steps 26 and 27: an end-of-service payment and a
  month between jobs no longer lift Average monthly income. Expense categories can be **One-off**: they stay in cash flow and analysis but leave the
  budget's totals and estimates. Both flags are the same lists as Settings › Budget.
- The Categories page is one table: L1 as a header, an L2 with detail as a sub-header, L3 indented. Click a
  row to edit it in place. Archived categories are hidden behind an Archived link.
- Settings › Budget is compact: fields side by side in groups, choices as chips grouped under their L1.
### Overview 2.5 · 2026-10-01
- Net worth, Free cash and Net flow are wide split cards: numbers and toggle list left, the visual right.
- Where money in went is a Sankey; Cash flow has a column waterfall; Investments is its own section.
- No chart sits behind a toggle; Month by month is stashed (App guideline § 16).
- Four stat cards: Change in net worth, Savings rate, Investing rate and Left in plan. New figures
  Change in net worth and Investing rate.
### Mohab's workflow covers a salaried year · 2026-10-01
- **Steps 11–28 of the reference workflow** now carry Mohab from October 2026 to September 2027. They are dated, and each step has the figures it must show. The year includes an ATM fee, a refund, a repair paid from the emergency fund, a dividend, a reimbursed work expense, a bonus, an early payday, a raise, Eid, phone installments, a share sale, a rent rise, a holiday goal, and a job change with a month between jobs.
  - Each step says what is true today.
  - What Lightning cannot record yet (a gam'eya, a maturing certificate, dollar savings, early loan payoff) is listed separately.
- **`tests/test_mohab_year.py`** runs those steps on the demo household, one test per step. The steps that are wrong today are strict expected failures, so a fix shows up as an unexpected pass.
- **The questions** gain the follow-ups a salaried user asks, and a new question 8, "What changes when my pay changes?".
- **Wrong today** (recorded, not fixed):
  - A salary paid early, or a raise over 10%, is not matched, so the forecast counts it twice.
  - A rent rise matched within 10% leaves the plan at the old rent.

Older releases (0.5.0b1 and earlier) are further down in this file.

## [0.5.0b1] — 2026-10-03 — Next Windows desktop beta (package build pending)

- 2026-10-04 · Claude: Fixed: the Windows window never opened when the ZIP was downloaded in a browser and extracted in Explorer. Windows marks such files as coming from the internet, and .NET Framework then refuses to load pythonnet's and the WebView2 SDK's assemblies. The package now ships `Lightning.exe.config` with `loadFromRemoteSources`, and CI runs the shipped checks on files marked that way, which is how this was found. The window's failure report now records code locations.
- 2026-10-04 · Claude: Packaging review fixes. The shipped-ZIP checks now run on files marked as downloaded from the internet, as users' copies are. Licence notices also cover every package PyInstaller actually bundled, read from its build tables. Test tools (pytest, rich, pygments, httpx and others) are excluded from the app. The docs-only skip no longer misses a file moved out of the app (`--no-renames`). The release job only removes drafts it left itself (marker name), so a published release that lost its tag is never deleted. It also reports API errors as errors, not as "release already exists".
- 2026-10-03 · Claude: Dependable Windows packaging and releases (`.github/workflows/desktop-probe.yml`, now "Windows app"). The Windows build waits for the full Linux suite and is skipped only when nothing but documentation changed since the last successful Windows build (`packaging/ci_scope.py`). The ZIP that is uploaded is the one that was tested: checksum-verified, extracted to a fresh folder, and that `Lightning.exe` must pass the self-check and the WebView2 window check (`packaging/run_check.ps1`: time limit, exit code and report). The frozen self-check now renders the main finance pages and every app file they link on an encrypted synthetic profile, and a failed start records its stage and code locations. `packaging/package_app.py --strict` lists licences only for what ships, plus CPython's, PyInstaller's and the vendored notices in `packaging/notices/` (SQLCipher, OpenSSL, WebView2 SDK, .NET facades, proxy-tools); it writes `BUILD_INFO.txt` and names test builds `-dev-r<run>-<commit>` so they cannot pass for a release. A `v<version>` tag on `main` publishes the tested ZIP to `Lightning-downloads` through `packaging/publish_release.sh`: never replacing a version, draft first, read back byte for byte, then published. The bundled README gives the 5 MiB CSV limit. Owner setup and release steps: Architecture › Build and release.
- 2026-10-03 · Claude: Omar is now **Mohab** everywhere, at the owner's request: Mohab's test (`tests/test_mohab_year.py`), the sample household (`lightning/samples/mohab_2026/`, `generate_mohab_2026.py`, `load_mohab_2026`, the `/sample/mohab-2026` routes), the demo, the welcome page, the docs and older changelog entries. The website and its sample pack follow.
- 2026-10-03 · Claude: Budget group detail (owner request): "Tracked · N categories" and "Not tracked · N categories · X expected" are collapsible lists, each with "Select all" that ticks its rows for the bulk rules (% of income, 3m or 6m average) and updates the "N selected" count. Tracked opens by default; Not tracked starts closed.
- 2026-10-03 · Codex: Set the source version to 0.5.0b1 (display 0.5.0-beta.1) for the next beta. The Windows package workflow now runs from `main` and names the ZIP `Lightning-v0.5.0-beta.1-Windows-x64.zip`. This records the packaging setup only; Windows build verification and distribution are still pending.

## [0.4.0b1] — 2026-10-01 — First Windows desktop beta

### Desktop beta v0.4.0-beta.1 packaging · 2026-10-01
- Show the version in the Windows title and Settings. Align package metadata with it.
- Download one readable GitHub ZIP containing only the Lightning app, not a ZIP
  inside another ZIP with engineering-probe reports. Use one extraction.

### Key notes: the number first · 2026-10-01
- Every key note and the small cards on Expense analysis now read like a stat card:
  - a short label with a small tone icon;
  - **one big figure**, green when good, rose when it needs you;
  - one line of context;
  - one pill button.

  Examples: "Saved · 2026-09 → 32.4%", "Safe to spend until … → 49,520.84", "Bills · share of income → 30%".
- `keynotes.note()` gains `label` and `figure`. The full sentence stays as the title and the screen-reader label.
- App guideline 2.4 · Meadowlark documents the structure.

### Key notes that stand out, softer register fields, row actions on right-click · 2026-10-01
- **Key notes and the small cards on Expense analysis:**
  - Each card is a full tint of its tone with a matching border.
  - A solid colour tile holds a white icon that matches what the note says: trend up or down, wallet, share, alert, calendar, shield, people or tag.
  - Links take the tone's dark shade.
- **Register editing:**
  - The fields of the row you edit are a soft shade of the row, not white.
  - The field you are in turns a deeper shade with the green edge forms use.
  - The add row behaves the same way.
- **The bar under an edited row is gone.** Right-click the row for Save, Details and history, Cancel edit and Delete. Enter saves and Esc cancels. Other rows' right-click menu gains Details and history.
- **App guideline 2.3 · Glade** documents all three. Both halves are updated, and the azure-versus-green focus gap is closed.

### Desktop profiles and encrypted storage foundations · 2026-10-01
- Add Documents/Lightning profile paths, explicit alternate locations, read-only discovery, human-readable date/sequence/ID names and OS-backed profile locks. This is the upcoming launcher's storage contract; existing user files are not moved.
- Add an opt-in SQLCipher database driver, verified encrypted snapshots and explicit staged legacy import/recovery candidates that preserve their sources. Password screens and live restore are not yet connected.
- Commit migration SQL and its bookkeeping atomically, validate schema/resources before writes, and require protected verified pre-upgrade backups before upgrading existing data.
- Keep backup names identifiable by profile; pruning never touches another profile or protected upgrade backups. Update the existing Settings backup list for the new names.

### Windows desktop feasibility build · 2026-09-30
- Start the amended desktop plan with an isolated Windows one-folder build, protected loopback host, WebView2 navigation guard and synthetic encryption/resource checks.
- The first build is an engineering check, not a finance beta. It does not open or convert existing financial data; Linux browser operation is unchanged.
- Add password/recovery primitives shared across platforms, bounded tamper tests and a Windows build workflow. Password unlock is the chosen design on both operating systems; DPAPI is deferred.
- Remove the tracked `nul` artifact so Git for Windows can check out the repository. It remains recoverable from Git history.

### App guideline 2.2 · Grove: one guideline, with a visual page · 2026-09-30
- `docs/APPLICATION_BRAND_GUIDE.md` is rewritten as one unified guideline in 16 numbered sections. Its visual half, `docs/APPLICATION_BRAND_GUIDE.html`, uses the same numbering and shows every rule as a live sample. Rebuild the page with `python docs/build_brand_guide.py`.
- New in the guideline:
  - **Soft register fields:** 30px tall, `#F2F8F6` fill with no border, white with an azure border on focus. The row being edited takes the held tint.
  - **Stat cards:** three in a row, the first on the lead gradient.
  - **Key notes:** a tone tint fading to white, a 4px edge and a 32px icon tile.
  - **Cards:** the lead (gradient), wide, white and entry cards side by side, all with the app's 20px radius.
- **Charts:** a full catalogue of 40 chart types, each drawn with sample data and its use, rules and page:
  - 13 are in the app;
  - 25 are ready to use when a page needs them (forecast with range, Sankey, treemap, dumbbell, bullet, calendar heatmap and more);
  - 2 are marked to avoid.

  A "Never" list covers dual axes, 3D, gauges, radar and pies.
- **Where the old guideline and the app disagreed, the guideline now follows the app:** one type scale, the waterfall colours, the vivid gradient on the Investment planner button, and "Net gain or loss".
- No app behaviour changed. Two code comments now point at guideline 2.2.

### Desktop build spec (draft) · 2026-09-30
- New `docs/desktop/BUILD_SPEC.md` describes the Windows desktop app: one `Lightning.exe` window (pywebview, WebView2, PyInstaller) and data in `%LOCALAPPDATA%\Lightning`.
  - The database and backups are encrypted with SQLCipher. The key comes from a recovery key, and the app opens automatically through Windows DPAPI or asks for a password.
  - The local server needs a per-launch secret on every request.
  - It ends with ordered milestones, each with acceptance tests.
- It is a draft: nothing in it has run on Windows, and it has had no verification pass.
- `docs/desktop/WORK_LOG.md` records this session's work and the research behind the spec. `docs/desktop/reference/` holds the encryption prototype patch and the key-management sketch. Neither is production code.
- No application code changed.

### A chart with its numbers: net worth trend, free cash steps, richer Expense analysis · 2026-09-30
- **Overview:**
  - A net worth trend (the end of each month) sits at the top of Your position, with the breakdown cards under it.
  - Free cash shows its steps as a small waterfall: cash you own, less reserves and bills due, down to free cash.
- **Expense analysis** gains:
  - Compared with your usual month: each category this month against the average of the three months before, with a mini trend and the difference.
  - Who you paid, and Paid from (which account).
  - The largest payments.
  - These breakdowns add up to Money out.
- **Register:** the add row's fields are line-height and softly tinted instead of white.

### No browser history under fields · 2026-09-30
- Fields no longer show what you typed before, such as old names, amounts or "Gold 24k". The only suggestions left are the app's own: counterparties, categories and accounts. This applies to every form, popups included.

### Target allocation page, three-card summaries, key notes with colour · 2026-09-30
- **Target allocation:** it has moved from the bottom of Investments to its own page, opened from a button in the Investments header and from a new Settings tab.
  - Columns: Current %, Required %, Difference, and Value to adjust (how much to invest in a class, or take out, to reach the required share).
  - A Total row shows the required shares' sum and the portfolio total.
  - Each Required % saves on Enter or when you leave the field. The table redraws in place, so the page doesn't reload or scroll away.
- **Expense analysis:** Money out and its two notes sit side by side as three small cards.
- **Key notes:** each note's card is tinted by its tone (green good, blue info, rose needs you), with an accent edge.

### Asset class colours, grouped categories, popups to full pages · 2026-09-30
- **Asset class colours:** each class has its own colour in a family (cash azure; deposits, money market and fixed income in teal to light green; gold and gold fund; stocks and equity fund in greens; other in greys). The colours are in the app guideline, and a Total line under each donut says what share of the whole it covers.
- **Categories are grouped:** "Where it went" and Expense analysis show each L1 category as a header with its L2 categories under it.
- **Overview:**
  - The net flow number has its own label.
  - Investments is a header you can open, showing the portfolio value and the net gain or loss while closed.
  - Free cash has a "Plan to invest" button.
- **Investment planner:** its own button in the Investments header, in the Meadow gradient.
- **Popups:** every popup has a full-page button. A page opened that way, or from any other page, has a Back button to where you were.
- **Transaction editing:** a soft blue tint, and fields the size of the row, so it no longer jumps.
- **Holdings:** set the horizon straight from the table.
- **XIRR:** the yearly return shows on the Portfolio value card, with a "?" that explains it.
- **Fixed:** Money added listed every transaction in the period, including groceries and rent. It now lists only money that moved into or out of investment accounts, and the list adds up to the figure.

### Docs: four files · 2026-09-30
- `docs/` now holds four files. Project Overview tells the story, Architecture holds the technical side, the App brand guideline holds the visual side, and the Glossary defines terms.
- Merged into those files and then removed: `PRODUCT_UX_ARCHITECTURE.md`, `UX_REVIEW.md`, `BUDGET_APP_GAPS.md`, `UI_AUDIT.md`, the Mohab persona reports in `docs/personas/`, and `application-brand-guide.html`, which is now written out in `APPLICATION_BRAND_GUIDE.md`. All of them remain in Git history.
- The docs describe the Overview with Birdview folded in, and use the new figure names (Net gain or loss, Gain from sales, Money added and the others).

### Birdview folded into the Overview; budget rows; clearer names · 2026-09-30
- **Birdview is gone.** The Overview is the quick glance, and the reports under it (Budget, Investments, Expense analysis, Cash planning) carry the depth.
  - The Overview gains "What it is made of" (everything you own by kind) and "If you sold today" (each class with its sale factor), side by side in one wide card with a divider.
  - Month by month sits at the bottom of the Overview as a closed row.
  - Old `/birdview` links open the Overview with the same period. Expense analysis keeps its address.
- **Budget:**
  - The summary reads Planned, Spent, then Left in plan.
  - Tracked categories show the field names once, in a header row, instead of on every line.
  - One **Amount or %** field per category: type `1,500` for a fixed amount or `12%` for a share of average monthly income. The rule in use shows as a small note under the category name.
  - "Reset carryover" appears only when there is carryover to reset.
- **Clearer names** (applied everywhere from the figures registry, with the old names kept as aliases):
  - Realized gain → **Gain from sales**
  - Change in unrealized gain → **Price change on what you hold**
  - New money in → **Money added**
  - Left in plan after bills → **Budget left to spend**
  - Deposits and holdings after sale (estimate) → **Investments if sold (estimate)**
- The Safe to spend parts take their names from the registry, so they can't drift.
- **Tests:** all 294 pass.
  - Nine older tests described screens, names and rules that have since changed; they now check the current design.
  - Migration `0032_suppressed_reevaluations.sql` is now in the changelog.
  - The Overview keeps the months you picked when a custom range is refused, as Birdview did.

### Month picker, no explainers, clearer investment gains · 2026-09-30
- **Picking a month:** every month box opens a small picker instead of being typed. Pick the year with ‹ › and then the month; months after this one are greyed out. This covers the period controls on every page (Monthly and Custom), the Transactions month filter and the carryover month.
- **No explanation toggles:** "How is this worked out?" is gone from every page. A figure's name has to explain itself; one that doesn't gets renamed.
- **Result is now "Net gain or loss"**, everywhere, including "Net gain or loss by asset class". It adds sales, price changes, and dividends and interest, so it isn't only unrealized gains.
- **Overview:**
  - A closed **Needs you** row sits at the top: it shows the count and the first item, and opens to the full list. When nothing is due it reads "Nothing needs you today".
  - The key note under it is what is safe to spend.
  - Net flow shows the savings rate on the right, behind a divider.
  - Month by month moves to Birdview.
- **Wide cards** (the ones that span the page) get a third gradient: the lead card's soft green on the left, fading to white on the right.

### Crisp pass: one look on every page, less text · 2026-09-30
- **One type scale:**
  - Text: 12 (labels), 13 (notes), 14 (body), 15 (key-note titles), 17 (card titles), 20 (sections) and 28 (page titles).
  - Numbers: 40 (lead card), 30 (other cards) and 24 (tiles).
  - Pages use 5–10 sizes instead of 10–14, and nothing is smaller than 12 px.
- **Currency once:** "EGP" appears small beside a card's main number. Row amounts show only the number.
- **One look for shared parts:**
  - Card shape, lead-card style and tile style.
  - One expander with a chevron on the right.
  - The same button sizes, and one primary action per header.
  - A settings icon in place of the ⚙ emoji.
  - "Back" sits with the actions on Settings.
- **Fixes:**
  - The Cash planning tabs show which one is open.
  - Transactions amounts are no longer cut off.
  - Dates and numbers no longer break across lines.
  - Tabs don't wrap on a phone.
- **Less text, nothing said twice:**
  - Formulas move inside "How is this worked out?".
  - Key notes only say what the page doesn't already show.
  - Repeated dates and "As of" labels are removed where the page header gives the period.
  - "Upcoming" labels are removed; only due payments are marked.
  - Empty tables show one line instead of headers.
  - Birdview, Expense analysis and Investments lose the sub-tabs that repeated the sidebar.
  - Birdview is two cards: What you own (or Net worth) with what it is made of, and If you sold today.
  - The Plan forecast table has 5 columns.
  - Investments hides the Horizon column until a horizon is set, and shows units without trailing zeros.
  - Transactions show the category name without its group (the full path shows on hover), trade descriptions without internal codes, and notes on one line.
- Word counts fell 20–64% per page (Birdview 403 → 145, Overview 383 → 269, Plan 319 → 201).

### Demo pass: visuals, key notes and a sample household · 2026-09-30
- **Key notes:** each main tab opens with up to three one-sentence notes: the answer, what changed, and what needs you. Each note has its number and one link.
  - Overview: safe to spend until payday, or what needs you; the change in what you own; how much of money in you kept.
  - Budget: the categories over plan, and what is left per remaining day.
  - Loans: the payoff date and the next payment.
  - The other tabs follow the same pattern.
- **Charts follow the app guideline** on every tab, with colours by meaning and bars from zero. Every trend has a "Show the numbers" table.
  - Overview: a month-by-month money in and out trend, "Where it went" spending bars, and a "What you hold" donut.
  - Birdview: a donut of what you own.
  - Expense analysis: category bars and a spending trend against the plan.
  - Budget: spent-of-plan meters, over plan first.
  - Investments: a portfolio trend that starts at the first holding, and an allocation donut.
  - Cash planning: the forecast line, the bills bars, a payment meter on each loan, and the emergency-fund meter.
- **Simpler screens:**
  - Lead cards use the soft gradient with dark text, so formulas on them can be read.
  - "Needs my attention" is now **Needs you** and appears only when something does.
  - The holdings table has 5 columns instead of 8, and "Update prices" is under More actions.
  - Recurring shows one bar card instead of three tiles.
  - Budget's summary cards fill one row.
- **Sample household:**
  - `python -m lightning --demo` opens Mohab's last three months (accounts, spending, investments, gold, money kept for Mom, a budget, the emergency fund, bills and a car loan) in a separate `data/demo.db` on port 8766.
  - It is rebuilt on every start and dated up to today.
  - An empty Lightning offers the same household from its welcome page.
- The tab-by-tab audit and what this pass changed are in `docs/UI_AUDIT.md`.

### Open findings fixed (Mohab runs) · 2026-09-30
- **#111:** a holding with no price yet is valued at what you paid (no gain yet) and flagged "valued at cost". The investment Result is no longer "Unavailable", and it now matches Result by asset class.
- **#129:** each derived figure shows its number, one formula line and one closed "How is this worked out?" toggle with the meanings and notes, the same on every tab. The Plan tab shows about 20% fewer words.
- **#130:** adding a recurring item whose date has passed asks once: "I paid it — start from the next one" (the default) or "Not paid yet — show it as due".
- **#131:** recurring amounts under 50 are no longer suggested.
- **#132:** closing a popup asks to discard only when something was changed.
- **#133:** paying a different amount says so, and Recurring offers "Use … from now on".
- **Import review:** answering one row fills the other rows with the same imported name (16 decisions instead of 40 for Mohab's statement).
- **Fees:** the fee field can always be typed: inside the amount by default, on top of it when "Fees are extra" is ticked.
- **Buying by amount:** leave Units blank to buy or sell a fund by amount; units come from the price per unit or the latest price.
- **New names:** a new name with no similar existing name is saved without an extra confirmation. Similar spellings still ask.

### Project overview: workflow, questions and gaps · 2026-09-30
- The Project Overview describes the three layers and the hurried-user principle. It adds Mohab's month as the reference workflow, the seven main questions each with follow-up questions (where each is answered, or the gap), and what is still missing compared with the best budgeting apps.
- Outdated decisions are corrected: loans and What you owe now count, and the emergency fund uses Average monthly income.
- The Mohab persona reports are kept in `docs/personas/`.

### Glossary by layer: ledger, plan, report · 2026-09-30
- The Glossary and Architecture describe three layers: the **ledger** (real money that actually moved), the **plan** (what-if: budgets, reserves, scheduled bills and loans, sale factors, the forecast; it moves no money) and the **report** (reads both, stores nothing).
- Every reported figure lists its layer (Ledger, Plan, or Ledger + Plan), how it is calculated, and the one function that computes it. The tables are generated from `lightning/core/figures.py` (`python -m lightning.core.figures`), and a test fails if the Glossary drifts or a listed function doesn't exist.
- The basic terms and entry-form fields are marked by layer too.
- Calculations moved out of screens into one function each: Savings rate (`CashFlow.savings_rate`), Change in what you own (`PositionService.change_in_what_you_own`), and Result with Change in unrealized gain (`investment_period`, `results_by_asset`). The Overview and Investments no longer compute Result separately.

### Fixes from the Mohab v7.1 re-run · 2026-09-30
- Skipping a loan payment no longer forgives it: the payment moves to the end of the loan ("Move to the end of the loan"), and skipped payments show on Loans and Recurring with an undo.
- Amounts and dates accept Arabic-Indic digits (٦٠٠, ٥/١٠) and the Arabic decimal and thousands marks.
- Opening a budget month that hasn't started returns to this month with an explanation instead of an error.
- Popup actions (mark paid, skip, stop, undo) always show a confirmation.
- Plan items with paid history show **Stop** instead of Delete, with matching confirmation text. Editing a loan says First due date and Number of payments.
- The Budget summary shows the loan payments included in Planned. The Plan tab's loans link reads "See your loans".

### Cash planning fixes from the Mohab re-run · 2026-09-30
- A loan adds its payments to the budget: while Personal › Loan payments (or the loan's category) has no budget rule, it is planned at the payments scheduled that month. It ends when the loan ends; setting an amount replaces it.
- Safe to spend and the cash forecast no longer count a due bill twice (once as a bill due, again as budget still to spend). Income that is due but not received stays in this month's forecast.
- "Left in plan this month" on the Plan tab is now **Left in plan after bills** (Left in plan − Bills inside the plan), so it no longer shares a name with the Budget's Left in plan.
- "Already in your transactions?" only suggests the same counterparty, the same category, or an amount within 10%.
- The pay and item forms list banks and wallets first, then brokerage, and no longer offer deposits.
- Account pages say **In this account · What you own · Held for others** instead of Total · Yours.

### One name and one calculation per figure · 2026-09-30
- Every reported figure now has one name, one meaning and one formula (`lightning/core/figures.py`, mirrored in the Glossary). Derived figures show their formula under them, e.g. "Free cash = Cash you own − Reserves − Bills due".
- One position calculation (`lightning/planning/position.py`) feeds the Overview, Birdview, Investments, Settings, Reserves and the cash forecast. The tabs no longer re-add balances their own way.
- One **Average monthly income** (`BudgetService.income_average`): the budget, emergency-fund coverage and the cash forecast use the same categories, months and manual override. Before, Reserves averaged salary over six months and the forecast averaged all income over three.
- Investments' after-sale estimate now applies the same sale factors as Birdview (95% when unset). It is now **Holdings after sale (estimate)**; before, it added holdings at full value. "Liquidation factor" is now **sale factor**.
- What you own adds up the same way everywhere: Cash you own + Deposits + Holdings value + Other you own. Birdview no longer groups deposits with investments.
- Renamed on screens (full list in the Glossary):
  - All accounts / Gross balances → In your accounts
  - Money from others → Held for others
  - Liquid cash / Owned liquid cash → Cash you own
  - Investment cash → Brokerage cash
  - Assigned reserves → Reserves
  - Estimated liquid investments → Deposits and holdings after sale (estimate)
  - Cashflow → Net flow
  - Invested capital → Cost
  - Period result / Investment result → Result
  - Cash added and withdrawn / New money added → New money in (net on every tab)
  - Budgeted / Current budget → Planned
  - Left → Left in plan
- Entry forms use the same field names:
  - Held for (was Whom, Owned by, Owner)
  - Amount (was Total paid, Each payment)
  - Units (was Pieces, Quantity, Units you hold)
  - Cost (was What you paid in total)
  - Account and Cash account (was Held in, Paid from, Paid into)
  - Counterparty (was Paid to, From)
  - As of (was Price date, Statement date)
  - Due date (was Next date)
  - Type (was Kind, Action)
  - Notes (was Details)
  - Fees (the checkbox is now "Fees are extra")

### Cash planning · 2026-09-30
- Reserves became **Cash planning** with four sub-tabs: **Plan** (safe to spend until the next income, what you owe, the next 30 days, a three-month cash forecast), **Recurring** (bills, subscriptions and income, with suggestions from payments that repeat in your history), **Loans** (loans and installment plans with progress and payoff date) and **Reserves** (the previous page). `/reserves` now opens `/plan/reserves`.
- Scheduled payments are marked paid automatically when exactly one posted transaction matches; otherwise pick the transaction, record the payment, or skip it. Voiding the transaction makes the payment due again.
- **What you owe** (bills due + loans still to pay) is shown as its own item: bills due come off free cash, and the Overview and Birdview show **Net worth** = what you own − what you owe. Forecasts never change either figure. The free-cash integrity check now includes bills due.
- Loan payments count as spending: a new loan defaults to **Personal › Loan payments** (migration `0035_loan_payments_category.sql`), so its payments show in the budget and cash flow; paying one also lowers loans still to pay, so net worth is unchanged.
- Migration `0034_cash_planning.sql` adds `planned_items` and `planned_payments`. Also recorded: `0033_reserve_account_matching.sql` links reserves to a payment account.

### Guideline 2.1 controls, month reports and report fixes · 2026-09-30
- Buttons follow the guideline: 48 px pills on pages and 36 px inside cards and rows; the date button and month arrows are 48 px circles. Textareas keep a 96 px minimum.
- Every date reads `yyyy-mm-dd` (hints, placeholders, period labels, the investments chart and Reserves use `yyyy-mm`). The period control is one `‹ yyyy-mm ›` stepper, and custom reports take a from/to month; Enter keeps the selected period.
- Screens use a true minus (−5,000.00); big figures shrink to their tile instead of breaking mid-number; the cash-flow figure no longer runs into the savings ring; the register's date and notes fields fit.
- CSV import: a merchant typed as new on several rows is created once; a row error no longer crashes the review (500), and the error view lists only the rows to fix.
- Emergency-fund coverage averages salary over the months that received it, instead of always dividing by six.
- "Returns by asset class" and "Biggest movers" include holdings sold out during the period.
- Revaluations replaced by the engine no longer appear in Deleted transactions and can't be restored into duplicates.
- "Add existing holding" on a physical item no longer asks for a cash account; the XIRR row waits for a year of holdings; a yearless date like 30/9 no longer jumps to last year; Birdview names deposits with investments ("Investments and deposits"); wording and favicon fixes.

### Uniform controls and date fields · 2026-09-29
- Buttons, text and number fields, dropdowns, month boxes and segmented toggles share one font, a 40 px height (30 px for small buttons), one border and an 8 px radius; checkboxes keep their natural 16 px size.
- Every date field is the same component: a typeable ISO box (`31/1`, `31/1/2026` or `2026-01-31`) with the same calendar button, including the register, CSV review, reconcile, data checks, custom periods, prices and physical items. Dates are normalised on submit as well as on blur.
- The register date column fits a full date; the settings carryover month uses the `yyyy-mm` box; the Birdview class popup keeps only the dialog's close button.

### Overview information flow · 2026-09-29
- Replaced the mixed card grid with six ordered, divided sections: wealth, available cash, period cash flow, attention, expenses and investments.
- Expanded cash and reserve amounts now reveal contributing balances inline; expense category links preserve dates, and investment results use the selected period.
- Removed the three-item attention limit and included spending above zero-value plans.

### Product workflow pass · 2026-09-28
- Reworked the main pages around focused questions, quiet number-led cards, consistent expandable category rows, and shared comparison/progress/time-series visuals. Added the application brand specification and live-styled component reference.
- Replaced Management navigation with a Settings hierarchy for counterparties, categories and data checks; added distinct sidebar icons and clearer account grouping.
- Corrected monthly Budget scope and exposed spending outside listed groups; preserved category scope in expense totals and trends; repaired saved CSV mapping, custody import and counterparty deletion workflows. Moved UI SQL behind services.
- Defined task ownership, follow-up paths, shared components, and visualization rules in `docs/PRODUCT_UX_ARCHITECTURE.md`.
- Recorded previously added migrations: `0032_suppressed_reevaluations.sql` records accounts whose monthly valuation checkpoint was skipped; `0029_birdview_class_factors.sql` stores liquidation factors by asset class; `0030_investment_targets_by_class.sql` links allocation targets to asset classes; `0031_dividend_asset_reference.sql` records the investment asset associated with dividends.
- Completed the prior migration log: `0024_reevaluation_ownership.sql` adds ownership-aware reevaluation entries; `0025_reserve_category_matching.sql` links reserves to categories; `0026_reserve_allocation_history.sql` records dated allocations; `0027_investment_planning.sql` adds allocation targets and asset planning metadata; `0028_budget_rules_and_resets.sql` adds income-percentage rules and carryover resets.

### UX review pass · 2026-09-28
- Main tabs share summary-first layouts and expandable calculation details; secondary account actions are grouped for review.
- Account CSV import includes a copyable AI preparation prompt, CSV template, and downloadable counterparty/category matching reference. Copy works in import popups with a manual fallback.
- Registers export their filtered posted cash activity for external analysis, with account, currency, type, linked-account and ownership context. Text fields are protected from spreadsheet formula interpretation.
- Added tab review notes and a prioritized comparison with YNAB, Monarch and Simplifi in `docs/UX_REVIEW.md` and `docs/BUDGET_APP_GAPS.md`.

### Changed
- Ledger lines can carry an optional owner. Linked legacy cash and investment custody entries migrate to owner-tagged lines, owner balances are checked across dated postings and edits, and brokerage buys must use cash from the brokerage account and the selected owner's balance.
- `0022_physical_items.sql` adds named physical items and dated item valuations; `0023_ledger_ownership.sql` adds ledger-line ownership.

### Fixed
- Counterparty management is now linked in the sidebar; canonical names and aliases can be edited, and delete removes unused records or archives records referenced by transaction history.
- Re-uploading a previously imported CSV creates a new review attempt; duplicate matches are warnings users may skip or explicitly approve, and voided/deleted transactions no longer count as active duplicates.
- Cross-account transfer matching now compares signs from the imported account's point of view, flagging the opposite statement leg as a likely duplicate.
- CSV uploads now pause at a prefilled field-mapping step before row review; review submissions scale Starlette's form-field limit to the staged rows, and Post rows is available above and below the list.
- Revaluation checkpoints are revisited after investment trades are voided, preserving fee details during trade edits, and record-level money values retain cents. Static asset versions are bumped with UI changes.
- Database migrations `0012_custody_transaction_links.sql`, `0013_reevaluation_ledger.sql`, `0014_preserve_category_codes.sql`, `0015_reevaluation_source_hash.sql`, `0016_reconciliation.sql`, `0017_cash_reserves.sql`, `0018_reserve_spending.sql`, `0019_recurring_reserves.sql`, `0020_reserve_counterparty.sql`, and `0021_budget_carryover.sql` are tracked here.
- Date fields now accept day/month input such as `31/1`, infer the current year, and normalize to ISO; CSV rows accept the same format.
- Account setup now records an optional starting balance as an opening entry on an explicit date, so it is not reported as income; the welcome steps explain this flow.
- The all-accounts register has a deleted-transactions page with direct restore actions, and changing a transaction's kind explains that the original reference remains in history.
- Investment quick entry now asks for Buy, Sell, or Dividend and takes positive units for both buys and sells.
- CSV review counts uncategorized rows before posting, and register labels clarify that the field is for who money went to or came from.

- Monthly investment checkpoints now detect changed historical trades and prices, void superseded system journals, and rebuild linked return entries; sale-day checkpoints value remaining units at the forced sale price.
- Counterparty default categories now resolve regardless of capitalization, and the all-accounts register reserves a separate, labeled action column for Add.
- Money entry rejects ambiguous decimal commas, exponent/underscore notation, and amounts too large for safe storage. New ledger money/base totals are limited to cents; app money displays round to whole currency units while entry fields retain cents.
- Invalid month, investment-price date, and category-parent URL values now receive safe validation instead of overflowing or raising a server error.
- Investment fee details stay hidden unless the user ticks “Fees are excluded from the total”; the select menu is removed.
- Account management is now directly reachable from the sidebar, including inactive accounts.

### Added
- Defined a consistent, typo-tolerant search workflow and identity-safety contract across Lightning in the three canonical docs, using an existing open-source matcher for candidate ranking.
- CSV imports are no longer capped by row count (the 5 MB file-size limit remains).
- Documented the native Windows readiness milestone and current launcher, time-zone, and data-location gaps in the three canonical docs; Windows support remains unverified.
- CSV import now supports either one signed amount column or separate inflow/outflow columns; mapped statement rows merge into a single signed Amount before review.
- Categories can be selected individually or in bulk for activate/archive/delete actions; deleting a category with history or references archives it instead.
- Consolidated the budget workflow, UI audit/tasks, user-question map, and milestone roadmap into the three canonical docs; added last-updated, document-revision, and app-version metadata to each.
- Split the UI workflow audit into ordered, bounded implementation tasks for Luna, with acceptance criteria and a separate check for the conflicting asset breakdowns.
- Budget now starts with a history-based plan preview or one broad limit, then opens on monthly status with attention items, free-cash context, transaction feedback, and optional spending-limit carryover.
- Added read-only integrity checks for gross versus owned/custody balances, account-level ownership splits, expense and budget totals, reserves, and the net-worth bridge; missing valuations are shown as incomplete.
- Corrected budget actuals so income categories no longer reduce reported money-out totals.
- Audited the customer workflow and UI hierarchy across Overview, Birdview, Accounts, Budget, Reserves, and import; documented which controls to remove, relocate, or keep and a phased UI redesign.
- Defined the budget customer-flow milestone: one-action plan setup, everyday status and transaction feedback, optional spending-limit carryover, and a month review; cash reserves remain separate from budget limits.
- Documented the user questions Lightning should answer, the follow-up drilldowns for each, and the next Birdview history/performance milestone, including the role and limits of XIRR.
- Birdview replaces Investments in the main navigation with current owned assets, a configurable investment liquidation factor, cash reserves/free cash, income and spending timelines, and capital/return breakdowns by investment type and holding.
- Cash reserves for emergency funds and planned projects, with recurring due dates, optional Counterparty matching, payment links, and free-cash calculations; custody transactions never auto-link.
- Statement reconciliation lets users mark cash transactions cleared and compare the cleared balance with a statement amount.
- Expense transactions can be split across categories, and refunds reduce spending in the original expense category instead of inflating income.
- Confirmed Counterparty aliases are manageable from the Counterparties page, capped at 10 per Counterparty, and offered in register and CSV search.
- CSV review can remember a confirmed category for future transactions from that Counterparty.
- Activity-ledger categories organized as Personal, Work, or Investment, with up to one user-defined detail level below each broad activity category; money direction no longer determines the category tree.
- Transaction multi-select and right-click delete actions, with audit-preserving deletion and restore.
- "Money from others" custody entries tied to an account and owner; outstanding balances are excluded from net worth and reconciled in the net-worth bridge.
- CSV import is available for all account types. Statement rows can be edited inline, and valid incomplete rows can post with safe uncategorized/optional-counterparty handling.
- Database migration `0011_money_from_others.sql` adds custody tracking and converts existing legacy receivable accounts to Other Assets.
- Database migration `0010_category_families.sql` stores category families and migrates income activities into the Personal/Work/Investment tree.
- Canonical Counterparty records with normalized names, confirmed aliases, reusable default categories, and ranked approximate suggestions that never auto-merge. Bank import staging retains original source rows for review.
- Database migration `0008_counterparties.sql` adds canonical counterparties, aliases, transaction links, and bank-import batch/row staging.
- Database migration `0009_import_column_maps.sql` remembers a confirmed CSV header/sign mapping per bank account.
- Best-effort investment quote refresh runs when Lightning starts, saving supported Yahoo Finance quotes to
  price history so portfolio values and unrealized gains recalculate from the newest quote. Stocks and funds
  use their ticker with Yahoo's CA suffix; unsupported symbols keep their prior saved valuation.
- Budget planning can use a rolling average of the previous 3 or 6 complete months of spending for a category
  or group. The method repeats until changed; this-month-only overrides still work. Existing manual budgets remain.
- Database migration `0007_budget_averages.sql` stores the selected calculation method.

### Changed
- Account opening dates no longer restrict historical transaction entry, editing, or restoration; valid past-dated activity can be added at any time.
- Removed "Money owed to me"/receivable accounts from the active account model and choices; the app has no receivables workflow.
- CSV import review no longer requires a separate Counterparties resolution screen; corrections are made on the transaction rows.
- Investment-account names now appear in the left sidebar without internal account codes.
- Account codes no longer appear beneath account names in the sidebar or account register heading, or beside
  account names in the account list and account edit heading. Account names are sufficient in these views.
- Roadmap places searchable Egyptian investment catalogue before daily wealth history and return breakdowns.

---

## [0.3.0] — 2026-09-25 — M3 Investments, new register

### Added — M3 Investments (manual)
- **Investments** you can hold: stocks, funds (equity, money market, gold, other), gold and other — created with a
  kind and symbol; codes `STK:COMI`, `FND:AZ-GOLD`, `GLD:21K`. Units follow the kind (shares whole, fund units
  4 decimals, gold grams 3 decimals, gold karat → purity).
- **Buy, Sell, Dividend** and **"Holding I already own"** (units + what you paid in total, for existing positions).
  Buy/sell use the broker's own cash (THNDR) or another account (e.g. wallet pays for gold at home).
- **Positions** from the ledger, average cost (as THNDR shows): cost basis incl. buy fees, realized gain on sells
  (after sell fees), unrealized gain, dividends per holding, total return; allocation by asset class and by
  exposure (a gold fund counts as gold).
- **Prices**: "Update prices" page (one date, a box per investment). Valuation uses the newest of a typed price
  and the last buy/sell price (a typed price wins on the same day); holdings entered as already owned are
  valued at cost until priced, marked "at cost". Price changes flow into the net-worth bridge as revaluation.
- **Investments page** (`/investments`): value, invested, unrealized, total return, holdings table, allocation,
  sold-out positions. Account pages of brokerage / gold-at-home accounts show a Holdings strip and
  Cash · Holdings · Total, with Buy / Sell / Dividend buttons.
- "Physical asset (e.g. gold at home)" account type is now offered.
- New `investments` module (builds lines, calls `TransactionService.post()`); `AssetService.create_investment`,
  `set_price(s)`; `TransactionService.post()/repost()` for documents built by other modules.
- Docs: `PROJECT_OVERVIEW.md` rewritten for 0.3.0; glossary and architecture notes updated.

### Changed — the register (owner feedback)
- Its own design (not Actual's): a quick-add row, coloured edge per kind (in, out, transfer, investment, opening),
  a date shown once per day.
- **One Amount column**: positive = money in, negative = money out (replaces Payment / Deposit).
- **"To"** replaces "Payee". Typing or picking one of your accounts in To makes the row a **transfer** automatically
  (the Category box is not needed and is disabled).
- **Category is a type-and-pick box** (a list of matches while you type), not a dropdown. It accepts the full name
  ("Personal › Food & Groceries"), the short name, a unique part of it, or the code; ambiguous names ask "Which one?".
- The account register lists **cash only**; investment lines appear in holdings. Buys show as money out with
  "Buy 150 × STK:COMI @ 92.4 + fee 45.00".
- Sidebar groups accounts by kind: Cash & bank · Deposits · Investments · Other (values include holdings).

### Fixed / rules
- A holding can never go below zero units at any date — enforced on sell, edit, void and restore.
- An account's cash opening balance and each holding's starting amount are separate (`OPN` per cash or per holding).
- Holding values are kept at full precision (rounded only on screen), so net worth = cash + Σ units × price exactly.

### Decisions
- 2026-09-25 — Average cost; buy fees go into cost; sell fees reduce what you receive (owner, THNDR style).
- 2026-09-25 — Buys and sells are conversions: their lines net to zero at cost/proceeds, so gains appear as
  revaluation in the net-worth bridge and as realized/unrealized in the portfolio view.
- 2026-09-25 — Register: one signed amount, "To" (an account there = transfer), typed categories (owner).
- Dividends link to their investment through the cash line's memo (the investment's code).

---

## [0.2.0] — 2026-09-25 — Register, budgeting, simplification

### Added
- GitHub-ready: `.gitattributes` (keeps `run.bat` in Windows line endings), README section on cloning to
  another computer; `data/` stays out of Git so finances are never uploaded.
- `docs/PROJECT_OVERVIEW.md` — detailed hand-off brief: purpose, terminology, architecture, data model,
  ledger rules, service APIs, UI routes, roadmap, decisions log and rules for future changes.
- **Account register (Actual-style):** each account page is now a register with an entry row on top —
  Date · Payee · Category · Notes · Payment · Deposit — press Enter to save and the row is ready for the next one.
  Transfers are picked from the same list ("Transfer ↔ another account"). Clicking a row opens it.
- Payee memory: typing a payee used before fills in the category used with it last time.
- `TransactionService.record_in_account()` turns one register row into money out, money in or a transfer.
- **Actual-style layout:** the sidebar lists every account with its balance, grouped like the dashboard
  (Liquid Cash, Deposits…), with an "All accounts" total and "+ Add account".
- **All accounts register** (`/transactions`): every account in one register, one row per account touched,
  with an Account column; new rows pick their account in the entry row.
- **Edit in place:** click a row and it becomes editable — Save, Cancel (Esc), Void, Details & history.
  If an edit changes the kind (e.g. a transfer becomes money out) the old one is voided and a new one recorded,
  so a ref's prefix always tells the truth. `TransactionService.update_in_account()`.
- Register toolbar: "+ Add New", search (payee, notes, category, amount, ref) and a month filter.
- **Budgeting** (new `budgeting` module, `/budget` page, "Budget" in the sidebar):
  - budget vs actual per month for money-out categories, in two sections: **Personal** and **Work**;
  - budgets on a group (Personal 20,000 — the ceiling) or on categories (Food 6,000 — part of it);
    a group without its own amount shows the total of its categories; a warning when categories exceed their group;
  - **repeat until changed**: an amount applies from its month onward; "Apply to this month only" for one-offs;
  - Budgeted · Spent · Remaining · Money in tiles, per-line progress bars, over-budget in red,
    "spent without a budget", and Spent links straight to those transactions;
  - Overview shows a Budget card (Personal / Work progress).

### Changed
- **Savings = bank account.** One type "Bank account (current or savings)". "Deposit" now means a
  certificate / time deposit (CD), reported under Deposits › CDs / Time Deposits.
- **Where an account appears on the dashboard now follows its type.** The "Report cash in this account as"
  picker is gone; the form shows the result in words (e.g. "Liquid Cash › Bank Balance").
- **Screens show plain names instead of codes** for categories and asset classes
  ("Personal › Food & Groceries", "Liquid Cash › Physical Cash"). Account codes still appear with names.
  Codes remain in search, the ledger detail and the database views.
- **Categories page redesigned:** one block per group, categories as clickable chips, one "+ Add" per group;
  codes moved into an optional field on the edit form; system categories hidden.
- Dashboard renamed **Overview**; tiles: Net worth · Money in · Money out · Left over.
- Register columns follow Actual: Date · Payee · Notes · Category · Payment · Deposit · Balance.
- Generated codes keep whole words ("Cash at hand" → `CASH-AT-HAND-CSH-EGP`, not `CASH-AT-HA-…`).
  Existing codes are not changed — rename them from the account's edit page if you like.
- Opening balances cannot be negative.

### Fixed
- An account's start date can no longer be moved after its first transaction (the review's gap #1).
- **No more future dates:** transactions and account start dates cannot be after today, so every balance has
  one meaning ("today"); the "including entries dated after today" note is gone. Scheduled payments will come
  as recurring transactions (M7).

### Removed (architecture simplification)
- **Stored search text and the full-text index.** Search now reads transactions, accounts and categories
  directly (ref, date, payee, description, notes, account, category, amount), so nothing derived is stored and
  nothing can go stale. This also removes the search rebuild on renames and the whole category workflow.
- `ledger_entries.claim_id` and `transactions.import_batch_id` (their milestones, M5 and M7, will add them),
  the unused `DRAFT` status, and the empty `integrations/` placeholders.

### Removed
- The separate Money out / Money in / Move money form pages and the old transactions list — the register replaces them.
- **Liabilities.** Credit card, loan / installments and "money held for others" account types, the
  Liabilities asset classes, and all "amount owed" logic. Lightning tracks what you own.
- The "Savings / Interest-bearing" asset class (savings accounts are bank accounts).

### Decisions
- 2026-09-25 — No liabilities (owner). Card or loan payments are recorded as money out from the paying account.
- 2026-09-25 — Savings and current accounts are the same type (owner).
- 2026-09-25 — Codes are for data; screens use names, except account codes which always travel with the name (owner).
- 2026-09-25 — Account pages work like Actual Budget: one ledger underneath, filtered per account (owner).
- 2026-09-25 — Screen structure follows Actual: accounts sidebar + register (owner). Schedules, import and the
  cleared tick come with their milestones (M7 recurring, M7 import, M2 reconciliation), not as placeholders.
- 2026-09-25 — Budgeting (owner): budget vs actual (no rollover), budgets at either level, repeat until changed,
  Personal and Work as separate sections. Actuals always come from the ledger; only budget amounts are stored.
- 2026-09-25 — Architecture review simplifications applied (owner). Kept on purpose: price and asset fields
  (M3 investments is next) and `sort_order` (keeps asset classes in a meaningful order, e.g. Liquid Cash first).

### Schema
- `0006_simplify.sql` — drops the full-text index, its triggers and `transactions.search_text`,
  `transactions.import_batch_id`, `ledger_entries.claim_id`. No financial data changes.
- `0005_budgets.sql` — `budgets` (category × month × amount, repeating or this-month-only) and a readable `v_budgets` view.
- `0004_bank_and_no_liabilities.sql` — savings accounts become BANK; every account's reporting group is reset
  from its type; unused Liabilities and Savings asset classes removed. Stops without changing anything if a
  credit-card, loan or held-for-others account exists.

---

## [0.1.0] — 2026-09-25 — M0 Foundation + M1 Cash & bank basics

### Added — M0 Foundation
- Project skeleton as a modular monolith: `core`, `database`, `assets`, `categories`, `accounts`,
  `transactions`, `reporting`, `workflows`, `integrations`, `ui`.
- Exact money handling: `Decimal` everywhere; stored as integers ×1,000,000 (`_e6` columns).
- ISO dates (`yyyy-mm-dd`) enforced on input, storage and display.
- Readable identities: account codes (`CIB-CUR-EGP`), asset codes (`CASH:EGP`), dotted category and
  asset-class codes (`EXP.WORK.SOFTWARE`), and fixed document refs (`OUT-2026-09-25-003`, lines `/1`).
- Posting engine (`core/ledger.py`): internal lines must net to zero; money in/out needs a category.
- Plain-SQL migrations with a `schema_migrations` table; optional FTS5 search migration with LIKE fallback.
- Seed data: asset-class tree, cash assets (EGP, USD, EUR, GBP, SAR, AED), category tree.
- Audit log for every edit, void and restore.
- Automatic backup on start (`data/backups/lightning_yyyy-mm-dd_HHMM.db`, newest 30 kept) and a
  "Back up now" button.
- Architecture rules enforced by `import-linter` (4 contracts) and tests.
- `CHANGELOG.md` (this file) — every change is logged here; a test checks each version and migration is listed.

### Added — M1 Cash & bank basics
- Accounts: cash wallet, bank, savings/deposit, brokerage, money owed to me, credit card, loan,
  money held for others. Codes suggested automatically; last 4 digits only.
- Opening balances recorded as `OPN` transactions; liabilities entered as "amount owed".
- Money in, money out and transfers, with edit (ref never changes), void and restore.
- Credit cards and loans work as balances: spending on a card is money out; paying it is a transfer.
- Search across ref, date, accounts, categories, amount, payee, description and notes (Arabic works).
- Reports: net worth (total, by account, by asset class), net-worth bridge, cash flow
  (household vs investment income, personal vs work spending), spending by category, 6-month trend,
  account statement with running balance.
- HTML app (FastAPI + Jinja2, no build step, works offline): dashboard, accounts, transactions,
  categories, settings. Light and dark mode, phone-friendly.
- Windows launcher `run.bat` (macOS/Linux `run.sh`).
- 100+ automated tests, including a randomized 300-step ledger test for the net-worth equation.

### Decisions
- Accounts (where) and financial assets (what) are separate; cash is classified by the account
  holding it (`cash_class`), investments by the asset.
- One ledger: transactions (documents) → ledger entries (lines). Every balance and report is derived.
- Net-worth equation: closing = opening + money in − money out + revaluation + new balances added.
- No `opening_balance` field on accounts and no `include_in_net_worth` flag (it would break the equation;
  pass-through money belongs in a "Money held for others" account instead).
- Edits happen in place with an audit trail, not by reversal entries.
- Plain `sqlite3` + SQL files instead of SQLAlchemy/Alembic.
- M1 is EGP-only; other currencies wait for FX rates in M4.
- Balances on screen are "as of today"; future-dated entries are shown separately.
- Edit and void moved from M2 into M1 (the app is not usable without them).

### Schema
- `0001_initial.sql` — settings, asset_classes, financial_assets, accounts, categories, transactions,
  ledger_entries, price_history, fx_rates, audit_log.
- `0002_search.sql` — FTS5 full-text index on transactions (optional).
- `0003_readable_views.sql` — `v_ledger`, `v_balances` for browsing the file.
