# Lightning collaboration and security plan

Prepared 2026-10-18. This plan retains the AI review and merge model in app PR #19, as requested.

App PR #19 was merged after GitHub reported 2,051 tests passed, 19 skipped, four import contracts kept, and successful dependency review/CodeQL. AI powers remain as requested.

## What was verified

| Repository | Current owner | Main protected? | Purpose |
|---|---|---|---|
| Lightning | LightningEg | Yes | Application, builds, sync and journal |
| Lightning_website | elfekimuhammed | No | GitHub Pages marketing site and Apps Script source |
| Lightning-downloads | elfekimuhammed | No | Public downloads and release artifacts |
| Lightning_Market_Data | elfekimuhammed | No | Published market prices |

The application has two active rulesets. Its main ruleset requires a PR, one code-owner approval, approval after the latest push, dismissed stale approvals, resolved discussions, linear history, squash merging, and up-to-date `tests`, `dependency-review` and `analyze` checks. Repository admins have a PR-only bypass. Its `v*` tag ruleset restricts creation, updates and deletion, with an admin bypass. These settings were read from GitHub, not inferred from files.

Organization membership, team membership, team repository grants, organization 2FA, Actions settings and environment reviewers could not be read through this connection. The table below specifies what to verify; it does not claim those settings have already been applied.

## 1. Confirm who can do what

Open LightningEg → Teams and Lightning → Settings → Collaborators and teams. Reuse the existing teams; avoid duplicate grants to individual users.

| Identity/team | Repository permission | Daily work | May merge? |
|---|---|---|---|
| Owner, @elfekimuhammed | Admin | Settings, sensitive approvals, releases | Yes |
| `internal` | Triage | Issues, labels, assignments; code changes from forks | No |
| `ai-reviewers` | Write | Branches, PRs, independent review | Yes, within PR #19's policy |
| Outside contributors | No membership needed for public repositories | Fork and submit a PR | Owner merges their PRs |

Check inherited permissions as well as direct grants. A person in another team with Write or Maintain still has that higher permission. Triage does not grant push access, so your internal contributors use forks under this model. Do not put human collaborators in the AI team just to give them convenient branch access if you want to preserve PR #19's human/AI distinction.

Use a separate authenticated identity for each AI reviewer. Two models using the same GitHub account are one reviewer to GitHub; neither a model's prose nor a second chat is an independent GitHub approval. Branch names and commit author labels do not establish identity. The current connection performs writes as the owner's account, so it is suitable for explicitly authorized owner operations, but it does not demonstrate separate AI identities.

Give AI identities Write, not Admin, and no branch-rule bypass. Limit installation/token access to the repositories they actually work on. Prefer short-lived credentials where supported. Never copy the owner's credentials into a collaborator's environment.

## 2. Check organization defaults

In LightningEg → Settings:

1. Under Member privileges, set base repository permissions to **No permission**; grant access through teams.
2. Under Authentication security, require 2FA after members have enrolled. Keep recovery methods private.
3. Review organization owners and repository admins. Keep the owner's intended admin boundary; do not grant Admin to AI accounts.
4. Review installed GitHub Apps and OAuth applications. Keep only the repositories and permissions each tool needs.
5. Review invitations and outside collaborators. Remove expired or unused access.
6. Enable private vulnerability reporting, dependency alerts, security updates, secret scanning and push protection where available.

This session did not change organization-wide permissions or remove members.

## 3. Verify the application's rules after PR #19 merges

Open Lightning → Settings → Rules → Rulesets. Keep the existing two active rulesets rather than importing duplicates.

1. Confirm the main ruleset targets the default branch and lists the exact check names `tests`, `dependency-review`, `analyze`.
2. Keep one approving review, code-owner review, dismissal after a new push, approval of the latest push by someone else, and discussion resolution enabled.
3. Keep branches up to date before merging, block force pushes and branch deletion, and allow squash merging.
4. Confirm `CODEOWNERS` recognizes `@LightningEg/ai-reviewers` with no errors. That team must be visible and have explicit Write access to this repository.
5. Confirm PR #19's owner-only paths still name the owner: `.github/`, AGENTS/CLAUDE instructions, LICENSE, SECURITY, packaging, Android, Cloudflare, tools and `tests/conftest.py`.
6. Confirm admins are the only bypass role; AI users must not inherit that role.
7. Using a non-admin AI identity, open a harmless test PR. Confirm it cannot merge before checks and a different reviewer's approval. Push another change and confirm the approval is dismissed.
8. Open an owner-only-path test PR and confirm an AI review cannot satisfy its code-owner requirement. Close test PRs afterwards.

GitHub's built-in controls enforce checks and code-owner approval. They do not fully enforce every sentence of PR #19's policy. In particular, Write normally includes the ability to merge an otherwise eligible PR; CODEOWNERS controls whose approval is required, not who presses Merge. The ruleset does not distinguish outside-contributor PRs from internal PRs, or prohibit an AI from pressing Merge on a sensitive PR after owner approval. Keep those restrictions as agent policy; if you need them technically enforced later, use a dedicated merge service that validates author membership, changed paths and reviewer identity before using its credentials. This observation does not remove the AI powers you requested.

