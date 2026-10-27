---
title: Theme materials, selling themes, owner console - what only the owner can do now
type: feature
area: appearance
status: building
created: 2026-10-26
by: Claude
skills: guideline-audit
repo: app
---

## What shipped (2026-10-26)

- **Materials:** every app theme element states paint, material and motion from a reviewed recipe library (`theme-kit/README.md`, `slots.json` schema 2, `theme-materials.css`); contrast checked at each surface's worst point; `tools/theme_shots.py` captures the roster.
- **One purchase, every surface:** the app's paid themes take the website's ids: Nile (palette, 300 coins), Cotton (textured, 600), Papyrus (animated, 1,000). Tiers for every look: `guideline/themes.md` section 7.
- **App ownership:** paid themes are tried by anyone and kept with a signed licence (`lightning/ui/entitlements.py`); Settings › Appearance redeems the website's one-time code. **One purchase, one profile (owner, 2026-10-27):** the code (one theme, no picker in the app) claims a seat for the open profile and is burned; the licence names that profile and is shared through the profile's synced settings (`store_licence.<item>`), so its other devices unlock with no code; another profile costs 25% of the price. Settings links to the marketplace (system browser) for prices. Needs the website's `20261027130000_profile_seats` migration and the redeployed `redeem-purchase` function before any app release that turns unlock on.
- **Website:** schema 2 validator and manifest copies (a test keeps them equal), catalogue migration, owner console rebuilt (Overview with *Ready to sell*, Catalogue with tier prices and app releases), Papyrus's gold thread on the site.

## Only the owner can do (in this order)

1. **Deploy** the website's migrations through `20261026120000_dendera_theme.sql` and the new `admin.html` assets.
2. **Open checkout** in the console (Settings › Checkout: InstaPay address, exact name, private QR), then make one real top-up from a second account, credit it, buy a theme, and check it on a second device. *Ready to sell* ticks each step.
3. **Store key:** run `python tools/store_keygen.py <private-file>` (Ed25519 pair); keep the private JWK offline with a backup. Set the Supabase secrets `STORE_SIGNING_PRIVATE_JWK`, `STORE_SIGNING_KEY_ID`, `STORE_ALLOWED_ORIGINS`; deploy `redeem-purchase` (JWT off) and `restore-purchases` (JWT on) with gateway rate limits. Give an AI only the public key and its id, to add to `lightning/security/store_keys.json`.
4. **Ship the app release** that carries the key, then Catalogue › App themes › *Turn on unlock* for Nile, Cotton, Papyrus and Dendera (its night mode rides on the same licence).
5. Turn on leaked-password protection in Supabase Auth.
6. **Before the app release that carries once-per-profile unlock:** deploy the website's new `redeem-purchase` (it accepts `items`) and its migration.

## Still to do by an AI

1. Native acceptance (8J): WebView2 and Android paint, cost of grain and blur on a low-end phone, Arabic mirroring of artwork and glow, forced colours; Dendera's frieze and pigment thread on a low-end phone.
2. Royal Obsidian & Gold needs a website version before it can be sold.
3. Pre-existing: the app's own green on dark cards reads low in every dark theme; the fix belongs to the dark adapter in `theme-surfaces.css`.
4. After 60 days of sales, review prices as `docs/payment-operations.md` (website) › Pricing describes.

## Done when

The owner has done steps 1-4 and a buyer has unlocked a theme on Windows and Android.
