---
title: A profile exported from Lightning must import into another profile, and read as the app reads
type: bug
look: technical
severity: medium
pillar: own
size: L
status: ready
created: 2026-11-06
by: Claude Opus 5.5
skills: number-audit
app_version: 2.0.3
commit: 4af457b
repo: app
---

## Report

The [profile export/import audit](../../reports/2026-11-06-profile-export-import/report.md) found the export is the
database table by table (59 sheets, row IDs, every fact twice) and the import works only into an untouched database
with the exact bytes and version. It fails after the welcome page's currency step, after a spreadsheet app saves the
file, for a file from an older Lightning, and for the CSV choice. Reproduce:
`python reports/2026-11-06-profile-export-import/evidence/roundtrip.py`. The report's *Proposed architecture* is the
design; these steps follow it. Built nothing yet. Owner decided 2026-11-06: one profile file (readable and importable); unfinished statement reviews stay behind, counted in Read me.

## 2AJ1 The profile file format · L
A versioned format (Format 1) of ten named sheets with Read me check figures; names in references, the existing
stable keys as No., no row IDs, one column per fact; export writes it. Done when: Mohab's export has ten sheets and no
`*_id` column.

## 2AJ2 A reader spreadsheet apps cannot break · M
Blank text is empty text, numbers, dates and booleans in any spreadsheet form, free column order, format upgraders,
unknown columns listed and ignored. Done when: report F4 and F5 files import.

## 2AJ3 Load records, not tables · L
Resolve names to new local IDs, write through the domain layer (journal commands on a synchronized profile),
rebuild derived data; "empty" means no user records, so the welcome choices do not block. Done when: report F3
imports and the check figures match after confirm.

## 2AJ4 Export and import pages · S
One "Profile file" choice, CSV labelled for reading only, the review shows check figures side by side, the upload
is held server-side instead of round-tripping in the page. Done when: report F6 and F9 are gone.

## 2AJ5 Round-trip acceptance · M
Every sample through the routes into a welcomed profile, after a re-save, and from the previous format's fixture;
Mohab moves his year into a new profile. Done when: the test runs in CI and replaces today's one-account round trip.

Order: 2AJ1, 2AJ2 with 2AJ3, then 2AJ4 and 2AJ5.
