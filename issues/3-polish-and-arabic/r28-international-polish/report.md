# International polish: the small things that make Lightning feel finished

Date: 2026-11-08 · Author/reviewer: Claude
Repository: app · Reviewed commit: 3c8743bb3b7cdfdf90200c588fa4f9fd9ca8e02b
Code: r28 · App version: 2.1.0 · Builds on: [r27](../../12-desktop-ux/r27-journeys-and-visual-unity/report.md)

## Assessment

Lightning already works, and most of the basics an international app needs are in place. Fonts are bundled for offline use, every page has its own title, the money formatter is shared and uses a true minus, double submits are blocked, dialogs are branded (there is no native `confirm()`), and Undo exists. The Arabic layout really is right to left, with Arabic-Indic digits and isolated dates.

What still gives it away as unfinished is a layer of **small inconsistencies people notice without being able to name them**:

- A "1 days left" here.
- A confirmation in Arabic that says "OK" to a delete.
- A chevron pointing backwards in Arabic.
- A browser tooltip where a branded message should be.
- A Windows default scrollbar.
- A "-89.5" with a hyphen next to "−66,500" with a true minus.
- "Ledger", "counterparty" and "Back to the dashboard" on a page called Overview.

r27 asked whether the journeys connect. This report asks the next question: **once they do, does every pixel and every word feel deliberate?** None of these items changes money logic. Most are size S or M, and together they move Lightning from "works" to "feels made".

## Scope and method

The probe ran on the latest `main` (3c8743b), on a disposable encrypted profile with the sample household, with the date fixed to 2026-11-08 and prices offline.

- **[evidence/probe.py](evidence/probe.py)** visits 17 PC pages at 1366 × 768 and 10 phone pages at 390 × 844, in English and Arabic (54 page visits).
  - On each page it records the title, `lang`/`dir`, how many figures use tabular digits, hyphen minus against true minus, decimals on big figures, leaked internal words, straight quotes, "1 things" plurals, date formats, Latin text on Arabic pages, all-caps, targets under 24 px, unnamed controls, clipped text, the spread of font sizes, weights, radii and shadows, inline styles, the first six focus rings and console errors.
  - It also checks where focus lands when Add opens, and whether the pages respond to the operating system's dark mode.
  - Results are in [evidence/probe.json](evidence/probe.json); 13 screenshots are in [evidence/shots/](evidence/shots/).
- **Two read-only code sweeps.**
  - Templates, CSS and JS for interaction states, forms, icons, tokens, accessibility and touch.
  - Words, i18n and Arabic: untranslated paths, plurals, bidi, voice, error text, search and sorting.
  - Each claim below was checked against the source at the cited line before it was filed. Counts come from `grep` on 3c8743b.
- **The rules being applied are the guideline's**: A06/A06.1/A06.2 numbers and type, A10 controls, A14 words, A15, C05 touch, C10, C13, and `brand-voice.md`.
  - Where a finding would change the guideline itself (date display, Arabic currency label), it is filed as an owner decision, not a fix.

**Limits.**

- This is an expert walkthrough in headless Chromium, not WebView2 on Windows or a physical Android phone.
- Arabic was checked by rule and pattern, not by a native reader.
- Paid themes, onboarding and native file dialogs were not exercised.
- The probe's heuristics over-count in places: "small targets" includes 13 px checkboxes that sit inside a larger clickable row, and "clipped" includes headings whose glyphs overhang. Every finding below was confirmed on the screenshot or in the source.

## What r27 found that is now fixed

