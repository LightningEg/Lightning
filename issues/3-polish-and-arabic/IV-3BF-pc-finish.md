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

## 3BF1 One focus ring, also in High Contrast · S
Files: `lightning/ui/static/style.css` (rules at ~326, ~333, ~1083, ~2003, ~2120, ~3033, ~3037), `lightning/ui/static/profiles.css` (~32, ~80). The RTL files are generated: run `node tools/build_rtl_css.js` after editing (read its header for usage).
Do: add one token in the guideline `:root` (~line 1000): `--focus-ring: 0 0 0 3px rgba(11,138,95,.28)` (the colour already used). Add one rule `:where(a, button, summary, input, select, textarea, [tabindex]):focus-visible { outline: 2px solid transparent; box-shadow: var(--focus-ring); }` and `@media (forced-colors: active) { :focus-visible { outline: 2px solid CanvasText; } }`. Remove the per-control focus rules listed above when they only repeat this; at ~326/333 keep the background tint but stop removing the outline on `:focus-visible`.
Done when: new `tests/test_focus_browser.py` (profile set-up as in `tools/phone_check.py` lines 70-97, PC app) presses Tab 8 times on `/` and `/transactions` and asserts each focused element has a non-`none` box-shadow or outline; with `page.emulate_media(forced_colors="active")` the outline is not `none`. `python -m pytest tests/test_focus_browser.py -q`.

## 3BF2 Only the brand's fonts · S
Files: `lightning/ui/static/style.css` lines ~17-45 (legacy `:root` and font stacks), ~118, ~128, ~214, ~799-800; `lightning/ui/static/profiles.css` ~36, ~49, ~51; `lightning/ui/static/fonts/fonts.css`.
Do: replace "Inter" and "Plus Jakarta Sans" in every `font-family` with the A06 faces (Manrope for text, "Bricolage Grotesque" for headings and figures), and "JetBrains Mono" with `ui-monospace, Consolas, monospace`. Delete those faces' `@font-face` blocks and their files under `static/fonts/` only if nothing else references them (`grep -rn "Inter\|Jakarta\|JetBrains" lightning`). Font weight 650 becomes 600 or 700 (pick the nearer the design: headings 700, labels 600).
Done when: that grep is empty except comments, `grep -rn "font-weight: *650\|font-weight:650" lightning/ui/static` is empty, and `python -m pytest tests/test_brand_audit.py -q` has no new failure (one, `test_links_are_ink_and_underlined`, already fails on main). Compare the profiles screen before/after on a screenshot.

## 3BF3 Windows chrome: scrollbars, selection, spellcheck, balanced headings · S
Files: `lightning/ui/static/style.css` (append to the guideline layer), the templates with name inputs: `grep -rln 'name="name"\|name="counterparty"\|name="notes"' lightning/ui/templates`.
Do: `html { scrollbar-color: var(--c-line, #C9D6D2) transparent; scrollbar-width: thin; scrollbar-gutter: stable; }`; `::selection { background: <the guideline's soft Nile/green wash token>; color: inherit; }` (find the token with `python tools/guideline.py A03`); `h1, h2, h3 { text-wrap: balance; }`, `p { text-wrap: pretty; }`. Add `spellcheck="false" autocomplete="off"` to name, counterparty, merchant and account-name inputs (not to notes).
Done when: `grep -c 'spellcheck="false"' -r lightning/ui/templates` rises from 11 to cover every input from the grep above, and a screenshot of `/transactions` shows the thin scrollbar. `python -m pytest tests/test_pc_layout_browser.py -q`.

