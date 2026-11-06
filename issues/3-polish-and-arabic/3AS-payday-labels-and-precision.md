---
title: Payday funding labels and amount precision must remain readable
type: bug
look: visual
severity: low
pillar: feel
size: S
status: new
created: 2026-11-05
by: Codex
skills: guideline-audit
app_version: 1.5.4
commit: a7ff8d8
repo: app
post: no
---

## Report

Phone payday renders Eating OutFunded spending left without visual separation and a reserve suggestion as 60420.110000. Separate label/state/input and format monetary fields at currency precision. Check English/Arabic and enabled/disabled funding states. Broader workflow simplification stays with IV-3G/IV-3AN.

Evidence and acceptance: [desktop and phone UX audit, F12](../../reports/r24-desktop-phone-ux/report.md). Dummy data only. This is an audit finding; no implementation change is included.

