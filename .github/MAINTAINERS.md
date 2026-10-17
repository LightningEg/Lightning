# Maintainers: collaboration and security setup

Who may do what, and the GitHub settings that enforce it. The files in this repo carry the rules; the settings below
are the part only a repository admin can switch on (they cannot be committed).

## People

| Group | How they work | Access |
|---|---|---|
| Owner (`@elfekimuhammed`) | Reviews and merges everything | **Admin**: the only Admin |
| Internal team (trusted) | Push branches `who/feature`, open PRs | **Write**, through one team `internal` |
| Open contributors (unknown) | Fork, branch, open PR from the fork | **None**. They never get Write until you decide |

Merging to `main` is the owner's alone. Write access lets someone push a *branch*, never `main`.
AIs (Claude, Codex, Luna) work like the internal team: they push their branch and open a PR; the owner merges.

## Switch on once (Settings of the repository)

1. **Rules › Rulesets › New › Import a ruleset:** import [rulesets/main.json](rulesets/main.json), then
   [rulesets/tags.json](rulesets/tags.json). Result: `main` accepts changes only through a squash-merged PR that is
   approved by the code owner, has green `tests`, `dependency-review` and `analyze`, and has resolved conversations. The
   `update` rule blocks every merge except by the Admin bypass, so a collaborator with Write cannot merge even after
   approval. No force-push, no deletion. Only Admin creates `v*` release tags.
   Check afterwards: open a test PR as a non-admin and confirm the Merge button is disabled.
2. **Actions › General:**
   - Fork pull request workflows: **Require approval for all external contributors** (nothing from a stranger runs until you click Approve).
   - Workflow permissions: **Read repository contents** only; untick *Allow GitHub Actions to create and approve pull requests*.
   - Actions permissions: allow GitHub-owned and verified actions only.
3. **Advanced Security (Code security):** enable *Private vulnerability reporting*, *Dependency graph*, *Dependabot alerts and
   security updates*, *Secret scanning* with **Push protection**, and *Code scanning* (CodeQL runs from `codeql.yml`).
4. **General › Pull Requests:** allow **squash merging** only; tick *Automatically delete head branches*; untick *Allow auto-merge*.
5. **Collaborators and teams:** create team `internal`, give it **Write**, add trusted people. Keep Admin to yourself.
   Under the organisation: *Authentication security* › require 2FA for all members; base permission **No permission**.
6. **Environments › New `release`:** *Required reviewers* = you. Move `LIGHTNING_DOWNLOADS_TOKEN` and the
   `ANDROID_KEYSTORE_*` secrets into it, and give the jobs that publish `environment: release`. Then no workflow can
   read a signing key or push a release without your click.
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

Open contributor → after a few good merged PRs, invite to team `internal` (Write). Revoke the same way. Neither
changes who can merge to `main`.
