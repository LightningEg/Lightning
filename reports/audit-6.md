# Audit 6: open pull request cleanup

2026-10-23 · Codex · starting app main `fdbea6b`, website main `8a8a5c0`.

The owner requested review and cleanup to zero open PRs. Original branches are retained. Changes are reconciled against current main and tested together before squash merging; closure does not delete source branches.

| Repository / PR | Disposition |
|---|---|
| Website #20, #21, #22 | Combined and merged in #57; website-security passed. |
| App #42 | Replace obsolete 1.3 headers with source 1.4.3 / published 1.4.2 and current roadmap wording. |
| App #47 | Incorporate pinned Actions upgrades; preserve permissions and release gates. |
| App #76 | Incorporate Overview cards, five-column holdings and Spending flows; preserve current phone hero and More routes. |
| App #78, #79 | Incorporate report and efficiency fixes. Older audit becomes Audit 5; its reused 2G–2K and 3AC codes become 2P–2T and 3AF. 9J–9L remain open. |
| App #91 | Record existing v1.4.2 publication and finish 2D documentation. |
| App #101, #104, #106, #107 | Incorporate correctness audit, cash lifecycle validation, accurate Save outcomes, stale-form guards and retryable mass edits. Preserve #111's Delete confirmation and device-status fixes. |
| App #103 | Defer: input-only upgrade fails the Android lock contract and needs matching native wheels. Follow-up: [1H](../issues/1-easy-to-contribute/1H-coordinate-packaged-dependency-refresh.md). |

## Remaining scope

2M retains its three form revision fields as a reviewable patch; its issue remains open. The native-device and recovery acceptance work in 2A–2C and 4A remains open. This cleanup does not sign or publish a release, alter repository protections, or delete remote branches.

## Validation

Website: feedback security, website receiver, analytics receiver/rules, deployment unit tests and generated receiver syntax all pass; site checker reports 76 pages, zero errors and 14 existing warnings. The final integration's GitHub website-security check passed before #57 was merged.

App: full local suite: 2,457 passed, 10 skipped; one workflow-pin consistency failure identified missing updates in workflows added after #47, then corrected and checked again. All four import contracts pass. Journal worker: 12 tests pass, npm audit reports zero vulnerabilities. Final-head CI results belong to the integration PR.

Browser review: ten English/Arabic PC/phone captures of Overview, holdings, Spending and More; no horizontal overflow or JavaScript errors. Review samples: [PC cards](audit-6/overview-pc.png), [Arabic holdings](audit-6/holdings-arabic.png), [Arabic phone](audit-6/overview-phone-arabic.png).