| r27 | Then | Now (this probe) |
| --- | --- | --- |
| J1 | Phone Add opened on `kind`; typing 120 filled nothing | **Fixed on the phone.** Focus is on `amount` and typing gives `120` (`phone en add-focus` in probe.json). **Still open on the PC.** `/accounts/1/transaction/new` opens with nothing focused, the amount is the fourth field, and typing fills nothing (`pc en add-focus`): see F12. |
| J3 | Scenarios showed literal "None" and cents | **Fixed.** It now says "No shortfall" and shows whole EGP, with a line explaining why it differs from Cash planning ([shot](evidence/shots/pc-en-plan-scenarios.png)). |
| J5–J8, visual unity | Hierarchy, navigation, secondary-job layout | Not re-checked here; they stay with IV-3AY, IV-3AM and IV-3H. |

## Findings

Severity: **high** means wrong action or lost trust, **medium** is visible on a common path, **low** is noticed only by a careful eye.

### A. Things that are wrong today (bugs)

| ID | Sev. | What a person sees | Evidence | Item |
| --- | --- | --- | --- | --- |
| F1 | high | **Arabic delete confirmations look harmless.** `askFrom` translates the text first, then looks for `?` and the English words `delete|remove`. Arabic ends in `؟` and has neither word, so every Arabic delete opens as an info dialog with "OK", focus lands on Yes, and Enter deletes. The English safeguard (Enter must not delete) is lost in Arabic. | `lightning/ui/static/app.js:503-506` | BV-3BB fixed: [browser regression tests](../../../tests/test_confirm_dialog_browser.py) |
| F2 | medium | **Chevrons point backwards in Arabic.** "ادفع ›" and "مراجعة ›" point right, toward the word, on a right-to-left row. Forward should point left. 105 `›` text glyphs appear in templates. Only some SVG chevrons are flipped (`style.rtl.css:3256`, `phone.rtl.css:47`). | [phone-ar-home](evidence/shots/phone-ar-home.png), rows "To do" | [IV-3BG](../IV-3BG-phone-finish.md) |
| F3 | medium | **Plurals.** "1 days left" (`ui/kpis.py:123`), "1 categories" (`categories/list.html:46`), "Delete 1 transactions?" (`app.js:850`), "1 of 1 payments made" (`keynotes.py:212`). 47 hand-rolled `'s' if` ternaries and no shared helper. In Arabic, a count built in English before translation never agrees: "2 معاملة", "في 1 حسابات". The Arabic counted-noun engine (`i18n.py:3485-3511`) knows only 4 nouns. | grep counts in the item | [IV-3BC](../IV-3BC-counts-read-right-in-both-languages.md) |
| F4 | medium | **Half-English sentences in Arabic.** "جرّب تاني بعد 5 minutes." (`runtime/session.py:84`). "احذف this category? …" (`categories/list.html:100`). "البند 2: price and exchange rate must be positive." (`core/ledger.py:164`). A record reference in the tooltip: "OUT-2026-10-02-001 — عدّل في القايمة دي" (`register.html:217`). | source lines | [IV-3BD](../IV-3BD-errors-speak-plainly-everywhere.md) |
| F5 | medium | **Unbranded and untranslated errors.** Validation errors from JSON routes return `{"error": "<English>"}` (`web.py:670`). A cross-origin block is plain text (`web.py:612`). `HTTPException(400)` in exports falls to FastAPI JSON (`routes/exports.py:37,109`). 87 validation messages have no Arabic. Every validation page is titled "Check your setup" and offers the same three links, whatever the error (`validation_error.html:2-5`). Raw Python exception text reaches people ("Could not read this CSV: {exc}", `bank_import_rows.py:277`). | source lines | IV-3BD |
| F6 | low | **A PC route that 500s.** `GET /transactions/sorted` renders `transactions/sorted.html`, which exists only as a phone template, so the PC gets a server error. Phone sorting is fine. | `routes/transactions.py:161` | IV-3BD |
| F7 | low | **Hyphen where a minus belongs.** "-89.5 points" on the Overview KPI sits beside "−66,500" (`kpis.py:294,341` use `f"{gap:+.1f}"` and bypass `_signed_pct`). In the browser, `Intl.NumberFormat(undefined, …)` (`app.js:1391,1443,1526`) follows the Windows locale, so a German or French PC shows "1.234,56" with a hyphen next to the server's "1,234.56". | [pc-en-home](evidence/shots/pc-en-home.png), KPI row | [IT-3BE](../IT-3BE-one-number-format.md) |

