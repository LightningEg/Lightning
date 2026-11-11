---
title: Audit public repositories for personal data and security exposure
type: tech
pillar: build
size: M
model: opus
status: ready
post: no
created: 2026-10-16
by: GPT-6
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

4. **MEDIUM — Internal operational files are publicly accessible.** App `AGENTS.md`, `NOW.md`, `ai/PROJECT_OVERVIEW.md`, `ai/COMPETITION.md`, `docs/proposals/`, and `report/` expose coordination practices, roadmap, unresolved bugs, security design and product priorities. Website `CLAUDE.md`, `README.md`, `audit/`, `test.html`, `analytics/dashboard.html` and `apps-script/` reveal development workflow, analytics architecture and testing surfaces. `noindex` does **not** restrict access. Not intrinsically a vulnerability: owner should decide which operational details belong in a public source-available project. **Action:** classify public documentation versus private operational notes; do not presume that removing current files removes past commits.

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

## Checked · 2026-11-08

- The four repositories now live under the `LightningEg` organization; `tools/security_setup.py` (preview by default, `--apply` with the owner's `gh` login) already holds rulesets for the app, website, downloads and market-data `main` branches, the `v*` tags, the environments and the secret moves. Whether the owner has run it with `--apply` is not recorded anywhere.
- Finding 1 is still live: `git log --format=%ae -50` shows the owner account's personal address on 48 of the last 50 commits (the squash merges). The address is not copied here.
- Finding 7 (pairing listener on all interfaces) is part of the native acceptance in [2C](../2-safe-for-real-money/IT-2C-ordinary-pc-acceptance.md) and [4A](../4-edit-journal-and-devices/NF-4A-edit-journal.md); it is not repeated below.
- The website half (finding 2, 3 and 5, the Apps Script receiver, website PR #19) lives in the website repository, which this session could not read; 1E3 starts by checking it.
- Release checks already refuse tracked key, keystore and database files (`tools/release_check.py` `PRIVATE_FILES`), but no tool scans Git history or the built ZIP/APK.

## Decided

- 2026-11-08, owner (1E2): (a) keep AGENTS.md, NOW.md, ai/ and issues/ public; security findings stay out of them.
- 2026-11-08, owner (1E1): (c) leave it: no email change and no history rewrite. Do not raise it again unless the owner asks.

## How to work on this item

Each step below is one pull request or one owner action. **A real finding is never written in a public issue, pull request, commit message, `NOW.md` or this file** (skill `security-sweep` › After): it goes to a private GitHub security advisory and the owner hears of it in the question tool; the public line says only "checked, N findings filed privately". Read `skills/security-sweep/SKILL.md` first. Run `python -m pytest tests/test_issues.py -q` after editing this file, and delete a step's heading in the same commit that finishes it.

## 1E4 Check the live website receivers against formula injection and key leaks · S · opus
1E3 done 2026-11-11 (owner: receiver deployed, analytics key rotated, secret updated).
Files: the website repository's `apps-script/` (read-only), its tests named in website PR #19.
Do: with the deployed receiver, send one benign formula-shaped value (`=1+1`) through each public form (feedback, UX tests, survey, signup) and check the sheet stores it as text. The dashboard half is dropped: analytics now live in the owner console on Supabase (owner, 2026-11-11) and `analytics/dashboard.html` only redirects, so no read key travels through a page. Report pass/fail per form to the owner in the question tool; a failure goes to a private advisory.
Done when: the owner has the pass/fail list, and this file has one dated line "1E4 checked, N findings filed privately".

## 1E6 Prove the committed encrypted fixture is the demo household · S · sonnet
Files: `lightning/runtime/roundtrip.py` (`make`, `run`, `expected`), `tests/test_device_roundtrip.py`.
Do: add `test_the_committed_fixture_is_the_generated_demo_household(tmp_path)` to `tests/test_device_roundtrip.py`: call `roundtrip.make(tmp_path)` (it builds the demo household up to `AS_OF` with fresh keys), then assert `expected(tmp_path)` equals `expected(FIXTURE)` line for line and that `run(FIXTURE)[0]` equals `run(tmp_path)[0]`. The fixture's own recovery key and password are dummy (`PASSWORD` in `roundtrip.py`); never print `recovery.txt`. If the lines differ only because the demo or schema changed since the fixture was made, rebuild with `python -m lightning.runtime.roundtrip --make tests/fixtures/roundtrip` in the same pull request and say so in `Detail:`.
Done when: `python -m pytest tests/test_device_roundtrip.py -q` passes with the new test.

## 1E7 Scan every repository's full history for secrets · M · opus
1E5 done 2026-11-11 (owner: protections applied, secret scanning and push protection on). GitHub's own alerts can be compared.
Files: none changed in the repositories; the scan runs in the scratchpad.
Do: clone each of the four repositories with all refs (`git clone --mirror`), run `gitleaks detect --source <mirror> --log-opts="--all"` (install the pinned release binary in the scratchpad; do not add it to the repository), plus `git log --all -p | grep -nE "(BEGIN [A-Z ]*PRIVATE KEY|ghp_|github_pat_|AKIA[0-9A-Z]{16})"`. Triage each hit as test/dummy, public-by-design (IndexNow token, public update and store keys in `lightning/security/*.json`), or real. Real ones: rotate first (owner, through the question tool), then a private advisory.
Done when: this file has one dated line per repository: "history scanned, N real findings filed privately"; nothing else about them is public.

## 1E8 Inspect the published Windows ZIP and Android APK · S · opus
Files: none changed; the newest release's ZIP from `Lightning-downloads` and the APK from the app's newest release, downloaded into their own empty scratchpad folder.
Do: list each archive (`unzip -l`); fail on any `.git/`, `tests/`, `*.db`/`*.sqlite`, `recovery.txt`, `keys.json`, `*.pem`/`*.key`/`*.jks`/`*.p12`, `.env`, a `Documents/Lightning` path or a name from the sample households outside `lightning/samples/`; run `strings` over the binaries for the patterns of 1E7; compare the APK's permissions (`aapt dump permissions` or `apkanalyzer`) with `packaging/android-permissions.txt`. If a check belongs in every release, add it to `tools/release_check.py` with a test in `tests/test_release_check.py` (create it if missing) in its own pull request.
Done when: this file has one dated line naming the two versions checked and "N findings filed privately"; any new release check passes `python -m pytest tests/test_release_check.py -q`.

## 1E9 Triage the open dependency alerts · S · opus
Files: `pyproject.toml`, `requirements/*.in` and locks, `cloudflare/journal/package.json` as the alerts point; skill `dependency-change`.
Do: list open alerts with `gh api repos/LightningEg/Lightning/dependabot/alerts --jq '.[] | select(.state=="open") | [.number,.dependency.package.name,.security_advisory.severity] | @tsv'` (needs the owner's login or a session with access). For each: update through skill `dependency-change` (one pull request per group), or dismiss with a written reason when the vulnerable code is not reachable (development-only, not shipped). Revisit the Sharp and Undici overrides in `cloudflare/journal` noted above.
Done when: the alert list is empty or every open alert has a dismissal reason, and `cd cloudflare/journal && npm ci --ignore-scripts && npm audit --audit-level=high` is clean.

## 1E10 Close the item · S · sonnet
Needs 1E4, 1E6, 1E7, 1E8 and 1E9 done first.
Files: this file; `SECURITY.md` (only if a step changed what it says is checked); `issues/1-easy-to-contribute/README.md` (`done:` line).
Do: check that every finding in the Report is either fixed (name the commit or the owner's dated answer), filed privately (say only that), or accepted by the owner. Then delete this file and add `1E` to `done:` (AGENTS.md §3).
Done when: `python -m pytest tests/test_issues.py tests/test_docs_structure.py -q` passes.
