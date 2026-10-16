---
title: Public repositories expose identity metadata and need security hardening
category: technical-improvement
area: security
status: reported
created: 2026-10-16
reporter: ChatGPT
skills: none
app_version: 1.1.0b1
commit: a853d5d
repo: both
---

## Report

**Scope:** Read-only review of the four public repositories `Lightning`, `Lightning_website`, `Lightning-downloads`, and `Lightning_Market_Data` on 2026-10-16. This is a consolidated cross-repository security/privacy triage, not a claim of a complete forensic audit. File inventories covered 1,656 tracked files (761, 884, 4, and 7 respectively). Targeted source and configuration files and recent commit metadata were inspected. Binary release archives, all historical commits, and every archived website asset were **not** exhaustively inspected. No production exploit or secret validity testing was performed. No app, website, analytics, or security settings were changed.

### Findings (highest priority first)

1. **HIGH — Personal email appears in public commit metadata (confirmed privacy exposure).** Recent commits in all four repositories include author identities associated with a personal email domain. Email address intentionally omitted here. Anyone can inspect public commit author metadata. Configure a GitHub-provided no-reply address for future commits; assess the benefits and disruption of rewriting old history separately. Changing the current Git email does **not** remove existing metadata.

2. **HIGH — Analytics read-key handling exposes a sensitive value to unnecessary surfaces (confirmed code behavior).** In `Lightning_website/analytics/dashboard.html:216-217`, the dashboard saves the read key to `localStorage`; around `:232-235`, requests include it as a URL query parameter. In `Lightning_website/apps-script/AnalyticsEventsReceiverPatch.gs:659-674`, setup generates a key and line 674 writes it to Apps Script logs. Browser storage, request URLs, and logs are not appropriate default homes for reusable secrets. **Action:** remove secret logging, rotate the deployed read key after verifying exposure, and move authorization away from URL query parameters; consider a short-lived or server-mediated access design. The real deployed configuration was not verified.

3. **HIGH — User-controlled feedback fields are written to Google Sheets without visible formula neutralization (code-level injection risk, production impact unverified).** `Lightning_website/apps-script/AppFeedbackReceiverPatch.gs:125-144` writes fields such as descriptions/reporter details using `setValues`. `Lightning_website/apps-script/UXTestsReceiverPatch.gs:49-71` similarly writes submitted titles, reasons and page URLs. Spreadsheet cells beginning with formula-significant characters may be interpreted as formulas. **Action:** force untrusted values to literal text before writing, including leading `=`, `+`, `-`, and `@` as appropriate for Sheets; regression-test malicious input in an isolated test sheet. No live payload was submitted.

4. **MEDIUM — Internal work material is intentionally or unintentionally public (confirmed accessibility; disclosure sensitivity depends on owner).** `Lightning/NOW.md`, `AGENTS.md`, `docs/proposals/`, `docs/COMPETITION.md`, and open `report/` files disclose work in progress, bug status, internal processes and roadmap ideas. The website also exposes `audit/2026-10-03-website-audit.md`, `analytics/dashboard.html` and `test.html`. The latter two having `noindex` is **not** access control. **Action:** decide which content is meant to be public, then relocate sensitive operations/strategy material to a private repository or protected service. **This report itself is public if merged:** keep private identities, credentials and exploit payloads out of it.

5. **MEDIUM — Public telemetry endpoint can be spoofed or quota-exhausted (architectural abuse risk, not live-tested).** `Lightning_website/js/analytics.js` exposes the public Google Apps Script ingestion endpoint. Anonymous collection is expected, but code-enforced daily caps (including visitor, pageview, and row limits) could be consumed by fabricated traffic. **Action:** rate-limit upstream where feasible, separate analytics trust levels and monitor quota usage. Public endpoint URLs are not by themselves leaked secrets.

6. **MEDIUM — Three public repositories lack `main` branch protection (confirmed branch metadata at audit time).** `Lightning-downloads`, `Lightning_Market_Data` and `Lightning_website` report unprotected default branches; `Lightning` reports protected `main`. **Action:** require review/status checks where appropriate, restrict force pushes and protect distribution tags. Protection reduces accidental/compromised-account changes; this is not proof of an existing compromise.

7. **VERIFY — Encrypted test profile and recovery fixture publicly tracked.** `Lightning/tests/fixtures/roundtrip/profile.db`, `keys.json`, `recovery.txt`, and `expected.json` are public. Test code labels the profile a dummy encrypted fixture, and demo financial CSVs appear generated, but binary provenance and a definitive no-real-data guarantee were not established. **Action:** confirm these are entirely synthetic; avoid including any actual recovery material or financial records in public fixtures. Do not treat test fixtures as production leaks without evidence.

8. **VERIFY — Release ZIP and older artifacts not cleared.** The roughly 30 MB Windows release ZIP in `Lightning-downloads/downloads/v0.5.0-beta.1/`, historical Git objects, and roughly 591 archived website files were not inspected byte-for-byte for embedded keys, local usernames/paths, source maps, metadata or real data. **Action:** perform offline recursive binary/archive scanning and full-history secret scanning before issuing any all-clear.

### Additional observations

- The inspected Lightning LAN sync code binds to `0.0.0.0` but includes TLS, pairing and peer-verification safeguards; binding alone is not sufficient evidence of a critical weakness.
- References to `GOATCOUNTER_API_KEY`, `ANALYTICS_READ_KEY`, Android signing credentials, and market tokens appeared as environment/Actions secret names. **No confirmed plaintext production credential was found in reviewed source.** This is **not** a clean bill of health for uninspected assets or Git history.
- `Lightning_website` public business contact links and IndexNow verification material may be deliberately public, and must not be mislabelled as credential leaks.

### Proposed acceptance criteria

1. New public commits no longer publish personal email addresses; historical exposure is understood and an explicit owner decision is recorded.
2. Deployed analytics no longer logs reusable read keys or sends them in GET query strings; rotated credentials and access tests are documented.
3. Feedback and UX telemetry spreadsheet writes safely store user-controlled strings as literal values; automated formula-injection regression tests pass.
4. The owner signs off a public/private content inventory, including public reports, roadmaps, audit pages and prototypes.
5. Branch and release-tag governance is reviewed for all four repositories; telemetry abuse controls are assessed.
6. Fixture provenance, public downloadable binaries, historic Git objects and site archives have been scanned before reporting comprehensive clearance.

**Classification:** Security/privacy audit with confirmed identity exposure, confirmed unsafe key-handling patterns, and source-level input-validation risks. Severity is a triage estimate; production exposure and exploitability require separate validation. **No fixes applied by this report.**
