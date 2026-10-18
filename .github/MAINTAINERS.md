# Maintainers: collaboration and security setup

Who may do what, and the GitHub settings that enforce it. The files in this repo carry the rules; the settings below
are the part only a repository admin can switch on (they cannot be committed).

## People

| Group | How they work | Access |
|---|---|---|
| Owner (`@elfekimuhammed`) | Reviews and merges everything | **Admin**: the only Admin |
| Internal team (trusted humans) | Fork, branch `who/feature`, open PRs from the fork; triage issues and PRs | **Triage**, through one team `internal`. Triage cannot push or merge |
| AI agents (Claude, Codex, Luna) | Push their own branch, open a PR, may merge when the rules below are met | **Write**, through team `ai-reviewers`, each AI on its **own bot GitHub account** |
| Open contributors (unknown) | Fork, branch, open PR from the fork | **None**. They never get Write until you decide |

Nobody pushes to `main`; every change is a PR. You (Admin) can merge anything. An AI may merge a PR only when **all** hold:
green `tests`, `dependency-review` and `analyze`; every conversation resolved; one approval from the owner or from a
*different* AI account than the author (GitHub blocks self-approval); no path owned only by the owner touched
(`.github/`, `packaging/`, `android/`, `cloudflare/`, `tools/`, AGENTS, LICENSE, SECURITY); and the PR author is the owner,
the `internal` team or an AI. **Only you and the AI accounts hold Write or Admin, so only you and the AIs can merge.** Humans never get Write.
PRs from outside contributors are merged by you only.

**Do not give the AIs your own login.** An AI running as `@elfekimuhammed` is Admin and bypasses every rule. Give each AI a
separate bot account (Claude, Codex, Luna), add them to `ai-reviewers`, and never to Admin.

## Switch on once

**Fast path:** run `bash .github/apply-settings.sh` (Git Bash on Windows) as the owner (needs `gh auth login`). It does steps 1-5 below. Step 6 and
the bot accounts stay manual. The script is untested against GitHub; read its errors if a call fails.

**By hand:**

1. **Rules › Rulesets › New › Import a ruleset:** import [rulesets/main.json](rulesets/main.json), then
   [rulesets/tags.json](rulesets/tags.json). Result: `main` accepts changes only through a squash-merged PR that is
   approved by a code owner (you, or `ai-reviewers` outside owner-only paths), has green `tests`, `dependency-review` and
   `analyze`, and has resolved conversations. These rules apply to AIs too; only Admin can bypass. No force-push, no deletion. Only Admin creates `v*` release tags.
   Check afterwards: open a test PR as a non-admin and confirm the Merge button is disabled.
2. **Actions › General:**
   - Fork pull request workflows: **Require approval for all external contributors** (nothing from a stranger runs until you click Approve).
   - Workflow permissions: **Read repository contents** only; untick *Allow GitHub Actions to create and approve pull requests*.
   - Actions permissions: allow GitHub-owned and verified actions only.
3. **Advanced Security (Code security):** enable *Private vulnerability reporting*, *Dependency graph*, *Dependabot alerts and
   security updates*, *Secret scanning* with **Push protection**, and *Code scanning* (CodeQL runs from `codeql.yml`).
4. **General › Pull Requests:** allow **squash merging** only; tick *Automatically delete head branches*; untick *Allow auto-merge*.
5. **Collaborators and teams:** create team `ai-reviewers` (**Write**, bot accounts only) *before* merging CODEOWNERS, and team `internal` (**Triage**, trusted humans: they can label, assign and comment, but not push or merge). Keep Admin to yourself.
   Under the organisation: *Authentication security* › require 2FA for all members; base permission **No permission**.
6. **Environments** (the names the workflows already use): `android-signing` (the four `ANDROID_*` signing secrets) and
   `production-release` (`LIGHTNING_DOWNLOADS_TOKEN`): *Required reviewers* = you, deployments from `main` and `v*` tags only.
   `market-publishing` (`LIGHTNING_MARKET_TOKEN`): `main` only, no reviewer, since it runs on a schedule. Add each secret to its
   environment, then delete the repository-level copy. Then no workflow can read a signing key or push a release without your click.
7. **Your account:** 2FA with a passkey or hardware key.

## Rules of the repo files

- `pr-checks.yml` and `codeql.yml` use `pull_request`, never `pull_request_target`: fork code runs with a read-only
  token and no secrets. Keep it so; never add a workflow that checks out fork code with secrets.
- `CODEOWNERS` assigns the owner to every path; changes under `.github/`, `packaging/`, `android/`, `cloudflare/`, `tools/`
  need extra attention, since they run on machines or ship to users.
- Review a fork PR before approving its workflow run: read the diff for changes to workflows, `tests/conftest.py`,
  `tools/` and install/build scripts first.
- Never paste a secret into a PR, issue or log. If one leaks, revoke it first, then clean up.

## Promoting someone

Open contributor → after a few good merged PRs, invite to team `internal` (Triage). Revoke the same way. Neither
changes who can merge to `main`.
