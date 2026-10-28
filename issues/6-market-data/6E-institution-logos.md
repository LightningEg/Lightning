---
title: Additional broker and institution logos still needed
type: owner
area: accounts
status: ready
created: 2026-10-19
by: Claude
---

## Report
2026-10-28: 37 original bank logos remain in `assets/institutions-logos/icons/` after renaming the catalog. The new importer added 31 authentic e-wallet/fintech/payment/investment assets, including Vodafone Cash, Orange Cash, e& Cash, WE Pay, Telda, Thndr, Money Fellows, InstaPay, Fawry and valU. The known account-provider logos were also bundled at 64 px and mapped in `lightning/accounts/institutions.csv`. See `assets/institutions-logos/manifest.json` for source URLs and `download-report.json` for import failures.

2026-10-28 (Claude): every wallet and fintech mark in the catalog is now an institution with its tile: 22 added (bank wallets such as NBE Phone Cash, CIB Smart Wallet, BM Wallet, Cashati; Halan, Khazna, MoneyFellows, InstaPay, easyCash, Axis, e-Pocket, Masary). `tools/bundle_institution_logos.py` trims each mark's white margin before the 64 px tile, so wordmarks stay readable.

## Remaining
Institution-picker monograms remain for brokers other than Thndr and for Arab International Bank, Nasser Social Bank and Egypt Post. Some third-party wallet directory artwork may reflect historic names; verify current branding before public release. Completing the remaining list requires actual marks in `assets/institutions-logos/icons/<code>.png`, matching `lightning/ui/static/institutions/<code>.png` and the CSV `logo` column. Use `tools/fetch_institution_logos.py` for available sites, review trademarks, and verify images in the app.

**Read:** Architecture › Modules (accounts).
