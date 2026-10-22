# Now and next

## Claimed

| Who | Work | Files | Since |
|---|---|---|---|
| Claude | 3W answer first: guideline 3.33 (both repos), then the six tabs. | `guideline/`, `lightning/ui/templates/{dashboard,budget,planning,investments,accounts,financial_health}*`, `lightning/ui/status.py`, `lightning/ui/static/style.css` | 2026-10-21 |
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

The whole plan, by milestone and code, is `issues/INDEX.md`. In order:

0. **Demo cut list from Audit 1** (owner, 10-20): built on seven `claude/` PRs (2E1–5, 5H, 3U1–4, 3V, 7L1, 7K, 3R, 3S1–2, 3C, 3A). Left: 3U 5–6, 2F (phone backup and import), then 7L2–7L4, 5K, 3S 3–20, 3T. Recapture the website once these merge: the sample now has ten accounts, goals, a gam'eya and more (it shows the sample on 10-04, with a late rent). **Read:** `reports/audit-1.md` › Demo cut list.
1. **1B Owner runs the security setup**, then **1C** a trial contribution. **Read:** 1B.
2. **2A/2B restore and durability:** restore mechanisms already implemented; run the dummy Windows reboot drill. Power-loss evidence remains open. **Read:** 2A, 2B.
3. **4A Edit journal:** local integration and both review packages in PR #97; its checks record validation. Native PC/phone acceptance remains. Cloud deployment waits. **Read:** 4A §10 J6; Architecture › Command proposals.
4. **3I Owner check, PC and phone:** first run and import review. **Read:** 3I.
5. **3W Answer first** (Claude): guideline 3.33 and all six tabs built (PC and phone); left: Overview KPIs to A08, flows to Spending, holdings in five columns, site-recapture. **Read:** 3W *Steps*; A09.
6. **3H Tab-by-tab review:** §13 milestone 1 and the trust milestone built; next, optional reminders and grouped confirmations, then analytics; trust step 2, weekly friction. **Read:** 3H §13–14.
7. **5G Brokers:** next, phase 4 import. **Read:** 5G *Fix*.
8. **Website:** 8B on `codex/sync-app-guidelines`; 8F next (recaptured 10-21; 3AB blocks Budget); 8I owner. **Read:** 8B, 8F.
9. **6B Europe/GCC shares**, **6D gold**, **6E institution logos**, **5I gam'eya and zakat follow-ups:** waiting as their items say. **Read:** each item.
10. **3AD Phone overhaul, step 2** (3AC built the rest, guideline 3.34): quick add with the amount first, a transaction sheet with Plan left; ask the owner about swipe to sort and a health score. **Read:** 3AD.
