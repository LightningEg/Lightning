---
title: Search and matching: what is not built
type: feature
pillar: capture
size: L
status: ready
created: 2026-10-13
by: unknown (moved from docs/proposals)
---

# Search and matching: what is not built

**Status: proposal · 2026-10-13 · not scheduled.** The built part (one matcher for the Search page and Ctrl-K, `difflib` near spelling) is in [Architecture](../../ai/ARCHITECTURE.md) › Search and identity contract. The contract there holds for everything below.

Work, in order:

1. Agree the contract: common misspellings, Arabic/English variants, aliases, duplicate names across entity types, short codes, account-versus-counterparty ambiguity.
2. Replace `difflib` with [RapidFuzz](https://rapidfuzz.github.io/RapidFuzz/Usage/process.html) ranking (local similarity and score cutoffs). Needs 7D1 agreed first. Calibrate cutoffs with real names, especially short ones, not one threshold for all entities. It has a native component, so Windows installation is a release check.
3. Apply the matcher to scoped pickers: transfer account, counterparty, custody owner, category, instrument.
4. Page search for Accounts, People, Counterparties, Reserves and investments, grouped by type.
5. Let transaction history find rows through matched alias, account and category IDs, keeping exact date, amount and ref filters.
6. Verify zero results, near ties, one- and two-character queries, Arabic text, large histories, archived records and transfer safety, and measure latency. If size requires an index, evaluate SQLite FTS5 for candidate retrieval under the same ranking and confirmation contract.

## 7D1 Agree the matching contract · M
Common misspellings, Arabic and English variants, aliases, duplicate names across entity types, short codes, account versus counterparty ambiguity.

## 7D2 Replace difflib with RapidFuzz · L
Calibrate cutoffs with real names, per entity; it has a native component, so Windows installation is a release check.

## 7D3 Scoped pickers use the matcher · M
Needs 7D2 merged first. Transfer account, counterparty, custody owner, category, instrument.

## 7D4 Page search grouped by type · M
Needs 7D2 merged first. Accounts, People, Counterparties, Reserves and investments.

## 7D5 History search through matched IDs · M
Needs 7D2 merged first. Rows found via alias, account and category IDs, keeping exact date, amount and ref filters.

## 7D6 Edge cases and speed · M
Needs 7D3 to 7D5 merged first. Zero results, near ties, one- and two-character queries, Arabic, large histories, archived records, transfer safety, latency; evaluate SQLite FTS5 only if size needs it.
