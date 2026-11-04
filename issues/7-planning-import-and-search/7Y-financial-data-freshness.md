---
title: Explain which stale or pending inputs affect a financial figure
type: feature
pillar: understand
size: M
status: building
post: no
created: 2026-11-03
by: Codex
app_version: 1.5.4
commit: 89848dc0e4ce35bb18f72e861c7c620d8052fae4
repo: app
---

## Report

[Smart-feature recommendation 4](../../reports/2026-11-03-code-quality-and-smart-features/report.md). Existing price source/date metadata, account checking, journal status and figure explanations provide the foundation. Add contextual reasons when stale quotes/FX, pending edits or missing receipts affect a result; do not create a second competing total or invent a numeric confidence score.

## Fix

Create a Python read model of reason, source date, affected figure and resolution link. Extend the existing figure explanation surface on PC/phone, with a clear distinction between known and unknown freshness. Test stale/fresh prices, absent FX, pending confirmations and reconciled accounts; verify the explanation cannot change the amount. Coordinate with market and journal owners.

Not posted: proposal awaiting prioritization and shared freshness semantics.

## Built so far · 2026-11-04

`lightning/planning/freshness.py` (`FreshnessService`, on the container as `c.freshness`): for **What you own** it returns notes of kind stale price (dated, older than 62 days), no price (undated), stale rate (dated, older than the FX limit) and no rate (undated), each with the figure it affects and where to fix it. The Overview's "What you own" explanation popup (`/explain/owned`, PC and phone) lists them under "What this figure leans on", in English and Arabic. `tests/test_freshness.py` covers fresh and stale prices, an unpriced holding, stale and missing rates, a profile with nothing to say, the Arabic page, and that no amount changes.

The remaining cash and forecast notes are implemented below; full-suite and PR validation remain before closure.

## Completion work · 2026-11-04

Cash explanations now read account checks (old after 31 days), certificate receipts awaiting confirmation and journal proposals excluded from confirmed figures. Forecast notes also identify missing or old rates. Reads do not match or post receipts; equity prices stay out of cash explanations. Focused boundary, historical cutoff, replica and bilingual frame tests cover these paths.
