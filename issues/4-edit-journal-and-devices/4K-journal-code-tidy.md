---
title: Journal code - two pairing clients
type: tech
pillar: build
size: M
status: ready
post: no
created: 2026-10-28
by: Claude
commit: 9ca53bd
repo: app
---

## Report

Audit 9 B8: `../../reports/2026-10-28-loose-ends-and-linking/report.md`. No behaviour changes; under the journal claim in `NOW.md`. 4K1-4K3 and 4K5 were done on 2026-10-28 (branch `claude/sync-errors-and-journal-tidy`, `tests/test_journal_tidy.py`).

## 4K4 One pairing client · done 2026-11-02

Owner decided (2026-11-02) to keep the stricter behaviour of each: `resume()` asks the home for status while proving or waiting; `compare()` checks the offer before the failed flag; cancel and finish require a started pairing (cancel also refuses once the encrypted copy is being installed). `runtime/journal_pairing_driver.JoiningDriver` now holds resume, compare, prove and cancel once; `NearbyPairing` and `NewJournalReplica` only supply where the state is kept (`_load_join`, `_save_join`, `_clear_join`, `_installing`). Pinned by `tests/test_one_pairing_driver.py`. Native device pairing acceptance stays with 4A.

## Note

Lending (`lightning/sync/*.py`) is still live; its retirement after J6 needs an item then. `runtime/journal_setup.py` still uses `open_lab`: it is the dummy-lab enrollment tool and only accepts a lab marked dummy.

**Not posted to contributors (2026-10-31):** it is pairing and journal code, inside the journal claim.
