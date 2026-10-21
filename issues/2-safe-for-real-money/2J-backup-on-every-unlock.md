---
title: Every unlock takes a full backup and checks the database three times; 30 unlocks push out every older backup
type: tech
area: backup
status: ready
created: 2026-10-21
by: Claude
---

## Report
Found by [Audit 3](../../reports/audit-3.md) §1.
- `runtime/session.py:406` builds the profile with `backup_on_start=True`.
- `_verify` (`session.py:477`) runs `integrity_check` and `cipher_integrity_check`. `export_snapshot` (`database/snapshot.py:98`) runs them again on the source, then on the copy.
- Unlock cost, Argon2 excluded: 0.14 s at 1 MB, 1.2 s at 4.4 MB, 6.2 s at 19 MB.
- `backup()` keeps the newest 30 (`database/backup.py:41`). With the 15-minute idle lock, especially on the phone, a few busy days replace every older backup.

## Fix
Owner decision first (see the report). Then: back up at most once a day, or only when the data changed since the last backup,
and keep daily, weekly and monthly copies. Drop the duplicate source check. Stay out of `runtime/restore.py` (2A claim).
