---
title: Bundles - the cart offers the cheaper set, and a starter bundle per theme
type: feature
area: website
status: ready
created: 2026-10-27
by: Claude
repo: website
---

## Report

[Store and community audit](../../reports/2026-10-27-store-and-community/report.md) B1. Sets exist (20% off their parts) but nothing points to them at the moment of buying.

## Fix

- `cart_view` returns `suggestions`: each set whose parts the cart and the inventory already cover at least half of, with the coins saved by swapping those lines for the set (server prices only). The window shows "Switch to the Nile set: save 176 coins" and one press does the swap (`cart_swap_for_set`, one transaction).
- Each sold theme gets a set (theme + its banner + frame + name) so every theme has a bundle; the owner prices sets in Catalogue as now.
- Sets tab first in Themes for a buyer who owns nothing. Tests in `supabase/tests/cart.test.mjs`.