Do not blindly run `.github/apply-settings.sh` against an established setup: it selects the first ruleset matching a target rather than matching its name and can overwrite another ruleset. Compare the live settings first. PR #19 is preserved; the script was not executed during this review.

## 4. Protect secrets and releases

Inspect the workflows already present rather than creating a different environment name from a generic checklist:

1. Use **android-signing**, already referenced by `android-app.yml`, for Android signing secrets.
2. Use **production-release**, already referenced by `desktop-probe.yml`, for the downloads publishing token.
3. Configure owner review and allowed deployment branches/tags for each environment: main and the intended protected release tags. Review plan availability if a GitHub plan limits protection features.
4. Move sensitive repository-level secrets to those environments and remove the redundant repository-level copies once the workflow has been adapted and tested. Environment protection cannot protect a duplicate repository secret.
5. The security PR removes repository-level Android secret forwarding; only the protected signing job reads the environment keys. The build-planning notice now defers key checks to that job. After migration, verify a manual matched build before tagging a release.
6. Give the downloads token access only to the downloads repository and only the contents permissions publishing needs. Use separate credentials for market-data publishing and analytics.
7. Keep PR workflows on `pull_request`. Never run fork code with production secrets through `pull_request_target` or a privileged `workflow_run` shortcut.
8. Keep the default Actions token read-only, disable Actions creating/approving PRs, and require approval for all external contributors' workflow runs. An approved run is permission to spend CI resources, not approval of the PR.
9. Review the diff before approving a fork run, including dependency install scripts, tests/conftest.py, build scripts and workflow changes. Keep third-party actions pinned and allow only required actions.

A collaborator with Write can author a workflow on a branch. Main protection alone is not a secret-access boundary. Environment restrictions, separate identities and narrowly scoped credentials matter especially when giving AI agents Write.

## 5. Use one repeatable contribution workflow

For every human or AI change:

1. Create an issue with the intended behavior, acceptance criteria, and dummy reproduction data. Report vulnerabilities privately instead of in public issues.
2. Assign one owner and a label such as bug, feature, security or documentation. Put work in a simple Project board: Backlog → Ready → In progress → In review → Done.
3. Read AGENTS.md and NOW.md. Check existing claims so parallel sessions do not overwrite one another.
4. Start from current main. Use one branch per finished change, named `who/feature`. Internal humans and outside contributors branch in their own forks; AI writers branch in the repository with their own identities.
5. Make small coherent changes. Never include real profile databases, backups, personal financial screenshots, credentials or analytics exports. Synthetic test fixtures are allowed when clearly documented.
6. Run relevant tests; run the repository-required full suite before pushing completed work. Update the changelog and the appropriate handoff/design documents.
7. Open a PR describing the problem, resulting behavior, test evidence and remaining risk. Keep new functionality separate from dependency-only updates where practical.
8. A different identity reviews the exact latest diff. Check failures and discussions must be resolved; a new push needs fresh review.
9. For ordinary trusted-author PRs, an AI may merge only when all PR #19 conditions hold. The owner handles sensitive paths and outside contributions. Do not manufacture a second approval with another chat using the same account.
10. Squash merge, delete the completed branch, close linked issues, and update the board and handoff. A merge does not automatically authorize publishing signed releases or changing organization settings.

Financial calculations, database migration, backup/restore, profile encryption, authentication and sync changes should state their failure modes and regression evidence explicitly even where CODEOWNERS does not make them owner-only.

## 6. Bring the supporting repositories into the same operating model

Organization teams cannot be granted access to repositories owned by a personal account. You can keep personal repositories with individual grants, but transferring them to LightningEg makes team management consistent.

Plan transfers separately; this session did not transfer repositories. For each one, check GitHub App installations, Actions secrets, environment protection, branch/tag rules, and integrations afterwards. Update hard-coded `elfekimuhammed/...` references in application release workflows, analytics scripts, download links and market-data URLs. GitHub redirects help but are not a substitute for verifying the real download and publishing paths.

For the website, preserve CNAME/custom-domain verification, DNS and Pages source settings, then verify HTTPS and English/Arabic pages. Protect main with PR review and website checks. Existing CLAUDE.md instructs automatic merging; align that file through a reviewed change when adopting the organization's policy.

For downloads, restrict write access to the owner and the publishing identity. Protect release tags and prefer immutable releases where supported. Verify artifact checksums, signatures/attestations and update provenance; do not allow general AI write access to shipped binaries merely because AIs can review application code.

For market data, allow only the price-publishing identity to update the intended data path/branch. Use a separate publishing branch or narrowly controlled bot exception if scheduled updates would otherwise be blocked by human-review requirements. Humans change collector code through PRs. The app must continue validating schemas, hashes and resource bounds when consuming public price files.

## 7. Run the parts that require your account

The available connection can push/review/merge PRs, but cannot administer all GitHub organization/environment settings or deploy into your Google Apps Script account. These scripts make those remaining actions repeatable. Run them from reviewed checkouts as the repository/Google project owner. They never ask you to paste credentials into chat.

**GitHub setup:**

