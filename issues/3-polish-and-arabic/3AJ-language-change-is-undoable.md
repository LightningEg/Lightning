---
title: Changing the language is recorded as an undoable action, so Undo switches it back
type: bug
look: technical
severity: low
pillar: feel
size: S
status: ready
created: 2026-10-29
by: Claude
skills: bug-hunt
app_version: 1.5.0
repo: app
github: 167
---

## Report

[#167](https://github.com/LightningEg/Lightning/issues/167) (taken by a contributor; the GitHub issue calls this item 3AI, which is now the logos item). `POST /settings/locale` writes a `settings` row that the undo triggers record, so the header Undo button reverts the language instead of the last money action.

## Fix

Exclude preference writes from undo capture (`lightning/undo.py`, `_EXCLUDED`). Test: switch the language, undo the top group, and the stored `locale` is unchanged while the money action below it reverts.
