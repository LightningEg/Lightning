---
title: Search and matching: what is not built
type: feature
area: search
status: ready
created: 2026-10-13
by: unknown (moved from docs/proposals)
---

# Search and matching: what is not built

**Status: proposal · 2026-10-13 · not scheduled.** The built part (one matcher for the Search page and Ctrl-K, `difflib` near spelling) is in [Architecture](../../docs/ARCHITECTURE.md) › Search and identity contract. The contract there holds for everything below.

Work, in order:

1. Agree the contract: common misspellings, Arabic/English variants, aliases, duplicate names across entity types, short codes, account-versus-counterparty ambiguity.
2. Replace `difflib` with [RapidFuzz](https://rapidfuzz.github.io/RapidFuzz/Usage/process.html) ranking (local similarity and score cutoffs). Calibrate cutoffs with real names, especially short ones, not one threshold for all entities. It has a native component, so Windows installation is a release check.
3. Apply the matcher to scoped pickers: transfer account, counterparty, custody owner, category, instrument.
4. Page search for Accounts, People, Counterparties, Reserves and investments, grouped by type.
5. Let transaction history find rows through matched alias, account and category IDs, keeping exact date, amount and ref filters.
6. Verify zero results, near ties, one- and two-character queries, Arabic text, large histories, archived records and transfer safety, and measure latency. If size requires an index, evaluate SQLite FTS5 for candidate retrieval under the same ranking and confirmation contract.
