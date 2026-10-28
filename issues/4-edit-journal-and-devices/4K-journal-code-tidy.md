---
title: Journal code - lab module in production, copied helpers, an import cycle, two pairing clients
type: tech
area: devices
status: ready
created: 2026-10-28
by: Claude
commit: 9ca53bd
repo: app
---

## Report

Audit 9 B5-B10: `../../reports/2026-10-28-loose-ends-and-linking/report.md`. No behaviour changes; under the journal claim in `NOW.md`.

## 4K1 Keep the lab out of production

`runtime/journal_profile.py:259` imports `LabServer` from `journal_lab.py`; `journal_setup.py:18` uses `open_lab`. Move the server to `runtime/http.py`. The production join says "This preview joins compatible dummy replicas" (`journal_pairing.py:96-97`).

## 4K2 One canonical hash, named limits

Canonical JSON + hash is rebuilt in `finance.py:462`, `journal_move.py:29-32`, `backups.py:263,281,315`, `cutover.py:68-164`, `areas/workflows.py:85,143`, `areas/imports.py:58`, `automation.py:285`: add `codec.stable_digest()` without the 256-item cap. Name the pairing limits (12, 3, 600 in `journal_pairing.py:74`, `pairing.py:77,191,260`); use the desk clock, not `time.time()`.

## 4K3 One errors module

`cloud.py:127,150` and `local.py:239` import each other's errors inside functions. Move them to `sync/journal/errors.py`.

## 4K4 One pairing client

`runtime/journal_enrollment.NewJournalReplica` and `runtime/journal_pairing.NearbyPairing` repeat find, join, resume, compare, prove, finish and cancel, and already differ on "waiting".

## 4K5 Role fence and dead code

`runtime/devices.py:130,171` picks the journal role from marker files: one `is_journal_profile()` with a test. Dead: the cancel branch at `journal_pairing.py:222`; guards above docstrings at `devices.py:139,171,190`; stale `sync/__init__.py` docstring. Lending (`lightning/sync/*.py`) is still live; its retirement after J6 needs an item then.
