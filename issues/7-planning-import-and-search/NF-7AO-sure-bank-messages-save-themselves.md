---
title: Bank messages Lightning is sure about save themselves, marked and undoable
type: feature
pillar: capture
size: L
model: opus
status: new
created: 2026-11-09
by: Claude
skills: bug-hunt
app_version: 2.1.2
commit: 90f0190
repo: app
---

## Report
[r31](r31-logging-entries/report.md) F3 (owner decision 2026-11-09: auto-save the sure ones; it replaces "nothing is posted without
review" for these messages only). Today every message waits on the review screen, and a shop seen for the first time
is "Needs you" even after the tenth visit is categorised the same way.

## 7AO1 What "sure" means, and the service · M
A message saves itself only when all hold: a named bank pattern read it (`sure=True`, never the general rule); its
card or account ending is already assigned; the payee has a category by rule or habit (transfers and salary by their
kind); it is not a possible duplicate of a ledger row; the profile is the journal's home (synchronized profiles post
once). Everything else goes to review as now. One code path: the review's own post, called for the sure rows.
**Done when:** tests cover each condition failing into review.

## 7AO2 Seen, marked, undoable · M
A saved message shows "From SMS" on its row with the message text behind it; Home says "3 saved from SMS · Undo"
until dismissed; a list of the last 30 with Undo each. Architecture and the SMS page's wording change with it.

## 7AO3 Not twice · M
The same payment typed by hand (or pasted) before its message arrives must match, not double: same account, amount
and day within the pairing window links the message to the entry instead of posting. Shares the duplicate work of NF-4B5.
