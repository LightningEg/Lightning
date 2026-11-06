---
title: Import another app's export with few questions
type: polish
look: technical
pillar: capture
size: M
status: new
created: 2026-11-05
by: Claude Opus 5.5
skills: feedback-review
---

## Report

A 377-row export from another tracker stopped 142 rows for review
([feedback FB1](../../feedback/2026-11-05-csv-import-and-phone-update.md)).

## Built 2026-11-05

Group column, balance rows as Skip, and one list of the file's unknown category names
(`tests/test_import_other_app_exports.py`; Architecture › CSV import).

## 7Z1 Remember a name's category for the next file · S

What the person picks in "Your file's categories" is saved per account, keyed by the name, so next month's file
from the same app resolves it before review. Test: a second file posts with no choices.

## 7Z2 Split one file by its Account column · M

A mapped Account column sends each row to the matching account (or asks once per unknown name), so a whole-app
export is one upload, not one per account.

**Safe part built 2026-11-06:** a row whose Account column names another of your accounts (by label, code, name or a unique institution) is an error row and never posts here. Open: the actual split into one batch per account.

## 7Z3 Paired rows of one movement · S

Two rows on one day with opposite amounts and the same note ("Ownership from … | Ownership to …") or a copy of a
transfer ("Transfer out | …") are offered as one, not two postings.
