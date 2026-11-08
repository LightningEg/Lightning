---
title: Phone finish - chevrons point forward in Arabic, quiet links 44 px tall, no tap flash or page bounce, tinted status bar
type: polish
pillar: everywhere
size: S
status: new
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
