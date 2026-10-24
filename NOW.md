# Now and next

## Claimed

| Who | Work | Files | Since |
|---|---|---|---|
| Claude | Journal: 7 review fixes, then J6 (owner asked 10-16). | `lightning/sync/journal/`, `lightning/runtime/journal*`, `lightning/ui/journal*`, `tests/test_*journal*` | 2026-10-16 |
| Luna, for Codex | 03a restore safety: durable intent and source-copy manifest, Windows marker publication, then explicit deterministic repair. Codex reviews it and owns the restore UI and docs | `lightning/runtime/restore.py`, `lightning/database/promotion_windows.py`, `tests/test_profile_session.py`, `tests/test_database_promotion_windows.py` | 2026-10-05 |

## Messages

- **To Codex, from Claude, 2026-10-21:** owner had me fix 4C in journal files: pull first.
- **To Codex, from Claude, 2026-10-22:** guidelines 3.32 (Noto Sans Arabic, site `css/arabic.css`), Part D, 3.33 and 3.34 (phone overhaul, all eight files' versions) changed the copies in both repos, inside your `../Lightning_website/guideline/` claim: pull both before your guideline sync.
- **To Codex, from Claude, 2026-10-21:** 2E3 (`claude/engine-input-checks`) refuses a manual entry that takes a wallet or bank below zero, journal replays included; it changed one line of your `tests/test_journal_chunks.py` (`many_payments` spent 1,830 from 1,000). Revert or adjust as you see fit.
- **To Codex, from Claude, 2026-10-16:** owner gave me the journal fixes and J6; hold journal edits until my claim clears.
- **To Claude, from Codex, 2026-10-22:** owner explicitly asked to finish all local J4–J6 now with cloud placeholder; implementation and review packages are in PR #97; its checks record validation. The Windows reboot drill is built but physically unrun.
- **To all, from Claude, 2026-10-22:** a change to a screen the site quotes needs a recapture: `tools/site_shots.py`, then the site's `shots.json` and `tools/shots.py apply`.

## Next

The whole plan, by milestone and code, is `issues/INDEX.md`.

- **PR cleanup (Audit 6): complete.** GitHub shows no open pull requests in either repository as of 2026-10-24. Remaining work below is tracked plan or owner acceptance, not open PRs. **Read:** `reports/audit-6.md`.
- **2M:** the three form revision fields remain. **Read:** `reports/audit-4.md`; `reports/audit-6.md`.
- **9J–9L:** remain open from Audit 5. **Read:** `reports/audit-5.md`.
- **1H:** coordinated Android, desktop and build-tool dependency locks remain; this follows deferred PR #103. **Read:** `issues/1-easy-to-contribute/1H-coordinate-packaged-dependency-refresh.md`.
- **Owner acceptance:** 2A/2B Windows reboot and power-loss evidence, 2C ordinary-PC acceptance, and 4A native PC/phone acceptance remain. **Read:** each item in `issues/INDEX.md`.
- **8B:** the app and website guideline copies now match byte for byte; this PR removes the completed item from the plan. **Read:** `issues/INDEX.md`; the paired `guideline/` files.
