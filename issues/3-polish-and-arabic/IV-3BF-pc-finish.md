---
title: PC finish - one focus ring, branded validation, only the brand's fonts, styled scrollbars, amount-first Add and fewer one-off styles
type: polish
pillar: feel
size: M
model: sonnet
status: ready
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

## How to work on this item

Each step is one pull request. Read only the files a step names; never open `guideline/app.html` whole (use `python tools/guideline.py A10`). Run the step's test command, then for a visible change `python -m pytest tests/test_mohab_year.py -q` and check A16 on a screenshot; delete the step's heading in the same commit.

## 3BF6 One set of icons · M · #419
Files: `lightning/ui/templates/partials/` (new `icons.html` macro file), templates found by `grep -rln "›\|×\|⋯" lightning/ui/templates --include=*.html` (PC ones; the phone is IV-3BG1), `lightning/ui/static/style.css`.
Needs 3BG1 merged first. It creates the chevron macro; reuse it.
Do: macros `icon_close()`, `icon_more()` as 20 px SVG with `stroke-width="1.75"` (A15); replace the text glyphs in PC templates; make every `stroke-width` in templates and CSS 1.75 (`grep -rn 'stroke-width' lightning/ui`). Give "Profiles & lock" in the side nav an icon like its neighbours (a lock, same size).
Done when: `grep -rn "›\|×\|⋯" lightning/ui/templates --include=*.html | grep -v "^.*phone/"` returns only text where the glyph is content (e.g. in a sentence), and `grep -rhn 'stroke-width="[02-9]' lightning/ui` is empty.

## 3BF7 Styles from tokens · M · #420
Files: `lightning/ui/static/style.css`, `lightning/ui/static/phone.css`, `lightning/ui/templates/transactions/detail.html:32,49,61`, `lightning/ui/templates/investments/prices.html`.
Do, in this order, one commit each: (a) replace each hex colour that equals a token's value with `var(--token)` (list tokens with `grep -n "^\s*--" lightning/ui/static/style.css | sed -n 1,200p`; e.g. `#097852` → `var(--positive)`, `#C93D72` → `var(--rose)`, `#0B6DD6` → `var(--azure)`); (b) replace `style="margin-top:14px|16px"` with the spacing utility the guideline names (`python tools/guideline.py A15`); (c) add `--z-sticky: 20; --z-popover: 100; --z-dialog: 1000; --z-toast: 1200` and map existing z-index values to the nearest. Do not change any value's look.
Done when: `grep -cE "#[0-9A-Fa-f]{6}" lightning/ui/static/phone.css` falls from 92 to the tokens' own definitions only, `grep -c 'style="' -r lightning/ui/templates` falls by the margin ones, and `python tools/theme_check.py` (read its header) and `python tools/phone_check.py` report nothing new.
