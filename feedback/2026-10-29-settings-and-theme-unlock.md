# Settings order and theme unlock

Date received: 2026-10-29 · Reviewed: 2026-10-29
Product/build/surface: Lightning v1.5.1, Settings
Source: user-provided screenshots and chat; no private identifiers retained

## Observations and themes

| ID | Observation | Expected outcome | Theme | Investigation verdict | Issue / disposition |
| --- | --- | --- | --- | --- | --- |
| FB1 | Entering a purchased theme code shows a store-response verification failure. | A valid purchase unlocks its theme for the open profile. | Theme delivery | Resolved: correcting the store signing key ID restored unlocking. | BT-10E; configuration resolution below |
| FB2 | Your data appears last in Settings. | Swap Your data back to first and Data checks to last. | Navigation | Built; owner overrides the 2026-10-28 default. | BV-3AK; [navigation regression](../tests/test_two_levels.py) |

Two observations from one respondent. Screenshots are described rather than retained.

## Dated follow-ups

- 2026-10-29: FB1 reaches `lightning/ui/entitlements.py`'s verifier rejection after a successful HTTP response. The live redemption function and database RPC match the checked-in format, including profile binding. A production signed response is needed to distinguish an unknown/mismatched signing key, invalid signature or invalid payload. No private signing material or purchase codes requested or stored.

- 2026-10-29: Live logs show HTTP 200 redemption responses during the reported attempts; aggregate audit checks show four completed redemptions and two new profile claims in that window. No identities or ticket values retained. A disposable WebCrypto signature from the checked-in store signer passes the Python app verifier, ruling out a general format incompatibility. The production signing key and rejected envelope remain unavailable.

- 2026-10-29: The user supplied the public verification key; it matches the app pin exactly. The production key ID and rejected response still need confirmation. This does not independently establish which private key the deployed signer uses.

- 2026-10-29: The user confirmed `STORE_SIGNING_KEY_ID` is the public key string. Root cause: `verify_license` looks up that ID in the app’s pinned keys and finds none; the app trusts ID `store-2026-1`. Correct the Supabase secret to that exact ID and issue a fresh code. Connected tools cannot edit secrets; no deployment or trust change is needed. Live end-to-end retry remains outstanding.

- 2026-10-29: The user corrected the Supabase secret to `store-2026-1` and confirmed unlocking works. BT-10E is resolved through production configuration; the public key, private JWK and app verification logic were unchanged.
