---
title: Wallet, broker and fintech logos: banks have theirs, the rest still show a monogram
type: owner
area: accounts
status: ready
created: 2026-10-19
by: Claude
---

## Report
2026-10-28: the 37 bank logos in `assets/bank-logos/icons/` are bundled as 64 px PNGs in `lightning/ui/static/institutions/` and linked in `institutions.csv` (Standard Chartered, The United Bank and onebank added; Telda and WE Pay added as wallets).
Still a monogram: the wallets (Vodafone Cash, Orange Cash, e& Cash, Telda, WE Pay), the fintechs (valU, Fawry), every broker (THNDR included), Arab International Bank, Nasser Social Bank and Egypt Post. The build session could not reach their sites.

## Fix
Put each logo in `assets/bank-logos/icons/<code>.png` (256 px, the institution's own mark) and rerun the conversion in the commit that closed the banks, or run `python tools/fetch_institution_logos.py` from a PC and commit `lightning/ui/static/institutions/` and the CSV. Check trademark permission before a public release (`assets/bank-logos/README.md`).

**Read:** Architecture › Modules (accounts).
