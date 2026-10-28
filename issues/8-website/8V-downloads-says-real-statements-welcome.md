---
title: Downloads tells visitors their real statements are welcome while real-money safety is unfinished
type: bug
area: website
status: ready
created: 2026-10-28
by: Claude
repo: website
commit: e8153a1
---

## Report

`current-status.html` (and `ar/current-status.html`) says under the buttons: "Version 1.5.0 is ready to use: your real statements are welcome." AGENTS.md §4 says dummy data only until ordinary-PC acceptance, legacy import and backup restore are done, and milestone 2 (2A restore safety, 2C, the held 2B drill in Project Overview §9) is open. The same page a section lower says "Keep your own backup if you test with real data", so the page contradicts itself too. The line came with the rewards work (site commit 7b4dbda), not an owner decision on record.

## Fix

Say what holds: "Try it with Mohab's sample year first; if you use your own statements, keep your own backup" (and Arabic). Change it when milestone 2 is done. If the owner has decided real data is fine now, record that in Project Overview §2 and change AGENTS.md §4 instead.
