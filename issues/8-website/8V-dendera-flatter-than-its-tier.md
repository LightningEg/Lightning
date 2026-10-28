---
title: Dendera sells at 1,000 like Papyrus but is flat - no answering motions, flat cards, menus, tabs and dialogs
type: polish
area: appearance
status: new
created: 2026-10-28
by: Claude
commit: dae3aa3
repo: both
---

## Report

The animated tier promises "motions that answer you: a light following the pointer on cards, a sheen on buttons, dialogs rising in" (`guideline/themes.md` §7). Comparing `lightning/ui/static/cosmetics/dendera.json` with `papyrus.json`, Dendera has `cards.hover: none`, `controls.press: none`, `hero.sheen: none`, and `flat` cards, menus, overlays, tabs, navigation and progress at `low` depth, where Papyrus uses satin, foil, lacquer and gloss. Its pigment thread is its one continuous motion, so the gap is in the answering motions and materials, not in adding a second loop.

## Fix

Take it through `guideline/themes.md` §5-6 as a new plan revision in `theme-kit/plans/dendera.html`, using recipes the library already draws:
- Answering motions: `cards.hover: light`, `controls.press: sheen`; dialogs rising in.
- Materials: gold-leaf `foil` on tabs and the cartouche, `satin` cards and menus, `lacquer` dialogs, `gloss` progress, `mid` depth, a `soft` vignette.
- Night mode: the Dendera ceiling - the zodiac ring as a star field, gold on lapis.
- Pair with NF-8T (its banner, frame and name) so the set sells as one.

Do it before any Dendera licence is issued: the version bump locks out buyers until BT-8U1 is fixed. Check contrast at each surface's worst point and `tools/theme_check.py` (no element moves).
