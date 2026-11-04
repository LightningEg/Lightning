---
title: Match bank-imported transfer pairs across currencies
type: feature
pillar: capture
size: M
status: building
created: 2026-10-19
by: Claude
---

## Report
The open part of multi-currency (v1.1).

## Implementation · 2026-11-04

Review one statement leg first: explicitly pick the other owned cash account and enter its exact positive native statement amount. The normal conversion service records one CNV with the executed quantities; an explicit fee inside the debit is included. Import the debit first when fees exist. The other statement suggests that same conversion only when its account, signed native amount and the existing settlement-date window agree; the review shows both account/currency legs. Linking preserves cash and the transaction date. No FX approximation or pending-pair guess is used. Tests cover fee, settlement delay, exact mismatch, incoming-first, retry, void and PC/phone forms; 59 import tests pass. Full acceptance and PR validation remain.