### B. Polish gaps (the "feels made" layer)

| ID | Sev. | Gap, and what professional apps do | Evidence | Item |
| --- | --- | --- | --- | --- |
| F8 | medium | **Focus rings.** Buttons get the browser's default ring, while tiles get a custom 2 px ring. Inputs use `outline:0` with a box-shadow (`style.css:1083`), which disappears in Windows High Contrast (`forced-colors`: 0 rules). `style.css:326,333` drop the outline on `:focus`. Linear and Revolut use one ring, on `:focus-visible` only. | source lines | [IV-3BF](../IV-3BF-pc-finish.md) |
| F9 | medium | **Native browser bubbles for validation.** 224 `required` fields, 0 `novalidate` forms, and `reportValidity()` at `app.js:800`. The guideline's rose well (A10) appears only after a server round trip, so the first error a person sees is a Chromium tooltip in the system font. | source lines | IV-3BF |
| F10 | medium | **Off-brand fonts still load.** Inter, Plus Jakarta Sans and JetBrains Mono are declared at `style.css:29-45` and in `profiles.css` before the guideline layer at `:799` overrides them. A06 allows only Bricolage Grotesque and Manrope (Readex Pro and Noto Sans Arabic in Arabic). The profiles/lock screen, the first thing anyone sees, uses Plus Jakarta. | source lines | IV-3BF |
| F11 | low | **Windows chrome shows through.** No styled scrollbars (`scrollbar-color`/`scrollbar-gutter`: 0), so WebView2 draws thick grey Windows bars. No `::selection` colour (0 rules). Spellcheck is on for 940 of 951 inputs, so "Carrefour" and "THNDR" get red squiggles in name and counterparty fields. | grep counts | IV-3BF |
| F12 | medium | **PC Add is not amount-first** (r27 J1, PC side). The page title, the card title and the button all say "Add transaction" (A16: a line that repeats its label). An empty well sits above the buttons. The amount placeholder "0.00" shows decimals, and the amount is not focused. | [pc-en-…transaction-new](evidence/shots/pc-en-accounts-1-transaction-new.png) | IV-3BF |
| F13 | medium | **Phone touch details.** In phone Settings, 12 quiet links are under 24 px tall (C05: quiet links 44 tall). No `-webkit-tap-highlight-color` in `phone.css`, so Android flashes a grey box on every tap. No `overscroll-behavior` on the body, so the whole app bounces. No `user-select:none` on the tab bar. No `<meta name="theme-color">`, so the status bar is not tinted. `enterkeyhint` appears once in all phone forms. | probe `phone en /settings`; grep | IV-3BG |
| F14 | low | **Icons are drawn three ways**: Lucide-style SVG (73), text glyphs (`›` 105, `×` 11, `⋯` 13), and stroke widths 1.75, 1.8, 2, 2.2, 2.4, 2.6 and 3 where A15 says 1.75. Text glyphs follow the font, so their size and weight drift from page to page, and in Arabic they render as F2 shows. "Profiles & lock" is the only side-nav item without an icon ([pc-en-home](evidence/shots/pc-en-home.png)). | grep counts | IV-3BF (PC), IV-3BG (phone) |
| F15 | low | **Design-token drift.** 13–14 distinct font sizes and weights 400/500/600/650/700/800 on one PC page (A06 names 500, 600, 700 and 800). 9–12 border radii per page. 139 inline `style=` attributes (35 on Budget, 39 on Cash planning). About 294 hard-coded hex colours outside the token files (e.g. `phone.css:204` `#097852` is `--positive`). 290 `!important`. 27 z-index values with no scale. Each is invisible alone; together they cause the "slightly different on every page" feeling. | probe.json `fontSizes`, `fontWeights`, `radii`; grep | IV-3BF |

