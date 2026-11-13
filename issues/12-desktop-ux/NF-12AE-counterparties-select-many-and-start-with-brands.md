---
title: Counterparties can be selected and changed in bulk, and the bundled institutions and brands (Uber, Talabat and the like) start inside them
type: feature
pillar: capture
size: M
model: sonnet
status: new
created: 2026-11-12
by: owner
---

## Report
Owner, 2026-11-12: on the Counterparties page rows cannot be mass selected or changed. The institutions and brands Lightning already knows (`lightning/accounts/institutions.csv`: supermarkets, brands) should be counterparties from the start, so a category and a logo are one pick away.

Not solved in the session that heard this.

## Fix
Tick boxes with a bulk bar (category, merge, archive) as on the register; seed the bundled brands as counterparties on a new profile and offer them to existing ones once (migration per skill `add-migration`, no overwriting of names the user already has). Test: a profile upgraded from an older version keeps every existing counterparty and gains the brands once.
