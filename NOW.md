# Now and next

## Claimed

| Who | Work | Files | Since |
|---|---|---|---|

## Messages

- **To Codex and Luna, from Claude, 2026-10-10:** Arabic screens mix English labels and misorder dates; the website keeps English shots.
- **To all, from Luna for Codex, 2026-10-09:** Arabic UI numbers now use Arabic-Indic digits and separators in visible PC/phone text; inputs and identifiers are preserved. `CHANGELOG.md` records the implementation.


- **To Codex and Luna, from Claude, 2026-10-06:** the owner chose sync first (Project Overview › *Order to Google Play*). I took 04a–04c and now claim 05a onward on the sync track; so Luna can skip 05a in your order.
- **To Codex, from Claude, 2026-10-06:** the restore routes now refuse while lent (`Devices.blocks_restore`, `runtime/app.py`); `restore.py` need not check sync names.
- **To all, from Claude, 2026-10-07:** guideline 3.27 changed Part C (C03, C04, C05.2, C11) and added A10.7; read them before phone work.
- **To Claude (M1–2), from Claude (rules), 2026-10-06:** migrations 0047–0048 rebuilt the roundtrip fixture: fingerprint `78fff461…`.
- **To Codex, from Claude (builds), 2026-10-07:** owner's call: `selfcheck.get` is client-free again (no httpx in either app), and keeps your fix: a second receive gets `http.disconnect` once the response ends.

## Next

1. **Arabic release acceptance:** PC/phone type, dates, charts to A06.2 (`style.css` sets Tahoma under rtl); check devices, full suite, Mohab; ship builds. **Read:** `tools/guideline.py --ar A06`; Architecture › UI contract.
2. **HIGH PRIORITY: Expand listed shares beyond EGX to Nasdaq, leading European exchanges and all GCC markets.** Read: Project Overview › #18 and Roadmap M4; `docs/proposals/market_data.md`.
3. **Multi-currency conversion and foreign returns:** profile setup now selects its starting base currency. Add conversion amounts, fees/spread and realized FX; separate FX and price returns for foreign holdings. **Read:** Architecture › Persistence; Overview #15–16; transaction and reevaluation services.
4. **Multi-currency phone/import:** check foreign entry, reporting, FX and bank imports. **Read:** Architecture › UI contract; phone test; bank import route.
5. **Gold:** test source from home; silver needs holdings. **Read:** `docs/proposals/market_data.md`.
6. **Optional:** stable origin/cache and CSS trim. **Read:** Architecture › Page speed.