## 3BF4 PC Add starts on the amount, says its name once · S
Files: `lightning/ui/templates/transactions/form_popup.html` (amount input at line ~28), the PC route `lightning/ui/routes/accounts.py:446`.
Verify first: open `/accounts/1/transaction/new` on the PC app; if the amount already has focus, delete this step.
Do: move the Amount field to the first row (beside Date), add `autofocus` to `#popup-amount` (the phone template `phone/transactions/form_popup.html` already does), remove `placeholder="0.00"` (A06.1: no 0.00 pretending to be data), and drop the inner card title "Add transaction" (the page title already says it; A16 "a line that repeats its label"). Find and remove the empty well above the buttons (inspect the element just before `.actions`).
Done when: new `tests/test_pc_add_focus_browser.py` opens the page, types `120` and asserts `input[name=amount]` has value `120`; saving with a category creates one transaction of 120 (check `/transactions`). Screenshot shows one "Add transaction" heading.

## 3BF5 Our message, not the browser's bubble · M
Files: `lightning/ui/static/app.js` (~261, ~755, ~800), `lightning/ui/templates/partials/macros.html` (the `err()` macro), `lightning/ui/templates/base.html` and `phone/base.html`.
Do: add `novalidate` to every `<form>` by setting `form.noValidate = true` for all forms on load in `app.js` (one place); on submit, if `!form.checkValidity()`, prevent it, and for each invalid field show the `err()` well's markup under the field (`aria-invalid="true"`, `aria-describedby` pointing at the message) with the field's `validationMessage` replaced by our sentence ("Enter an amount.", "Choose a category.", "Pick a date.") from a small map keyed by `name`; focus the first invalid field. Remove `reportValidity()` at ~800.
Done when: `tests/test_pc_add_focus_browser.py` gains a case: Save with an empty amount shows `.field-error` (or the class `err()` uses) with "Enter an amount." and the amount is focused; no native bubble (assert `page.evaluate("document.querySelector('input:invalid')")` is the focused one and the error element is visible).

## 3BF6 One set of icons · M
Files: `lightning/ui/templates/partials/` (new `icons.html` macro file), templates found by `grep -rln "›\|×\|⋯" lightning/ui/templates --include=*.html` (PC ones; the phone is IV-3BG1), `lightning/ui/static/style.css`.
Needs 3BG1 merged first. It creates the chevron macro; reuse it.
Do: macros `icon_close()`, `icon_more()` as 20 px SVG with `stroke-width="1.75"` (A15); replace the text glyphs in PC templates; make every `stroke-width` in templates and CSS 1.75 (`grep -rn 'stroke-width' lightning/ui`). Give "Profiles & lock" in the side nav an icon like its neighbours (a lock, same size).
Done when: `grep -rn "›\|×\|⋯" lightning/ui/templates --include=*.html | grep -v "^.*phone/"` returns only text where the glyph is content (e.g. in a sentence), and `grep -rhn 'stroke-width="[02-9]' lightning/ui` is empty.

## 3BF7 Styles from tokens · M
Files: `lightning/ui/static/style.css`, `lightning/ui/static/phone.css`, `lightning/ui/templates/transactions/detail.html:32,49,61`, `lightning/ui/templates/investments/prices.html`.
Do, in this order, one commit each: (a) replace each hex colour that equals a token's value with `var(--token)` (list tokens with `grep -n "^\s*--" lightning/ui/static/style.css | sed -n 1,200p`; e.g. `#097852` → `var(--positive)`, `#C93D72` → `var(--rose)`, `#0B6DD6` → `var(--azure)`); (b) replace `style="margin-top:14px|16px"` with the spacing utility the guideline names (`python tools/guideline.py A15`); (c) add `--z-sticky: 20; --z-popover: 100; --z-dialog: 1000; --z-toast: 1200` and map existing z-index values to the nearest. Do not change any value's look.
Done when: `grep -cE "#[0-9A-Fa-f]{6}" lightning/ui/static/phone.css` falls from 92 to the tokens' own definitions only, `grep -c 'style="' -r lightning/ui/templates` falls by the margin ones, and `python tools/theme_check.py` (read its header) and `python tools/phone_check.py` report nothing new.
