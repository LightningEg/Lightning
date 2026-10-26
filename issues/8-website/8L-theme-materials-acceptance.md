---
title: Theme materials - owner review, website parity and native acceptance
type: feature
area: appearance
status: building
created: 2026-10-26
by: Claude
skills: guideline-audit
repo: app
---

## What shipped

The app's material system (owner asked 2026-10-26: textured backgrounds, cards and animation, never a palette swap): every element in `theme-kit/README.md` › Element inventory states paint, material and motion, chosen from a reviewed recipe library (`theme-materials.css`, `slots.json` schema 2). The validator refuses a missing layer, an off-list value, a second continuous motion and text under 4.5:1 at a surface's worst point. Two references: Cotton (light, new) and Nile Papyrus & Lapis Guilloché (dark, redone). `tools/theme_shots.py` captures the roster.

## Still to do

1. **Owner review.** Cotton and Nile on PC and phone, motion on (`tools/theme_shots.py OUT --motion`, or Settings → Appearance). Decide: keep the rules in `guideline/themes.md` §7 as written; a **Material** tier and its price (themes.md §7 lists Palette, Textured, Animated).
2. **Website parity.** The website validator (`js/cosmetic-parts.js`) and its copy of the app manifests still read schema 1; move them to schema 2. The site's `css/textures.css` should draw the same recipes (papyrus, linen, laid, film) so a theme looks the same bought as worn.
3. **Upgrade the palette themes.** Nile Nocturne and Royal Obsidian & Gold are schema 2 but wear `flat`/`none`; give each a material, or leave them as the Palette tier.
4. **Native acceptance** (8J): WebView2 and Android paint, cost of grain and blur on a low-end phone, Arabic mirroring of artwork and glow, forced colours.
5. **Pre-existing, seen in every dark theme:** the app's own green on dark cards (for example "+311,804 this year") reads low; money colours are not theme parts, so the fix belongs to the dark adapter in `theme-surfaces.css`.

## Done when

The owner accepts both references, the website reads schema 2 with matching textures, and 8J's native checks pass for them.
