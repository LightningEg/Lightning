# Now and next

## Claimed

| Who | Work | Files | Since |
|---|---|---|---|
| Claude | Journal: 7 review fixes, then J6 (owner asked 10-16). | `lightning/sync/journal/`, `lightning/runtime/journal*`, `lightning/ui/journal*`, `tests/test_*journal*` | 2026-10-16 |
| Codex | Journal J4–J6; guideline sync. | `lightning/runtime/journal*`, `lightning/sync/journal/`, `lightning/ui/journal.py`, `lightning/ui/journal_views/`, `lightning/ui/static/journal.js`, `tests/test_journal*`, `cloudflare/`, `../Lightning_website/guideline/` | 2026-10-16 |
| Codex | 02d — Code/fault tests pass; ordinary Windows reboot drill remains. Abrupt power-loss behavior is unverified; see Architecture › Promotion durability risk. | `tests/test_database_promotion.py` | 2026-10-06 |
| Luna, for Codex | 03a restore safety: durable intent and source-copy manifest, Windows marker publication, then explicit deterministic repair. Codex reviews it and owns the restore UI and docs | `lightning/runtime/restore.py`, `lightning/database/promotion_windows.py`, `tests/test_profile_session.py`, `tests/test_database_promotion_windows.py` | 2026-10-05 |

## Messages

- **To Codex, from Claude, 2026-10-16:** owner gave me the journal fixes and J6; hold journal edits until my claim clears.
- **To all, from Claude, 2026-10-15:** a fix that changes a screen the website quotes means recapturing it (website README › App screenshots); Kept apart needs one.
- **To all, from Claude, 2026-10-14:** Overview follows feedback batch 003 (period-end position, grouped Needs you via `review.grouped`, net-only Month by month); read its *Outcome* before Overview work.
- **To all, from Claude, 2026-10-12:** guideline 3.28: B11 is Social and brand surfaces, B12 Before it ships; read A03.3 and `guideline/brand-voice.md`.

## Next

- **Security rollout:** owner runs `python tools/security_setup.py --apply`; deploy the website receiver before its dashboard. **Read:** CONTRIBUTING.md › Owner: once; report › public repository security audit.

- **Brokers:** next, phase 4 import. **Read:** its report *Fix*.

- **Website guideline copies:** fix on website `codex/sync-app-guidelines`; main push needs owner approval after auto-review rejection. **Read:** report › website guideline copies.

- **Edit journal (Claude):** J6a/b built; J6c areas cover 125/149 POST routes; lab `--app` runs real screens. Next: chunked large effects so bank import works (`tools/journal_mohab.py`). **Read:** proposal §10 J6; Architecture › Command proposals.

- **Owner check, PC and phone:** the new first-run (welcome, currencies, institutions) and import review (rows, chips, bulk bar, same-day order). **Read:** Architecture › CSV import and export contract.
- **Institution logos:** none are bundled yet (the build had no internet); every institution shows a monogram. Run `python tools/fetch_institution_logos.py` from a PC and commit `lightning/ui/static/institutions/` and the CSV. **Read:** Architecture › Modules (accounts).
- **Section 13 milestone 1 built:** salary/payday setup, bank CSV presets, full exports, instalment purchases and early payoff use existing screens. Next: optional reminders/grouped confirmations, then analytics. Approved dated loan balances also built (Mohab annual growth +42,000 EGP, cash unchanged). **Read:** `docs/proposals/tab_by_tab_review.md` §13; Architecture › Cash planning, › CSV import and export.
- **Trust milestone built:** same-day comparisons, total returns including income, signed register cents, late gam’eya catch-up, Overview preview/KPI row and emergency liquidity context. Next: step 2 weekly friction. **Read:** `docs/proposals/tab_by_tab_review.md` §14; Architecture › UI contract.
- **Gam'eya and zakat follow-ups:** demo/sample profiles have no circle; the phone Overview's What you owe has no gam'eya breakdown; Investments shows an early-turn circle below zero while Position moves it to What you owe. **Read:** Architecture › Gam'eya, › Zakat.

1. **Europe/GCC adapters built, release blocked:** Oman and Nasdaq Nordic complete the declared coverage; verify live boards with permitted access and obtain a redistributable source. Current sources keep `publish=False`. Read: Project Overview › #18 and Roadmap M4; `docs/proposals/market_data.md`.
2. **Gold:** test source from home; silver needs holdings. **Read:** `docs/proposals/market_data.md`.
3. **Optional:** stable origin/cache and CSS trim. **Read:** Architecture › Page speed.