### C. Words (the "says it like a person" layer)

| ID | Sev. | Gap | Evidence | Item |
| --- | --- | --- | --- | --- |
| F16 | medium | **Accounting jargon on screen.** "ledger" (57 keys, including the heading "Reevaluation ledger"), "Counterparty/Counterparties" (63 keys, and a nav heading), "reevaluation" (12), "Principal cannot exceed the CD's currently owned ledger balance" (`deposits/service.py:296`). Monzo and YNAB say "who", "payee" or "shop", not "counterparty". | i18n keys | [IV-3BH](../IV-3BH-one-name-per-thing-no-jargon.md) |
| F17 | medium | **One thing, several names.** "Cash planning" (section) / "Plan" (tab) / "Planning" (heading). "Held for others" / `/money-from-others` / أموال لغيرك. "Overview" in the nav, but "Back to the dashboard" on the 404 page ([shot](evidence/shots/pc-en-does-not-exist.png)). "Gam'eya" 43× and "Gam’eya" 2×. Arabic mixes ذهب 32× with دهب 25×, and إنت 13× with انت 11×. | grep counts | IV-3BH |
| F18 | low | **Title Case and developer phrasing.** 27 of 61 built-in categories are Title Case ("Eating Out", "Unaccounted Money Found") against A05 sentence case. Other examples: "Could not save; retry with Enter or blur." (`budget.html:83`), "The journey" (`investments/holding.html:83`; brand-voice lists "journey" as off-voice), "YTD" as a button, headings built from codes ("Edit FND:AZMM", `investments/asset_form.html:4`). Straight apostrophes in visible strings: 30 straight, 6 curly. | source lines | IV-3BH |

### D. International readiness under the surface

| ID | Sev. | Gap | Evidence | Item |
| --- | --- | --- | --- | --- |
| F19 | medium | **Arabic search in the register is not folded.** Global search folds hamza, ة/ه, ى/ي and diacritics (`core/matching.py:33`). The Transactions search box uses plain SQL `LIKE` (`transactions/repository.py:63-70`), so "احمد" does not find "أحمد". Sorting is by code point or `NOCASE` with no Arabic collation. `localeCompare` is called without a locale (`app.js:1712,1801`). | source lines | [IT-3BI](../IT-3BI-arabic-search-sort-and-calendar.md) |
| F20 | low | **Calendar and clock.** The heatmap week starts on Saturday (`visuals.py:247`), but the date picker starts on Monday (`app.js:652`). 7 naive `datetime.now()` and 4 `date.today()` calls bypass the app's single `today()` (`routes/sms.py:92`, `sms_imports.py:125,408`, `desktop/window.py:82`). | source lines | IT-3BI |
| F21 | — | **Choices only the owner can make.** The guideline fixes these today, and international apps choose differently. Filed as one owner decision. | see the item | [OW-3BJ](../OW-3BJ-international-display-decisions.md) |

F21 covers these choices:

- **Dates.** A06.1 says `2026-11-08` and crosses out `30 Sep 2026`. Revolut, Monzo and YNAB show "8 Nov" and "November 2026"; ISO reads as a database to most people, and Arabic shows "٢٠٢٦-١٢-٠١" ([phone-ar-home](evidence/shots/phone-ar-home.png)). The period chip reads "2026-11" in Western digits on the Arabic PC page while the rest is Arabic-Indic ([pc-ar-home](evidence/shots/pc-ar-home.png)), and `workflows/review.py:31,251` already uses "%B %Y".
- **Currency label in Arabic.** "EGP" 243× on Arabic pages, with جنيه in a few translations.
- **Row decimals.** The PC keeps ".00" on every row; the phone drops it (A06.1 and C10 disagree).
- **Percent sign.** "%" 88× and "٪" 3×.
- **Light/dark.** The app ignores the system's dark mode ([pc-en-dark](evidence/shots/pc-en-dark.png)); A15 says light only for now.
- **How Arabic addresses the person.** It is always masculine (اختار 300×, no feminine or neutral forms).

