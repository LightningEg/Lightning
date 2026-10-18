---
title: Audit public repositories for personal data and security exposure
category: technical-improvement
area: tools
status: open
created: 2026-10-16
reporter: GPT-6
skills: none
app_version: 1.1.0b1
commit: a853d5d
repo: both
---

## Remediation status — 2026-10-18

App PR #19 is merged, preserving the owner-requested AI review/merge model. Live main and v* tag rulesets were inspected: PR/check/review requirements and admin bypass are active. The previewable `tools/security_setup.py` configures admin settings and moves known secrets; `CONTRIBUTING.md` › Owner: once is the setup. Organization/team grants and environment reviewers remain unverified because this connection cannot inspect their administration endpoints. Website, downloads and market-data main branches currently have no protection.

Website source fixes are prepared in [website PR #19](https://github.com/elfekimuhammed/Lightning_website/pull/19): literal feedback cells, field/request/row/image quotas, no logged or persisted dashboard key, authenticated reads in POST bodies with legacy GET refusal, and safe workflow input handling. They are not deployed. Deploy the Apps Script source and doPost router first, rotate the analytics key, then publish the dashboard. A complete replacement router now also validates survey/signup and writes new v2 tabs, with shared deduplication/session/global quotas. Browser forms wait for readable confirmation. A generated Apps Script bundle and a clasp backup/deployment script are supplied; live deployment remains pending. The existing feedback report remains open for its other UX and deployment work.

Journal development tooling was audited separately: npm initially reported three high-severity vulnerable packages (Miniflare via Sharp, Sharp, Undici). Wrangler 4.151.1 plus explicit Sharp 0.35.5 and Undici 7.29.1 overrides now produce zero npm audit findings; all 11 carrier tests pass. This changes development dependencies, not the deployed worker implementation. Revisit the overrides when upstream Miniflare adopts patched versions. All four pinned Python requirement sets returned no known PyPI advisories. GitHub's default-branch banner reported 13 dependency alerts before these fixes; this is not a claim that every GitHub alert has been closed.

Validation of website source: 11 new feedback security regressions, 98 receiver assertions, 75 dashboard browser assertions including POST-only key transport and locking during a pending load, 6 analytics-client privacy assertions, analytics rule checks, and site validation (62 pages, no errors; 12 existing warnings). Browser tests mock the remote receiver. The application PR's full Linux suite, import contracts, dependency review and CodeQL passed on GitHub.

Remaining: deploy/verify the live Apps Script receiver and verify the replacement survey/signup routes after deployment; verify team permissions, environment reviewers and absence of duplicate repository signing secrets; protect supporting repositories; triage remaining GitHub alerts; audit full history and binary releases. Public email metadata and historical analytics exports were not rewritten. No production credential value was printed or committed by this review. The older assessment below is the original 2026-10-16 evidence, not a statement that the prepared source fixes have reached production.

## Report

**Scope and method.** Read-only audit of the four public repositories owned by the same GitHub account as of 2026-10-16, on default branch `main`: app (761 tracked files), downloads (4), market data (7), website (884); **1,656 files inventoried** through complete, non-truncated Git trees. Reviewed selected source files, metadata and GitHub code-search matches. **This is not a byte-by-byte audit of every file or a complete Git-history/branch review.** Large binary files (including the Windows ZIP), screenshots, historical archive pages and some other files were not individually decoded or inspected. No live exploitation or dynamic testing was performed. Do not treat omitted findings as clearance.

### Confirmed exposures and security findings

1. **HIGH — Personal email in public commit author metadata.** Recent commits across the four repositories contain a personal-domain email address in Git author fields. The address is intentionally not copied into this public report. This is **public personal information**, not a credential. Anyone can retrieve metadata from the GitHub commit API. Changing future Git identity does not remove existing history. **Action:** use a GitHub `noreply` address for future commits, consider implications of history rewrite with collaborators/tags, and review older commits for further disclosure.

2. **HIGH — Analytics dashboard access key exposed to unnecessary surfaces.** Website `analytics/dashboard.html:216-235` keeps a privileged dashboard key in `localStorage` and transmits it as a **GET query parameter**. `apps-script/AnalyticsEventsReceiverPatch.gs:659-674` persists the same key in a spreadsheet cell and explicitly logs it. URL queries may be captured by browsing/network logs; script execution on the same origin can access local storage; the spreadsheet/logs broaden key access. **No hard-coded live value was found in the inspected source.** **Action:** remove key logging, use an authenticated server-side proxy or short-lived credentials (not key-bearing GET URLs), minimize browser storage, and rotate the key after migrating.

3. **HIGH (conditional impact) — Spreadsheet formula injection surfaces in public feedback receivers.** Website `apps-script/AppFeedbackReceiverPatch.gs:125-144` writes user-supplied descriptions, names and other fields directly to Sheets. `apps-script/UXTestsReceiverPatch.gs:51-71` likewise writes submitted feedback fields to Sheets without visible formula neutralization. A value beginning with a spreadsheet formula prefix may be interpreted as a formula. Whether practical exploitation succeeds depends on the deployed receiver and Sheets behavior; no exploit was attempted. **Action:** normalize untrusted values to literal text (not formulas) before writing; enforce limits and test with benign formula-shaped inputs.

4. **MEDIUM — Internal operational files are publicly accessible.** App `AGENTS.md`, `NOW.md`, `docs/PROJECT_OVERVIEW.md`, `docs/COMPETITION.md`, `docs/proposals/`, and `report/` expose coordination practices, roadmap, unresolved bugs, security design and product priorities. Website `CLAUDE.md`, `README.md`, `audit/`, `test.html`, `analytics/dashboard.html` and `apps-script/` reveal development workflow, analytics architecture and testing surfaces. `noindex` does **not** restrict access. Not intrinsically a vulnerability: owner should decide which operational details belong in a public source-available project. **Action:** classify public documentation versus private operational notes; do not presume that removing current files removes past commits.

5. **MEDIUM — Public write-only telemetry receiver invites abuse/metric poisoning.** `js/analytics.js` and `analytics/dashboard.html` publish the Apps Script receiver address, while `apps-script/AnalyticsEventsReceiverPatch.gs:268-342,689-750` accepts browser-submitted analytics events without a client authentication secret (as expected for anonymous analytics). Source contains daily row/visitor caps; these mitigate but cannot prevent fabricated traffic or quota exhaustion. The read-side dashboard checks a key (`analyticsRead_`, lines 804-807). **Action:** treat telemetry as untrusted, monitor anomalies/quotas, enforce server-side controls, and avoid using anonymous events as security signals.

6. **MEDIUM — Main-branch protection inconsistent.** GitHub branch metadata reported `main` protected in app but not in downloads, market-data or website at audit time. App exposed two active rulesets; exact app protection configuration was not inspectable due to integration permissions. **Action:** evaluate branch and tag protection, required review/checks and limited write credentials, especially for public download artifacts. Unprotected does not imply anonymous users can write.

7. **REVIEW — Network exposure is intentional but warrants acceptance testing.** App `lightning/runtime/devices.py:82` and `lightning/sync/transport.py:215` default a phone pairing/sync listener to `0.0.0.0` (all IPv4 interfaces). `lightning/sync/transport.py:220-223,336-349` uses TLS 1.3, a device certificate, and paired-device signature checks. **No authentication bypass was established.** **Action:** test pairing authorization, firewall/network visibility, revocation and rate limits on actual devices.

### Sensitive-looking assets and negative findings

- App `tests/fixtures/roundtrip/profile.db`, `keys.json`, `recovery.txt` are **publicly committed encrypted-profile test materials**, not automatically proof of a real user data leak. `tests/test_device_roundtrip.py` describes the profile as dummy, and `lightning/samples/generate_mohab_2026.py` generates seeded sample transactions. The binary database could not be decoded via the GitHub text connector; **independent validation that all records are synthetic remains required**. Do not reproduce the recovery value in issues or public audit documents.
- App `lightning/samples/mohab_2026/*.csv` contains named banks, salary, spending, investments and balances from a seeded fictional sample; disclosure is expected if verified synthetic.
- `Lightning-downloads` has a ~30 MB public Windows ZIP on `main`, plus releases not exhaustively reviewed here. **Contents, embedded strings, signing artifacts, configuration and bundled secrets not cleared**. Inspect locally with archive/file/hash/signature and malware tools before calling it clean.
- Site `tools/footer.py` contains business-domain contact email addresses and tester chat invite links. These appear intended for public visitors; verify the invites are appropriate for unrestricted circulation.
- Website `apps-script/AnalyticsEventsReceiverPatch.gs` has an empty source `ANALYTICS_SPREADSHEET_ID`, and repository workflows reference GitHub secrets by *name*. Neither observation establishes that secret values are published.
- The site root's IndexNow verification token file is intended to be public; it is not equivalent to a private API credential.
- The checked Android `network_security_config.xml` denies general cleartext traffic and permits HTTP only to `127.0.0.1`. App `lightning/runtime/http.py` has random session credentials and origin/host checks; no direct authentication bypass established.
- Targeted code searches did **not** confirm a production private key, GitHub personal access token, cloud API key or user financial database. These negative checks are incomplete because binary files, history and nonindexed material were not exhaustively scanned.

### Priority and acceptance criteria

1. **Now:** prevent future personal-email metadata leaks; review existing commit exposure; remove privileged analytics-key logging and query-string transmission; rotate key after remediation.
2. **Next:** harden and test both Sheets ingestion paths against formula injection; add abuse monitoring for public analytics; review branch and release protections.
3. **Before claiming clearance:** run `gitleaks` or `trufflehog` on **all refs/history**, inventory branches/tags/releases/Actions artifacts, inspect Windows ZIP and APK byte-for-byte, inspect archived screenshots and HTML, validate synthetic fixture provenance, and perform targeted runtime security tests.
4. **Public data policy:** keep this report redacted; avoid pasting private contact details, real finance records, unmasked secrets or private dashboard links. Decide which planning and internal coordination documents should be private, bearing in mind Git history persists.

**Assessment:** Confirmed personal-email disclosure; confirmed risky dashboard-key handling; unneutralized spreadsheet inputs; operational transparency that may exceed the owner's intended public surface. **No verified production credential leak or proven compromise.** This report records findings only and authorizes no changes to implementation, repository visibility, history, credentials or settings.
