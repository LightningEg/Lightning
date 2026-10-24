---
title: Cosmetic parts, account-wide claiming and native acceptance
type: feature
area: appearance
status: building
created: 2026-10-24
by: Codex
skills: none
repo: app
---

## Owner scope

Swappable data-only appearance parts, themes bundled with the app, permanent account ownership, one-time online delivery codes and offline local use. Supplied PDFs are references. Preserve fixed layout, financial meanings, free defaults, Arabic and accessibility.

## Built infrastructure

Bundled slot inventory and two test manifests; strict part validation and Ed25519 offline ownership verification, with portable account identity and no license expiry/device quota. Website companion: `codex/store-wallet-foundation`, Supabase activation/proof migration and test previews. No app public keys or signing secrets seeded.

## Remaining acceptance

1. Add native Settings activation/restore UI, safe HTTPS exchange and release-pinned public key distribution.
2. Save verified licenses atomically outside financial profile backups; isolate account changes; support offline file import and replacement-device recovery.
3. Inventory every hard-coded colour/logo/control/chart style and map it to approved parts. Implement per-part fallback and whole-theme failure rollback without changing layout or finance.
4. Test every screen on Windows/Android in English/Arabic, reduced motion, semantic states, contrast and geometry. Theme manifest copies must match the website source at release.
5. Only then register enabled bundled versions and app compatibility on the store. No paid app item may be sold before claiming/applying works.
6. Finish main-site checkout/admin receipt UI, accept terms before QR, Sheets reporting and staged signing/redemption endpoint acceptance. Owner supplies actual prices/payment details.

## Read

`docs/ARCHITECTURE.md` › Cosmetic parts and offline ownership; website `cosmetics/README.md`, `cosmetics/payment-policy.md` and `supabase/README.md`.

## Baseline regression note

The full app suite reports an existing investment-link brand-audit conflict: holdings links are intentionally not underlined under the owner decision in Project Overview (7P / 3AG), but `test_links_are_ink_and_underlined` still expects underlines there. The cosmetic infrastructure does not change these links or their styles. Align the audit with the approved baseline before native skin acceptance.
