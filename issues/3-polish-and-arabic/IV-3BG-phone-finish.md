---
title: Phone finish - chevrons point forward in Arabic, quiet links 44 px tall, no tap flash or page bounce, tinted status bar
type: polish
pillar: everywhere
size: S
model: sonnet
status: ready
created: 2026-11-08
by: Claude
---

## Report

Report [r28](r28-international-polish/report.md) F2, F13, F14 (phone side).

- **Arabic chevrons point backwards:** "ادفع ›", "مراجعة ›" on Home's To do ([shot](r28-international-polish/evidence/shots/phone-ar-home.png)); 105 `›` text glyphs in templates (`phone/home.html:15-16`, `phone-chevron` ×23); only some SVG chevrons are flipped (`phone.rtl.css:47`, `style.rtl.css:3256`).
- **Small targets:** 12 quiet links under 24 px tall in phone Settings (probe `phone en /settings`); C05 says quiet links 44 tall.
- **Touch polish missing in `phone.css`:** `-webkit-tap-highlight-color`, `overscroll-behavior` on the body, `user-select:none` on the tab bar and buttons; no `<meta name="theme-color">` in `phone/base.html`; `enterkeyhint` once in all phone forms.

## Fix

One SVG chevron partial, flipped under `[dir=rtl]`, replacing the `›` glyphs; Settings links as 44 px rows; the CSS and meta above; `enterkeyhint="done|next|search"` on phone fields. Tests: `tools/phone_check.py --arabic` gains a check that no visible `›` text glyph remains and that links are at least 44 px tall; owner's Android check with IV-3AY13, not before.

## How to work on this item

Each step is one pull request. Read only the files a step names; never open `guideline/app.html` whole (use `python tools/guideline.py C05`). Run the step's test command, then for a visible change `python -m pytest tests/test_mohab_year.py tests/test_mohab_phone.py -q` and check A16/C12 on a screenshot; delete the step's heading in the same commit.

## 3BG1 One chevron that points forward in both languages · S · #421
Files: new `lightning/ui/templates/partials/chevron.html` (a macro), the phone templates from `grep -rln "›" lightning/ui/templates/phone` (e.g. `phone/home.html:15-16`, `phone/planning/plan.html:76,82,110`), `lightning/ui/static/phone.css` (`.phone-chevron` ~line 329); the RTL stylesheet is generated with `node tools/build_rtl_css.js`.
Do: macro `chevron()` renders `<svg class="chevron" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/></svg>`. The existing RTL rule `html[dir="rtl"] svg:has(> path[d="M9 6l6 6-6 6"]) { transform: scaleX(-1); }` (style.rtl.css:3256) already flips it; add the same rule to the phone RTL source if it is missing. Replace every `<b>›</b>` and `<span class="phone-chevron" aria-hidden="true">›</span>` with the macro inside the same span. Keep `.phone-row-more[open] .phone-chevron { transform: rotate(90deg) }` working (rotate the svg). The CSS `content: "›"` in `phone.css:573` becomes a mask or stays only if it is flipped under `[dir=rtl]`.
Done when: `grep -rn "›" lightning/ui/templates/phone` returns nothing that is drawn as an arrow, and `tools/phone_check.py --arabic --shots <dir>` home shot shows the chevrons pointing left. Add to `tools/phone_check.py` a check that no visible text node equals "›". `python -m pytest tests/test_phone_check.py -q`.

## 3BG2 Quiet links are 44 px tall · S · #422
Files: the phone Settings template (find it: `grep -rln "Sale factors" lightning/ui/templates/phone lightning/ui/templates/settings`), `lightning/ui/static/phone.css`.
Do: the plain links in Settings (Sale factors, Budget settings, Financial health limits, Financial assets, Target allocation, Price files, Rules, Categories) become rows: `display:flex; align-items:center; min-height:44px` (C05.1 "Quiet link · 44 tall"), with the chevron from 3BG1 if 3BG1 is merged.
Done when: `tools/phone_check.py` gains a check that every visible `a`/`button` on the listed pages is at least 44 px tall (allow checkboxes inside a 44 px label), and `python tools/phone_check.py` prints nothing for `/settings`.

## 3BG3 No tap flash, no page bounce, no selected buttons · S · #423
Files: `lightning/ui/static/phone.css` (top of file).
Do: `html.phone { -webkit-tap-highlight-color: transparent; overscroll-behavior-y: none; }`, `html.phone .phone-tabbar, html.phone button, html.phone .btn, html.phone summary { -webkit-user-select: none; user-select: none; }`, and a visible `:active` state instead of the flash: `html.phone :is(a, button, summary):active { opacity: .7; }` unless a component already has one (`grep -n ":active" lightning/ui/static/phone.css`). Keep `overscroll-behavior: contain` on the inner lists that already have it.
Done when: a test in `tests/test_phone_check.py` (or a new small browser test) reads `getComputedStyle(document.documentElement).overscrollBehaviorY === "none"` and the tab bar's `userSelect === "none"` on `/home`. Owner's Android check comes with IV-3AY13.

## 3BG4 Status bar colour and keyboard Enter key · S · #424
Files: `lightning/ui/templates/phone/base.html` (meta tags ~line 7-9), the phone form templates (`grep -rln "<input" lightning/ui/templates/phone`).
Verify first: #393 made the Android status bar follow the theme natively; open `lightning/ui/templates/phone/base.html` and `android/` for `theme-color`/`statusBar`. If the native side already tints it, only add the meta for the browser build.
Do: `<meta name="theme-color" content="{{ theme_bar_colour }}">` using the colour the page's top bar uses (read it from the theme tokens the template already has; fall back to the guideline's app-bar colour, `python tools/guideline.py C02`). Add `enterkeyhint`: `next` on fields followed by another field, `done` on the last field of a sheet, `search` on search boxes (one already does: `phone/search.html:10`).
Done when: `grep -c "enterkeyhint" -r lightning/ui/templates/phone` covers every phone `<form>`'s text/number inputs, and the rendered `/home` has a `meta[name=theme-color]`. `python -m pytest tests/test_mohab_phone.py -q`.
