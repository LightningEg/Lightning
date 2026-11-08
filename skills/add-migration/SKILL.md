---
name: add-migration
description: Add a SQLite migration to the app safely: a numbered file appended after the last, no transaction statements, the bundled version bumped, one module that owns the table, seed, export, journal and undo kept in step, and tests that upgrade a real older profile. Use when the app needs a new table, column, index, trigger or a data fix in existing profiles. For the website's Supabase use skill supabase-migration.
---

# Add an app migration

Tool-neutral. A migration runs once on every person's encrypted profile, on Windows and Android, and cannot be taken back: a mistake here loses or corrupts real money records. Read `ai/ARCHITECTURE.md` › Persistence, precision, and indexing first.

## Steps

1. **Need.** Is the state new, or derivable from what is stored? Derived figures are computed in services, never stored. Define a new concept in `ai/GLOSSARY.md` before building it.
2. **File.** `lightning/database/migrations/NNNN_what_in_snake_case.sql`, the next number with no gap (`ls lightning/database/migrations | tail -1`). The first lines are a comment saying what and why, with the item code. Never edit or renumber an applied migration (anything on `main`); add a new one.
3. **Rules the migrator enforces** (`lightning/database/migrator.py`): no `BEGIN`, `COMMIT`, `SAVEPOINT` or `ROLLBACK` (the migrator wraps each file in one transaction), complete statements only, and `BUNDLED_LATEST_VERSION` set to the new number in the same commit. `-- @optional` on the first line only for a feature a platform may lack (FTS5).
4. **Shape.**
   - Tables: `INTEGER PRIMARY KEY`, foreign keys with an explicit `ON DELETE`, `CHECK` constraints for closed lists, `created_at`/`updated_at` text, money as integer `_e6`, dates ISO text. One module owns the table and is the only one that writes it (Architecture › Modules).
   - Columns: `ALTER TABLE ... ADD COLUMN` with a default that is correct for every old row. SQLite cannot drop or retype a column in place: rebuild the table (create new, copy, drop, rename) and recreate its indexes and triggers.
   - Indexes only for a query that needs one; a unique constraint that leads with the same columns replaces an index.
   - Data fixes: idempotent (`INSERT OR IGNORE`, `WHERE ... IS NULL`), never touching `ledger_entries` amounts; a posting change goes through `TransactionService` in code, not SQL.
5. **Keep the rest in step** (grep an existing table such as `other_asset_details` to find each place):
   - `lightning/database/seed.py` when a new profile needs the rows;
   - `lightning/workflows/data_export.py` `TABLES` when it holds a person's records;
   - the sync journal: the area in `lightning/sync/journal/areas/` and a command for each write, or the route in `tools/journal_coverage_allow.txt` with a reason (`python tools/journal_coverage.py --check`);
   - undo reads the schema itself (`lightning/undo.py`); check a write to the new table can be undone;
   - `Database.referenced` decides delete or archive from foreign keys, so a new reference makes the referenced row archive instead of delete: say so in the item.
6. **Tests.**
   - The migration on a database at the previous version with realistic rows (copy the shape of `tests/test_migration_safety.py`): old rows keep their values, new defaults are right, a second run does nothing.
   - The owning service's behaviour, and `tests/test_atomic_write_failures.py`, `tests/test_device_roundtrip.py` and the journal tests when the table is synced.
   - The full suite once, Mohab (`tests/test_mohab_year.py`), and skill `number-audit` if any figure reads the new state.
7. **Commit** with the item code in the subject; `Detail:` names the migration number. `tools/release_notes.py cut` lists migrations in the version notes on its own.

An upgrade on a real profile makes a backup first (`SchemaInspection.needs_backup`); never weaken that path. A migration that cannot run on an old profile the owner has is a release blocker: ask the owner to try an upgrade from the last released version before the tag (skill `release-check`).
