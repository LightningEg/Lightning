---
title: The phone's + button sits over amounts in lists
type: polish
area: phone
status: new
created: 2026-10-21
by: Claude Sonnet 5.5
skills: site-recapture
app_version: 1.3.0
commit: 6e1c043
repo: app
---

## Report
On the phone (360 wide), the round + button (`.phone-add`) is fixed at the bottom right (left in Arabic) and covers part of whatever is under it: on an account page it hid "-3,410.00" and the balance line, on Overview the "As of" date and the next row's amount, on Cash planning the end of the safe-to-spend bar. A figure half hidden is a fault for any screenshot (website B12) and for the person reading. The website captures scroll until the button sits between rows, and for the 2026-10-21 set it did.

## Fix
Give lists room: keep the last row clear of the button (bottom padding), or let the button hide while scrolling. Check Overview, Cash planning and an account page, English and Arabic.
