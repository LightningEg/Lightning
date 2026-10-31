---
title: Journal code - two pairing clients
type: tech
pillar: build
size: M
status: ready
created: 2026-10-28
by: Claude
commit: 9ca53bd
repo: app
---

## Report

Audit 9 B8: `../../reports/2026-10-28-loose-ends-and-linking/report.md`. No behaviour changes; under the journal claim in `NOW.md`. 4K1-4K3 and 4K5 were done on 2026-10-28 (branch `claude/sync-errors-and-journal-tidy`, `tests/test_journal_tidy.py`).

## 4K4 One pairing client · M

`runtime/journal_enrollment.NewJournalReplica` and `runtime/journal_pairing.NearbyPairing` repeat find, join, resume, compare, prove, finish and cancel. Not merged in 4K: they differ in behaviour, not only in storage (an enrollment slot file against `journal_local`). On "waiting", `resume()` asks the home for status in enrollment but leaves it to `finish()` in nearby pairing; `compare()` checks the offer before or after the failed flag; cancel and finish have different preconditions (an encrypted copy being installed; membership accepted in place). One driver needs those choices made first, with the owner or in 4A, then a store interface both use.

## Note

Lending (`lightning/sync/*.py`) is still live; its retirement after J6 needs an item then. `runtime/journal_setup.py` still uses `open_lab`: it is the dummy-lab enrollment tool and only accepts a lab marked dummy.
