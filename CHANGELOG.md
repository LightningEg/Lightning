# Changelog

Every change to Lightning is recorded here — newest first. Dates are `yyyy-mm-dd`.

**How to log a change**

- Add one entry at the top of `## [Unreleased]
- 2026-10-13 · Codex: Project Overview sections and nested screen questions now use tiered numbers for clear handoffs; contents table matches.
- 2026-10-13 · Claude: website analytics in two tiers (website repo): a consent bar (Keep essential only / Allow all), a Privacy Notice in EN and AR, release-tagged GoatCounter events (`events.csv`) and opt-in linked visits through Apps Script (`journeys.csv`, 90-day purge). Setup in `OWNER.md`.

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
- Keep it to three lines at most: what changed for the user or the code, and where. The reasons and details belong in the doc that owns them (`AGENTS.md` lists which).
- To catch up, read only the first entries here, or `git log --oneline -20`. Entries further down are history, not the current specification.
- When a version is tagged, rename `Unreleased` to that version and start a new `Unreleased` above it.

## [Unreleased]

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
