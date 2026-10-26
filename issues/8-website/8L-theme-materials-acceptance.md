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
- **App ownership:** paid themes are tried by anyone and kept with a signed licence (`lightning/ui/entitlements.py`); Settings › Appearance redeems the website's one-time code.
- **Website:** schema 2 validator and manifest copies (a test keeps them equal), catalogue migration, owner console rebuilt (Overview with *Ready to sell*, Catalogue with tier prices and app releases), Papyrus's gold thread on the site.

## Only the owner can do (in this order)

1. **Deploy** the website's migrations through `20261026120000_dendera_theme.sql` and the new `admin.html` assets.
2. **Open checkout** in the console (Settings › Checkout: InstaPay address, exact name, private QR), then make one real top-up from a second account, credit it, buy a theme, and check it on a second device. *Ready to sell* ticks each step.
3. **Store key:** the owner provided the public key and key ID on 2026-10-26; they are pinned in `lightning/security/store_keys.json`. The owner confirms `STORE_SIGNING_PRIVATE_JWK` and `STORE_SIGNING_KEY_ID` are set as Supabase Edge Function secrets, and both functions are deployed with the intended JWT settings. Keep the private JWK offline with a backup. Set `STORE_ALLOWED_ORIGINS` and gateway rate limits. A signed response from Supabase must verify against the pinned public key before an app release; the secret/public pairing has not been verified.
4. **Ship the app release** that carries the key, then Catalogue › App themes › *Turn on unlock* for Nile, Cotton, Papyrus and Dendera (its night mode rides on the same licence).
5. Turn on leaked-password protection in Supabase Auth.

## Still to do by an AI

1. Native acceptance (8J): WebView2 and Android paint, cost of grain and blur on a low-end phone, Arabic mirroring of artwork and glow, forced colours; Dendera's frieze and pigment thread on a low-end phone.
2. Royal Obsidian & Gold needs a website version before it can be sold.
3. Pre-existing: the app's own green on dark cards reads low in every dark theme; the fix belongs to the dark adapter in `theme-surfaces.css`.
4. After 60 days of sales, review prices as `docs/payment-operations.md` (website) › Pricing describes.

## Done when

The owner has done steps 1-4 and a buyer has unlocked a theme on Windows and Android.
