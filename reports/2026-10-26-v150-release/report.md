# v1.5.0 review and package preparation

Date: 2026-10-26 · Reviewer: Codex
Repository: app and website · Reviewed app base: d6bc3f1a5dd4599dfeb7c0a15aabc177ac98ba67

## Scope and method

Review open Lightning pull requests, retain their authors' work while resolving current-main conflicts,
and prepare matched Windows and Android v1.5.0 packages. All local profiles and screenshots use dummy data.
This report records preparation, not public publication or physical-device acceptance.

## Review results

| PR | Review and validation | Disposition |
| --- | --- | --- |
| App #147 | Shared posting currency checks, reserve restore/undo bounds, loan precision and overpayment checks, submission idempotency, planning and valuation fixes. 34 new regression cases and the wider money/planning tests pass. | Merged after green CI, 75260f0b. |
| App #143 | Complete allowlisted material recipes, reproducible compiler, offline signed licences, bounded HTTPS code redemption, ownership enforced by the server. Theme/licence/compiler tests pass. | Merged after green CI, d8239936. |
| App #144 | Dendera day/night share one licence; SVG compiler accepts shapes only. No layout movement across six screens per mode; frame comparison against default passes on a quiet run. | Merged after green CI, b3d56c60. |
| App #146 | Theme-scene guideline copied from the website; retain the same guideline files across repositories. | Merged after green CI, 11693019. |
| App #117 | Recognized currency wrappers, Arabic digits, preserved leading decimal point, rejection of percent/arbitrary wrappers/extra signs; 0.50 EGP posts once. All 41 bank-import tests pass. | Merged after owner workflow approval and green CI, cfd693e5. |
| App #122 | Dependency input changes do not match the packaged native-wheel lock matrix; phone build checks fail. | Leave open: [1H](../../issues/1-easy-to-contribute/1H-coordinate-packaged-dependency-refresh.md). |
| Website #99/#100 | Inline payment errors remain visible; recorded money leads, outstanding amount prefilled, oldest-first queue. Existing server authorization and credit RPCs unchanged. Relevant page tests and security/account CI pass. | Merged, fbc91480 / a9bd606a. |
| Website #101 | Bounded theme-specific canvas scenes, mobile density and reduced-motion handling; mirrored guideline. | Merged after green CI, 920c194a. |
| Website #102 | English/Arabic hero and downloads layouts, consent-before-invite, labels/digits. Width checks at 390 and 1280 pass; site checker: zero errors. | Merged after green CI, 2a2381e. |

## Theme switching

Settings → Appearance applies a selection immediately. Free and unlocked choices persist in the profile;
the default remains available. The UI now explains that mechanism and confirms a successful save in
English and Arabic. Unowned paid choices are previews, and a failed save is reported.
The unlock form exchanges a website app code for a verified licence stored beside the profiles.

[Browser results](evidence/theme-switching.json) cover PC and phone, English and Arabic: switch,
save, reload, return to default, try an unowned theme without saving it, and check width.
[Reproduction script](evidence/check_theme_switching.py) creates disposable profiles.
Screenshots: [PC English](evidence/pc-en-theme-switching.png), [PC Arabic](evidence/pc-ar-theme-switching.png),
[phone English](evidence/phone-en-theme-switching.png), [phone Arabic](evidence/phone-ar-theme-switching.png).

Paid unlocking is intentionally unavailable until the owner supplies the store's public verification key
and completes deployment/checkout acceptance in [8L](../../issues/8-website/8L-theme-materials-acceptance.md).
No production credentials, keys, migrations or payment records were changed during this review.

## Validation and limits

- Full combined suite with Playwright: 2,676 passed, 11 skipped, 26 subtests passed; 10 failures in 562.99 seconds. Four release-preparation errors were corrected (display version, handoff length, changelog heading placement and date punctuation). Six browser failures were reproduced unchanged on the reviewed Dendera branch: the tests measured a closed Overview disclosure. They now click its visible summary before measuring/clicking the existing charts. All assertions remain.
- [All 45 affected checks pass](evidence/corrected-checks.txt): browser feedback, docs structure, changelog, packaging/version and release validation. The full suite is not repeated locally; final PR/main CI must pass. Brand, Arabic, ledger and Mohab workflow cases passed in the full run.
- Architecture: [four import contracts kept](evidence/import-contracts.txt).
- Phone: [no sideways scrolling at 320 or 360 px](evidence/phone-widths.txt).
- Theme geometry/frame comparison: [default and Dendera night](evidence/theme-frame-comparison.txt).
  The initial run under concurrent test load exceeded the frame threshold; the quiet comparison passed for both.
- The crawl reaches 600 URL variations; its one HTTP 400 is the expected empty-profile safeguard on
  `/exports/import/template`, whose page explains that requirement. It is not evidence of a complete route crawl.
- All main pages pass the 150 ms/400-query budget on the quiet final candidate: [measurements](evidence/page-performance-final.txt). The concurrent-test measurement was slow with unchanged query counts; no financial or caching behavior was changed to compensate.
- Market release bundle generation succeeds; the available FX snapshot is dated 2026-10-11. The generated ZIP is not committed.
- Native WebView2/Android builds, signed packages, low-end-phone visual/motion and accessibility acceptance are pending.
  Browser screenshots do not replace [8J](../../issues/8-website/8J-cosmetic-parts-and-claiming.md) acceptance.
- Public tag publication requires owner approval under [release-check](../../skills/release-check/SKILL.md).

## Dated follow-ups

2026-10-26: preparation continues on `codex/release-1.5.0`; no tag or public release has been created.

2026-10-26: displayed version now agrees at 1.5.0. The repeated theme-switching browser run passed all four PC/phone and English/Arabic combinations; screenshots were refreshed after the version fix. Documentation links/catalogues and the theme compiler check pass.

2026-10-26: owner approved the contributor workflows; #117 passed PR checks and CodeQL and was merged at cfd693e5. Release-preparation head af8ac8c9 also passed both required workflows. Synchronizing the release notes with the contributor merge changes no application behavior.

2026-10-26: [manual package run #597](https://github.com/LightningEg/Lightning/actions/runs/40363515349)
used main 884476c2892816a9412ffa2ba42ee633e194a194. Android built, signed and passed its certificate/package checks.
Windows stopped before packaging: 273 tests passed, 12 skipped, and
`test_unpaired_or_revoked_pc_and_forged_signature_are_refused` failed with `DeviceCredentialError`.
The fixture changed `DeviceIdentity.device_id` to impersonate a paired PC, changing the authenticated binding
used to unseal its DPAPI-protected key. Windows correctly refused the altered binding before a forged request
could be sent; the fixture expected a network `ProtocolError`. The same failure was reproduced on Linux
with an injected AES-GCM protector, so the regression is now exercised on every host.
The fixture now claims the paired ID on the wire while signing with the stranger's unchanged identity.
It requires the phone's `UNAUTHORIZED` response and checks the legitimate PC still works before revocation.
Both default and injected protection cases pass; sync/credential tests: 31 passed, one Windows-only skip.
No application, credential-protection, signature-verification, signing or workflow code changed.
The full suite and required PR checks must pass before merge; a fresh manual build on the fixed main is
needed for Windows package evidence. Retrying #597 uses the old source and cannot apply the fix.

2026-10-26: full local suite after the #597 fixture fix: 2,687 passed, 11 skipped, 26 subtests passed in 564.65 seconds. All four import contracts and documentation/link checks pass. Native Windows packaging still needs the fresh build run.