## What is already international-grade (keep it)

- **Type.** Fonts are bundled, `font-display: swap`, `unicode-range` on every face, no CDN. `tabular-nums` appears 138× in `style.css` and is used for most figures (the probe saw 41/41 on Transactions and 16/21 on Overview). No `...` (the ellipsis character is used), no emoji, sentence-case headings, no "Please", "Successfully" or "!".
- **Money.** One server formatter (`web.py:61` `_money` over `core/money.py:301`), a true minus on screen and a hyphen in exports, whole EGP on reporting pages, `nowrap` figures with the currency inside the span.
- **Arabic.** `<html lang="ar-EG" dir="rtl">`, a generated RTL stylesheet, Arabic-Indic digits with `٬` and `٫`, U+2066/2069 isolation of numbers and dates, compact ألف/مليون, Egyptian month names, letter-spacing reset, and arrows swapped (`i18n.py:3532`). 18 Arabic tests pass. A crawl of 50 Arabic pages found almost no lowercase English.
- **Feedback.** Branded dialogs, `role=status` flash messages with Undo, global double-submit protection with `aria-busy`, a reduced-motion reset, branded 404 and 500 pages, and `aria-label` on icon buttons.
- **Layout.** No sideways overflow on any of the 54 visits. Safe-area insets on the phone. Each page title reads "X · Lightning".

## Recommended order

1. **BV-3BB** (S). The only finding that can cause an unintended delete. Fix it first.
2. **IV-3BC + IT-3BE** (M + S). Plurals and one number format. These are high-frequency, low-risk, and every page benefits.
3. **IV-3BG** (S). Phone finish, including the Arabic chevrons. Most of it is CSS.
4. **IV-3BD** (M). Errors in the user's language on a branded surface. Wrong-language errors cost the most trust.
5. **IV-3BF** (M). PC finish: focus, validation wells, fonts, scrollbars, amount-first Add, token drift.
6. **IV-3BH** (M). Words. Rename gradually; one PR per term so the Arabic and the tests follow.
7. **IT-3BI** (M). Arabic search and sorting, then the calendar and clock.
8. **OW-3BJ.** Owner decisions. Nothing in 1–7 waits on them; decide before the next guideline version.

**Acceptance for the whole report.**

- Rerun `evidence/probe.py`. It should show 0 hyphen minus, 0 "1 …s" plurals, 0 Latin words on Arabic pages other than names, a focus ring on every one of the first six tab stops on PC and phone, and no unbranded response.
- Run `tests/test_mohab_year.py` and check A16 for each visible change.
- Do one Windows WebView2 pass (scrollbars, High Contrast, spellcheck) and one Android pass (tap highlight, overscroll, status bar) when IV-3BF and IV-3BG land, not before.

## Validation

- `python issues/3-polish-and-arabic/r28-international-polish/evidence/probe.py` ran to completion: 54 page visits plus Add focus and dark-mode checks.
  - Every page returned HTTP 200. The deliberate `/does-not-exist` returned 404, and its only console error is that 404.
- `pytest tests/test_arabic_no_english.py tests/test_arabic_number_display.py`: 18 passed.
- Screenshots are viewport-only, quantised to 256 colours to keep the repository small.

## Dated follow-ups

None yet.

## Follow-up · 2026-11-08 · Codex

BV-3BB: delete markers now explicitly select danger tone and the translated Delete label, including local category and counterparty handlers and the category edit page. English and Arabic question marks split the title and explanation. The complete category and counterparty warnings have Arabic. Browser tests cover both languages: Enter cancels without sending a delete, an explicit Delete sends it once, and marked deletes stay dangerous regardless of wording. Evidence: `tests/test_confirm_dialog_browser.py`.
