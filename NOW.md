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
- **To all, from Claude, 2026-10-22:** a change to a screen the site quotes needs a recapture: `tools/site_shots.py`, then the site's `shots.json` and `tools/shots.py apply`.

## Next

- **Owner checks held (2026-10-28):** the owner will not run checks step by step; 1B, 1C, 2B drill, 3I, 3AH, 8C, 8I are closed and listed for end-to-end testing. Bring them up then, not before. **Read:** Overview §9.

- **Audit 9:** built; left NF-7T5/7T6, IT-4K4. **Read:** `reports/2026-10-28-loose-ends-and-linking/report.md`.


- **Store and community (2026-10-27):** 10C unlock once, 8M–8S merged in both repos; the website migrations (up to 20261027210000) are run and checked live and `redeem-purchase` is redeployed; the app release that carries 10C ships the unlock. Next: 10D (Papyrus and Dendera sets need a banner, frame and name designed). **Read:** `reports/2026-10-27-store-and-community/report.md`.

- **10A/10C app themes:** ready to sell, Dendera included; the owner deploys, opens checkout, provisions the store key and turns on each app release. New themes: `guideline/themes.md` §5. **Read:** `issues/10-looks-and-store/10C-theme-materials-acceptance.md`.

- **Website (2026-10-28):** store analytics (site PR #126, migration applied live), Downloads platform-first (site #127); leaderboard banners next. **Read:** site README › Analytics.

The whole plan, by milestone and code, is `issues/INDEX.md`.

1. **v1.5.0 is public; dependency PR #122 remains blocked.** CSV contribution #117 and the reviewed Actions/theme/engine PRs are merged. #122 still needs coordinated native wheels and lockfiles (1H). **Read:** `reports/2026-10-26-v150-release/report.md`.
2. **Audit 8 follow-ups:** 2J on journal profiles, 2Z (bridge check), owner decisions 7R and 7S. **Read:** `reports/2026-10-26-engine-audit/report.md`.
3. **9J, 9K and 2AB:** remain open from Audit 5. **Read:** `reports/2026-10-21-backend-streamlining/report.md`.
4. **1H:** coordinated Android, desktop and build-tool dependency locks remain; this follows deferred PR #103. **Read:** `issues/1-easy-to-contribute/1H-coordinate-packaged-dependency-refresh.md`.
5. **2A:** restore safety code (Luna's claim); its reboot drill joins the held checks. **Read:** 2A.
6. **2C and 4A:** native PC/phone and power-loss acceptance remain; pairing dummy fault kit built. **Read:** `reports/2026-10-26-pairing-hardening/evidence/acceptance.md`; `issues/INDEX.md`.
7. **Website recapture** after 3W / 3AG / 7Q so the site shows the current screens. **Read:** `skills/site-recapture/SKILL.md`; Changelog 2026-10-21.
8. **3H Tab-by-tab review:** optional reminders and grouped confirmations, then analytics; trust step 2 and weekly friction. **Read:** 3H §13–14.
9. **5G Brokers:** next, phase 4 import. **Read:** 5G *Fix*.
10. **Website:** 8F next (device captures ready; 3AB blocks Budget). **Read:** 8F.
11. **6B, 6D, 3AI, 5I:** shares, gold, institution logos, and gam'eya/zakat follow-ups remain as their items describe. **Read:** each item in `issues/INDEX.md`.
12. **3AD Phone overhaul:** amount-first quick add and transaction sheet; ask the owner about swipe-to-sort and a health score. **Read:** 3AD.
