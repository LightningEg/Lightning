---
title: Budget's Needs attention lists categories that are finished, repeats them below, and in Arabic a zero left reads as a dot
type: bug
look: visual
severity: medium
pillar: plan
size: S
model: sonnet
status: ready
created: 2026-11-09
by: Claude Opus 5.5
---

## Report

Report [r29](r29-google-play-readiness/report.md) T5-T7, shots `en-budget.jpg`, `ar-budget.jpg`. Needs attention shows Health
900 of 900, Housing 12,000 of 12,000, Loans 2,500 of 2,500 (0 left) and Food; Your categories then lists them all again. In Arabic
"0" is "٠", a dot, so four rows end in "•". All bars are one blue.

## Fix

Files: `lightning/ui/phone/screens/budget.py` (or the Budget screen builder), `lightning/ui/templates/phone/budget*.html`, `phone.css`.
Needs attention holds only categories over plan or ahead of their pace; a category at exactly its plan with nothing left is done
(a quiet "Paid" or "—", never "٠" alone); a category shown in Needs attention is not repeated under Your categories; bars take state
colours (at plan quiet, ahead of pace amber, over rose).
Done when: a test on Mohab's month shows no fully-spent fixed category in Needs attention, no category twice, and no row whose
remaining text is a lone 0.
