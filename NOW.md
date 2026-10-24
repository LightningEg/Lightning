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

1. **Audit 6 PR cleanup is complete.** GitHub showed no open pull requests in either repository before this documentation PR. The remaining items below are plan or owner acceptance work, not open PRs. **Read:** `reports/audit-6.md`.
2. **2M:** the three form revision fields remain. **Read:** `reports/audit-4.md`; `reports/audit-6.md`.
3. **9J–9L:** remain open from Audit 5. **Read:** `reports/audit-5.md`.
4. **1H:** coordinated Android, desktop and build-tool dependency locks remain; this follows deferred PR #103. **Read:** `issues/1-easy-to-contribute/1H-coordinate-packaged-dependency-refresh.md`.
5. **2A/2B:** run the Windows reboot drill; power-loss evidence remains. **Read:** each item in `issues/INDEX.md`.
6. **2C and 4A:** ordinary-PC, recovery, and native PC/phone acceptance remain. **Read:** each item in `issues/INDEX.md`.
7. **3I owner check:** first run and import review on PC and phone. **Read:** `issues/3-polish-and-arabic/3I-owner-check-first-run-and-import.md`.
8. **Website recapture** after 3W / 3AG / 7Q so the site shows the current screens. **Read:** `skills/site-recapture/SKILL.md`; Changelog 2026-10-21.
9. **3H Tab-by-tab review:** optional reminders and grouped confirmations, then analytics; trust step 2 and weekly friction. **Read:** 3H §13–14.
10. **5G Brokers:** next, phase 4 import. **Read:** 5G *Fix*.
11. **Website:** 8F next (device captures ready; 3AB blocks Budget) and 8I owner checks. **Read:** 8F, 8I.
12. **6B, 6D, 6E, 5I:** shares, gold, institution logos, and gam'eya/zakat follow-ups remain as their items describe. **Read:** each item in `issues/INDEX.md`.
13. **3AD Phone overhaul:** amount-first quick add and transaction sheet; ask the owner about swipe-to-sort and a health score. **Read:** 3AD.
