---
was: 6E
title: Additional broker and institution logos still needed
type: owner
pillar: feel
status: parked
created: 2026-10-19
by: Claude
---

## Report
2026-10-28: 37 original bank logos remain in `assets/institutions-logos/icons/` after renaming the catalog. The new importer added 31 authentic e-wallet/fintech/payment/investment assets, including Vodafone Cash, Orange Cash, e& Cash, WE Pay, Telda, Thndr, Money Fellows, InstaPay, Fawry and valU. The known account-provider logos were also bundled at 64 px and mapped in `lightning/accounts/institutions.csv`. See `assets/institutions-logos/manifest.json` for source URLs and `download-report.json` for import failures.

2026-10-28 (Claude): every wallet and fintech mark in the catalog is now an institution with its tile: 22 added (bank wallets such as NBE Phone Cash, CIB Smart Wallet, BM Wallet, Cashati; Halan, Khazna, MoneyFellows, InstaPay, easyCash, Axis, e-Pocket, Masary). `tools/bundle_institution_logos.py` trims each mark's white margin before the 64 px tile, so wordmarks stay readable.

## Remaining
Institution-picker monograms remain for brokers other than Thndr and for Arab International Bank, Nasser Social Bank and Egypt Post. Some third-party wallet directory artwork may reflect historic names; verify current branding before public release. Completing the remaining list requires actual marks in `assets/institutions-logos/icons/<code>.png`, matching `lightning/ui/static/institutions/<code>.png` and the CSV `logo` column. Use `tools/fetch_institution_logos.py` for available sites, review trademarks, and verify images in the app.

**Read:** Architecture › Modules (accounts).

## 2026-11-12 · Broader, simpler default picker

- Keep one canonical **Vodafone Cash** entry and logo; the CSV only contains one. Avoid introducing additional Vodafone variants. Existing user-created account names are not altered.
- Remove 18 niche / bank-specific wallet variants from the *default picker* (including CIB Smart Wallet); their legacy image assets remain in the repository but are no longer linked. Keep banks and well-recognized wallet/fintech providers.
- Add 11 popular supermarkets and 16 recognizable consumer brands, in separately named picker groups. Non-financial brands do **not** imply BANK/CASH/BROKERAGE account types.
- Bundle 14 locally stored vector brand marks from credited sources in both the original asset catalog and app static directory. Missing verified marks use existing monogram fallback rather than invented logos. **Retailers still needing verified marks:** Fathalla Market, Kazyon, Hyper One, Seoudi, Spinneys, Metro Markets, Kheir Zaman, Awlad Ragab, Gourmet Egypt, Amazon Egypt, Jumia, Breadfast, Pizza Hut.
- Follow-up: check these marks against current official visual identity, licensing/attribution requirements, and mobile picker presentation before release. This does not implement automatic transaction-merchant matching or alter existing account records.
