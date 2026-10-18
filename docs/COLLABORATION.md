# How we collaborate on Lightning

This is the owner's current workflow, built around the decisions in the 2026-10-18 conversation. It replaces the earlier separate-AI-account and team-based plan.

## One change, one branch, one pull request

1. **Publish a task.** The owner or an AI creates a GitHub issue describing the problem, what a finished fix looks like, and which files to inspect. Use fictional examples, not personal financial records.
2. **Share it.** The website's Roadmap page contains the contribution guide and links to available issues. Share those links in Discord so people can find work and ask for help.
3. **Claim it.** The contributor comments `/take` on the GitHub issue and waits for the bot's assignment. `/drop` gives it back. Nobody, including an AI, starts work on someone else's assigned issue.
4. **Make the change separately.** Contributors use a fork (their copy of the repository) and a branch. Owner-authorized AIs use a branch through the owner's existing connected account. Nobody pushes directly to `main`.
5. **Propose the change.** Open a pull request, include `Closes #123` for the issue and explain how the change was tested.
6. **Check and review.** Automated checks run. A maintainer or owner-authorized AI reviews the latest changes, answers questions and resolves review discussions. Fix failed checks before merging.
7. **Merge.** The owner or an authorized AI squash merges the PR using the owner account. The proposed change becomes part of `main` and GitHub closes the linked issue. Update the changelog before merging.

## Accounts and access

AI sessions use the owner's existing connected GitHub account. The owner does not want separate AI accounts or credentials handed to contributors. GitHub cannot accept that account approving its own PR, so a separate approving identity is not required by this workflow.

Contributors use their own accounts and submit PRs from forks. No new team hierarchy or repository write grants are assumed by this plan. The owner retains control of settings and authorizes AI work. Permission to merge code does not authorize signing releases, replacing keys, sharing credentials or weakening protection.

## GitHub enforcement

Use the setup in [.github/MAINTAINERS.md](../.github/MAINTAINERS.md):

```bash
python tools/configure_pr_workflow.py
python tools/configure_pr_workflow.py --apply
```

The preview reads settings without changing them. Apply adds and verifies a rule for the app and website requiring PRs, current passing checks, squash merging and resolved discussions, with no bypass. It blocks direct default-branch pushes, force pushes and deletion while allowing owner-account PR merges without a second approving account. Existing check requirements are retained. Conflicting approval rules stop setup before any writes.

Committing these instructions does not activate live GitHub settings. The current connection can create and merge PRs but cannot change repository rules. Owner-side activation remains pending until this command succeeds.

## Discord and claims

Use Discord to share available tasks and answer questions. The assignment is the GitHub issue's assignee and `taken` label. Comment `/take` on the issue, not in Discord. Copy decisions from Discord onto the issue so contributors and AI sessions can find them later.

The existing GitHub Contributors workflow implements `/take`, `/drop` and expiry after inactivity. Its live execution and notification delivery still need an end-to-end check before advertising a working Discord integration. A custom Discord claiming bot is not part of the current implementation.

## Separate work

All four repositories have transferred to `LightningEg`. This setup changes collaboration protection only for the app and website. Downloads and scheduled market publication need their own publishing workflow decisions before protection changes.

The forgotten Android signing key is unresolved. No key or secret has been deleted or replaced. Investigate the existing signing capability before making a separate key-replacement change.

Previous deployment and security-audit procedures remain available in [the earlier document](https://github.com/LightningEg/Lightning/blob/a500d72f2a0b549dcdc35bd90fb9cc9a0aca8cbb/docs/COLLABORATION.md). They are reference material, not prerequisites or additional account rules adopted by this collaboration plan.
