---
title: The full Add page behind the sheet is titled with an account, lights Money, opens on an Import switch and uses an emoji
type: polish
pillar: capture
size: S
model: sonnet
status: ready
created: 2026-11-09
by: Claude Opus 5.5
---

## Report

Report [r29](r29-google-play-readiness/report.md) T8, shot `en-add.jpg`. The Add tab's sheet is right. The page
`/accounts/add-transaction` (opened by links and when the sheet cannot open) shows "‹ CIB Payroll" as its title, lights Money in
the tab bar, puts an Import / Accounts / Held for others switch above the form, and draws "📋" on Paste SMS.

## Fix

Files: the phone template that renders `/accounts/add-transaction` (find with `grep -rn "Held for others" lightning/ui/templates/phone`), `phone/base.html`.
Title "Add", Add lit, the form first (the switch moves to a "⋯" or below Save), the clipboard drawn with the app's icon set.
Done when: a test renders the page and finds the title "Add", `aria-current` on the Add tab and no emoji character.
