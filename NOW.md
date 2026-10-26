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
- **To all, from Claude, 2026-10-22:** a change to a screen the site quotes needs a recapture: `tools/site_shots.py`, then the site's `shots.json` and `tools/shots.py apply`.

## Next

- **3AH visual flow review:** implementation and browser evidence ready for owner review; native Windows/Android and assistive-technology acceptance remain. **Read:** `reports/2026-10-25-app-visual-flow/report.md`.

- **8J app theme acceptance:** palette swap and creator kit built; native paint/contrast and ownership remain. **Read:** `theme-kit/README.md`; `issues/8-website/8J-cosmetic-parts-and-claiming.md`.

The whole plan, by milestone and code, is `issues/INDEX.md`.

1. **Audit 6 disposition is complete; four other app PRs are open.** As of 2026-10-24, GitHub shows app PRs #117 and #121–#123 open, and no open website PRs. #117 is a CSV amount-format contribution; #121–#123 are Dependabot updates. They are separate from the historical PRs listed in Audit 6 and still need their own review. The remaining items below are plan or owner acceptance work. **Read:** `reports/2026-10-23-pull-request-cleanup/report.md`.
2. **Audit 8 follow-ups:** 2J on journal profiles, 2Z (bridge check), owner decisions 7R and 7S. **Read:** `reports/2026-10-26-engine-audit/report.md`.
3. **9J–9L:** remain open from Audit 5. **Read:** `reports/2026-10-21-backend-streamlining/report.md`.
4. **1H:** coordinated Android, desktop and build-tool dependency locks remain; this follows deferred PR #103. **Read:** `issues/1-easy-to-contribute/1H-coordinate-packaged-dependency-refresh.md`.
5. **2A/2B:** run the Windows reboot drill; power-loss evidence remains. **Read:** each item in `issues/INDEX.md`.
6. **2C and 4A:** native PC/phone and power-loss acceptance remain; pairing dummy fault kit built. **Read:** `reports/2026-10-26-pairing-hardening/evidence/acceptance.md`; `issues/INDEX.md`.
7. **3I owner check:** first run and import review on PC and phone. **Read:** `issues/3-polish-and-arabic/3I-owner-check-first-run-and-import.md`.
8. **Website recapture** after 3W / 3AG / 7Q so the site shows the current screens. **Read:** `skills/site-recapture/SKILL.md`; Changelog 2026-10-21.
9. **3H Tab-by-tab review:** optional reminders and grouped confirmations, then analytics; trust step 2 and weekly friction. **Read:** 3H §13–14.
10. **5G Brokers:** next, phase 4 import. **Read:** 5G *Fix*.
11. **Website:** 8F next (device captures ready; 3AB blocks Budget) and 8I owner checks. **Read:** 8F, 8I.
12. **6B, 6D, 6E, 5I:** shares, gold, institution logos, and gam'eya/zakat follow-ups remain as their items describe. **Read:** each item in `issues/INDEX.md`.
13. **3AD Phone overhaul:** amount-first quick add and transaction sheet; ask the owner about swipe-to-sort and a health score. **Read:** 3AD.