```bash
gh auth login
python tools/security_setup.py
python tools/security_setup.py --apply --org-controls
python tools/security_setup.py --apply --migrate-secrets
```

The first script invocation is a read-only preview. `--apply` configures the existing AI/Internal team grants, app rulesets without replacing unrelated rulesets, protection for supporting repositories, read-only Actions tokens, fork-run approval, GitHub-owned actions plus the two pinned Android/Gradle actions already in use, security features and protected environments. `--org-controls` also enforces organization 2FA and no default access; ensure members have recovery methods first. It fails visibly on an API/plan/permission error and can be rerun after that error is corrected. No repository transfer or membership removal occurs.

`--migrate-secrets` asks privately for the existing signing values. GitHub cannot return existing secret values. It writes the four Android keys into **android-signing** before removing their repository copies, and can move publishing/analytics values to their matching environments. Keep the original secret values in your private secret manager. Empty input cancels the signing migration; empty optional publishing/analytics input leaves that secret unchanged. Do not put secrets in command-line arguments.

The environment policies are: owner review plus main/v* for **android-signing** and **production-release**; main only, without manual review for scheduled **market-publishing** and **website-analytics**. Market main updates are limited to admin identities, plus an optional dedicated GitHub App supplied with `--market-publisher-app-id`. Verify your existing publisher identity before applying that rule, so a non-admin price publisher is not accidentally blocked. The script never grants general AI or general GitHub Actions bypass on the price feed.

The website's required check is **website-security**, added by its security PR. Merge that PR after deploying the receiver, then apply its required check. The app's journal-security check and npm Dependabot configuration cover the patched development tree.

**Apps Script source and deployment:** use the website repository's `tools/deploy_receiver.py`. It builds a single complete `LightningAppsScript.gs` from four reviewed source files. Install the bundle by itself; do not paste it alongside duplicate legacy entry points or patch files.

```bash
npm install -g @google/clasp
clasp login
python tools/deploy_receiver.py
python tools/deploy_receiver.py --apply --script-id YOUR_EXISTING_PROJECT_ID --deployment-id YOUR_EXISTING_DEPLOYMENT_ID
```

The project ID is in Apps Script → Project Settings. The deployment ID is the identifier between `/s/` and `/exec` in the existing receiver URL. Enable the Google Apps Script API if clasp requests it. The deploy script clones the existing project into a temporary directory and creates a private ZIP under `.security-backups/` before replacing source. Backups are ignored by Git and can contain private legacy configuration. The same web-app deployment URL and Script Properties are retained; spreadsheet rows are not deleted. Because the original survey layout was unavailable, new survey/signup records use separate **Survey responses v2** and **Email signups v2** tabs. App feedback, UX and analytics keep their existing tabs.

The replacement includes the complete doPost/doGet router, so you do not need to hand-edit routes. For a spreadsheet-bound script it uses the existing spreadsheet. A standalone project needs the private Script Property **WEBSITE_FORMS_SPREADSHEET_ID**. Existing analytics spreadsheet selection remains separate. If Google requests new Drive/Sheets/trigger scope authorization, approve it in the Apps Script editor as the project owner.

After deployment, run **rotateAnalyticsReadKey** once from the Apps Script editor. It updates the private Dashboard key tab without logging the value. Then set the matching GitHub environment secret privately:

```bash
python tools/security_setup.py --apply --analytics-key
```

Finally publish the website PR. Confirm a dummy survey, signup, app ticket and UX response each reaches its intended tab; a formula-shaped test value displays as text; the dashboard unlocks by POST; GET cannot read analytics; a rejected submission shows an error. Browser tests mock Google: live CORS/redirect/scope behavior must be verified after your deployment. If verification fails, use the private source backup/previous deployment version; the deployment script never claims to verify the entire live flow.

All four form types now pass through a shared server gate: filled honeypot rejection, strict known survey fields/choices, length/body/row limits, duplicate suppression, five submissions per client form session per ten minutes, thirty form requests per minute globally, and three hundred requests per form type per UTC day. App/UX feedback retain additional row/image caps. The client waits for a readable receiver confirmation before showing success, and failed storage writes are retryable. These are bounded anti-spam controls: session IDs and timing can be forged, caches can evict records, and a determined bot can consume the shared quota. CAPTCHA or a backend with IP-level limits remains an option if abuse warrants it; there is no claim that these public forms are spam-proof.

## 8. Maintain access and security

Weekly: triage Dependabot/CodeQL alerts, pending reviews, failed checks and receiver quota failures. Monthly: review team membership, direct grants, installed apps, token scope and release-environment access. On departure: remove grants, revoke credentials accessible to that collaborator, and review recent Actions/release activity.

Use GitHub's private email setting and a GitHub noreply commit address for future commits. Existing history already contains personal email metadata and old analytics exports; this review did not rewrite history. A history rewrite needs its own coordinated migration.

The review is a targeted source/configuration audit with tests, not a penetration-test certificate. Production Apps Script, DNS/TLS/HTTP response headers, complete Git history and every binary release remain outside the completed validation. The existing redacted public-repository security report records evidence and outstanding items; no claim is made that every GitHub dependency alert is already closed.
