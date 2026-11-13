---
title: Let the owner mark chosen investments as liquid, so they count with cash wherever liquid money is read
type: feature
pillar: plan
size: M
model: opus
status: new
created: 2026-11-12
by: owner
---

## Report
Owner, 2026-11-12: a way to mark certain financial assets to be counted as liquid assets as well (for example a money-market or Cloud fund that can be sold within a day). Not solved in the session that heard this.

## Fix
Each investment already has a liquidity class (assets/domain.py). Add an owner switch "Count as liquid" on the investment's edit page, stored on the asset (migration per skill add-migration), and have the figures that read liquid money (safe to spend, emergency fund cover, the liquid line of net worth) include marked assets at their value. One Glossary entry; the switch never changes the ledger. Test: marking a fund raises the liquid figure by its value and nothing else.
