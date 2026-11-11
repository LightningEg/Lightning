---
title: For Geeks gets two motion moments that are true - a posting that must balance, and a row that becomes ciphertext
type: polish
pillar: reach
size: M
model: opus
status: parked
created: 2026-11-11
by: Claude
skills: none
repo: website
post: no
---

## Report

Owner decision 2026-11-11 (OW-8D): of the outside audit's seven motion moments, build only two, because they show what the code really does: **a posting that must balance**, drawn beside the `ledger.py` code, and **a row becomes ciphertext** on the secure card. Not built: *nothing leaves the PC, 0 requests out* is false (the app fetches market prices and rates, `lightning/market/http.py`), and the other four are not chosen. Guideline D08 says motion is the weather, never the content, so each moment is a new D07 block and a guideline change first, made in both repositories in the same session.

## Fix

1. Add both moments to `guideline/coders.html` (D07 blocks, with their reduced-motion fallback) in the app repository and copy to the website repository (`cmp` must pass).
2. Build them on the For Geeks pages (English and Arabic), driven by real code lines, not invented ones.
3. Run the website tests and the guideline-copy test.

## Done when

Both moments play once, respect reduced motion, read correctly in Arabic, and the guideline copies match in both repositories.
