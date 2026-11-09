---
title: Paid themes barely reach the phone - the hero parts are PC-only, Papyrus has no motion there, and Cotton paints Add rose
type: polish
pillar: feel
size: M
model: opus
status: ready
created: 2026-11-09
by: Claude Opus 5.5
---

## Report

Report [r29](../11-phone-ux/r29-google-play-readiness/report.md) H1-H3, shots `themes-home.jpg`, `themes-money.jpg`. On the phone
the lead figure has no card (C06.2) and `theme-materials.css:243` gives it no artwork, so lacquer, foil edge, glint, winged disc and
lotus line never show; rows are flat, so card parts have nothing to dress. `document.getAnimations()` on Papyrus's phone Home is
empty, though Papyrus is sold in the animated tier; Dendera runs its pigment thread. Cotton's Add disc is rose-red (A03: rose is bad
money).

## Fix

Design first (owner picks, then `guideline/themes.md` §4 in both repos): give each paid theme a phone signature on surfaces the
phone has: the hero's ground band (a full-width band behind Safe to spend that takes `hero-finish`, `hero-artwork` and `hero-sheen`),
the header thread for Papyrus on the phone (its one continuous motion), and the tab bar's active mark. Cotton's Add takes its accent
only if the accent is not rose; otherwise Ink.
Done when: `python tools/phone_check.py --theme <id>` for each paid theme prints nothing, `getAnimations()` shows exactly one
continuous animation for each animated-tier theme on phone Home, and screenshots against the default show no layout shift.
