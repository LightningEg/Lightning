---
title: Dendera does not yet look or move like a 1,000-coin animated theme
type: polish
look: visual
pillar: feel
size: L
status: ready
created: 2026-11-02
by: Claude
skills: guideline-audit
repo: app
post: no
---

## Report

Audit: `reports/2026-11-02-dendera-premium-audit/report.md`. Its four broken motions (F1-F4) are fixed in the commit
that filed this item. What remains is that the theme does not read as premium: its one continuous motion is a 1 px
line, the frieze reads as dots, the hero has two competing watermarks, charts stay in the default's azure, the night
"gold leaf" is lavender, and the checks cannot tell a motion that paints from one that does not. Post: no; owner
design decisions come first (steps marked owner).

## Fix

Steps below, in order. Each keeps `guideline/themes.md` §6-7: one continuous motion (8 s or more), nothing on a number,
no element moved (`tools/theme_check.py`), and reduced motion stops on a still frame. Any recipe change is app code that
serves every theme. A change to the guideline or a website copy lands in both repos.

## 10F0 Approve the look · owner
Approve steps 1-3 and 5 from the report's proposal (the signature thread, frieze, lintel disc and gold leaf), and answer
10F7. A mock-up per step goes into `theme-kit/plans/dendera.html` before code.

## 10F1 A signature thread people notice · M
Paint the pigment thread 2 px in gold leaf (the hero pigment) with a soft glow under the seam. The light should always be
somewhere on the bar (no dead two thirds of the cycle) and keep its 14 s and its one-strip repaint. Done when the motion
probe shows motion on every 1 s sample and `theme_check.py` passes.

## 10F2 A real lotus frieze · M
Redraw `cosmetics/assets/dendera/lotus-frieze.svg`: alternate bud and open flower between two register lines, at about
twice the size, inside the header's existing bottom padding. Done when it reads as lotus at 100% on the PC and at 360 px.

## 10F3 The winged disc as a lintel · S
Hero artwork `winged-disc` sits centred across the hero's top edge, and Lightning's own watermark mark is hidden when a
theme brings hero artwork. Contrast is rechecked at the worst point by the build.

## 10F4 Charts wear the theme · M
Read `--theme-chart-grid` and `--theme-chart-accent` (generated, read by nothing today) in the chart styles for grid
lines and nonfinancial lines and fills only; money series keep their colours. Every paid theme benefits.

## 10F5 Gold leaf at night · M
Add a `gold-leaf` finish (foil drawn from the hero pigment) to the recipe library, `slots.json` and the kit's README, and
use it for Dendera night's tabs and primary button. Change the night hero grain from `fibre` to `paper`, and raise the
star ceiling to a visible strength. Contrast passes on both ends of the leaf.

## 10F6 Phone calm · S
On the phone, Dendera's cards take depth `low` and the ground artwork stays clear of list rows (themes.md §6).

## 10F7 Choose night, not only follow it · owner
Should Settings offer Day, Night and Follow this computer for a theme with a night version? If yes, it is an S step in
`theme-runtime.js` and Settings.

## 10F8 Checks that see a dead motion · S
Move `reports/2026-11-02-dendera-premium-audit/evidence/motion_probe.py` into `tools/theme_check.py` (each declared
motion must change pixels). Let `tools/theme_shots.py` capture a night version through the follow-night switch with a
dark colour scheme.
