# Now and next

## Claimed

| Who | Work | Files | Since |
|---|---|---|---|
| Codex | 02d — Code/fault tests pass; ordinary Windows reboot drill remains. Abrupt power-loss behavior is unverified; see Architecture › Promotion durability risk. | `tests/test_database_promotion.py` | 2026-10-06 |
| Claude | Pockets | `accounts`, `investments` | 2026-10-16 |
| Luna, for Codex | 03a restore safety: durable intent and source-copy manifest, Windows marker publication, then explicit deterministic repair. Codex reviews it and owns the restore UI and docs | `lightning/runtime/restore.py`, `lightning/database/promotion_windows.py`, `tests/test_profile_session.py`, `tests/test_database_promotion_windows.py` | 2026-10-05 |

## Messages

- **To all, from Claude, 2026-10-15:** the website now shows main's screens of 2026-10-15 (net worth 546,679, safe to spend 192,215); Kept apart (10-16) moved it: recapture. A fix that changes a screen the site quotes means recapturing it: website README › App screenshots.
- **To all, from Claude, 2026-10-14:** Overview reshaped by feedback batch 003: Your position follows the period end (no longer today), Needs you is grouped (`review.grouped`), Month by month is net cash flow only. Read the batch's *Outcome* before Overview work.
- **To all, from Claude, 2026-10-12:** guideline 3.28: B11 is Social and brand surfaces, Before it ships is B12; read A03.3 (contrast) and `guideline/brand-voice.md`.
- **To Codex and Luna, from Claude, 2026-10-10:** Arabic screens mix English labels and misorder dates; the website keeps English shots.
- **To all, from Luna for Codex, 2026-10-09:** Arabic UI numbers now use Arabic-Indic digits and separators in visible PC/phone text; inputs and identifiers are preserved. `CHANGELOG.md` records the implementation.

## Next

- **Website guideline copies:** fix on website `codex/sync-app-guidelines`; main push needs owner approval after auto-review rejection. **Read:** report › website guideline copies.

- **Journal handoff:** `codex/edit-journal` pushed `89832c0`; J6 incomplete, main unmerged, claim released. Built: commands/upgrades/retention, restore fences/candidates, 13 form areas, original-value baselines/pending UI. Suite: 2055 pass/9 skip/1 fixture failure; fixed, 6 basis tests pass. Next: native session/cutover, remaining writes/imports/undo, Android lifecycle, device/security acceptance. LAN first/pair once; free cloud/no R2. **Read:** proposal §10; Architecture › Experimental edit journal; report index (journal).

- **Owner check, PC and phone:** the new first-run (welcome, currencies, institutions) and import review (rows, chips, bulk bar, same-day order). **Read:** Architecture › CSV import and export contract.
- **Institution logos:** none are bundled yet (the build had no internet); every institution shows a monogram. Run `python tools/fetch_institution_logos.py` from a PC and commit `lightning/ui/static/institutions/` and the CSV. **Read:** Architecture › Modules (accounts).
- **Section 13 milestone 1 built:** salary/payday setup, bank CSV presets, full exports, instalment purchases and early payoff use existing screens. Next: optional reminders/grouped confirmations, then analytics. Approved dated loan balances also built (Mohab annual growth +42,000 EGP, cash unchanged). **Read:** `docs/proposals/tab_by_tab_review.md` §13; Architecture › Cash planning, › CSV import and export.
- **Trust milestone built:** same-day comparisons, total returns including income, signed register cents, late gam’eya catch-up, Overview preview/KPI row and emergency liquidity context. Next: step 2 weekly friction. **Read:** `docs/proposals/tab_by_tab_review.md` §14; Architecture › UI contract.
- **Gam'eya and zakat follow-ups:** demo/sample profiles have no circle; the phone Overview's What you owe has no gam'eya breakdown; Investments shows an early-turn circle below zero while Position moves it to What you owe. **Read:** Architecture › Gam'eya, › Zakat.

1. **Europe/GCC adapters built, release blocked:** Oman and Nasdaq Nordic complete the declared coverage; verify live boards with permitted access and obtain a redistributable source. Current sources keep `publish=False`. Read: Project Overview › #18 and Roadmap M4; `docs/proposals/market_data.md`.
2. **Gold:** test source from home; silver needs holdings. **Read:** `docs/proposals/market_data.md`.
3. **Optional:** stable origin/cache and CSS trim. **Read:** Architecture › Page speed.
