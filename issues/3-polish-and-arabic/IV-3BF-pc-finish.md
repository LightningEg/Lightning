---
title: PC finish - one focus ring, branded validation, only the brand's fonts, styled scrollbars, amount-first Add and fewer one-off styles
type: polish
pillar: feel
size: M
status: new
created: 2026-11-08
by: Claude
---

## Report

Report [r28](r28-international-polish/report.md) F8-F12, F14, F15 (PC side). Each step is small and can ship alone:

1. **Focus:** no shared `.btn:focus-visible`; inputs use `outline:0` + box-shadow (`style.css:1083`, `:3033`, `:3037`; `profiles.css:32,80`), invisible in Windows High Contrast (`forced-colors`: 0 rules); `style.css:326,333` remove the outline on `:focus`.
2. **Validation:** 224 `required`, 0 `novalidate`; `reportValidity()` (`app.js:800`) and `setCustomValidity` (`:261`, `:755`) show Chromium bubbles instead of the A10 rose well; `aria-describedby` used twice.
3. **Fonts:** Inter, Plus Jakarta Sans and JetBrains Mono still declared (`style.css:29-45`, `profiles.css:36,49,51`); the profiles/lock screen uses Plus Jakarta. A06 allows Bricolage Grotesque and Manrope only (Readex Pro, Noto Sans Arabic in Arabic). Weight 650 and 400 appear beside the guideline's 500/600/700/800.
4. **Windows chrome:** no `scrollbar-color`/`scrollbar-gutter`, no `::selection`, `spellcheck="false"` on 11 of 951 inputs (names and counterparties get red squiggles); no `text-wrap: balance` on headings.
5. **Add (r27 J1, PC):** `/accounts/{id}/transaction/new` focuses nothing, the amount is the fourth field with placeholder "0.00", and "Add transaction" appears as page title, card title and button; an empty well sits above the buttons ([shot](r28-international-polish/evidence/shots/pc-en-accounts-1-transaction-new.png)).
6. **Icons:** text glyphs `›` `×` `⋯` beside SVG; stroke widths 1.75–3 where A15 says 1.75; "Profiles & lock" is the only side-nav item without an icon.
7. **Token drift:** 13–14 font sizes per page; 9–12 radii; 139 inline `style=` (`transactions/detail.html:32,49,61` margins); ~294 hex colours outside tokens; 290 `!important`; 27 z-index values. Two `:root` token layers (`style.css:17` and `:1000`).

## Fix

In that order, one PR each: a single `:focus-visible` ring token plus `@media (forced-colors: active)` outline; `novalidate` and the existing `err()` well filled client-side; drop the three off-brand faces and the legacy `:root`; scrollbars, selection, spellcheck and balance; amount first and focused, one title, no "0.00"; SVG chevron/close/more icons at stroke 1.75; replace hex with tokens and inline margins with spacing classes. Tests: `tools/theme_check.py`/guideline-audit for fonts and colours, a browser test that tabs through the first six stops and finds a ring, a test that the Add amount has focus. Check A16 and Mohab after each.
