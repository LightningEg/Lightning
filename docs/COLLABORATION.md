# How we collaborate on Lightning

This is the owner's current workflow, built around the decisions in the 2026-10-18 conversation. It replaces the earlier separate-AI-account and team-based plan.

## Completed so far

- All four repositories are under `LightningEg`.
- The contribution guide is published inside the Roadmap page, outside the header. The old `forgeeks.html#build` link forwards to `forgeeks-roadmap.html#build` ([website PR #29](https://github.com/LightningEg/Lightning_website/pull/29)).
- The repository and website describe owner-account AI merges: use branches and PRs, pass checks, and do not hand the owner's credentials to contributors ([app PR #41](https://github.com/LightningEg/Lightning/pull/41)). Separate AI accounts are not required.
- `tools/configure_pr_workflow.py` is merged, with preview, settings backups and readback verification. The additional live protection rule has not been confirmed activated.
- The GitHub Contributors workflow contains `/take`, `/drop` and inactive-claim expiry. A complete contributor trial and Discord notification/claim integration have not been verified.

## The collaborator's path

1. **Start on the website.** Open the Roadmap contribution guide. The intended main invitation is **Join Discord to start**; aligning the Roadmap's primary button is still a follow-up.
2. **Enter Discord.** Read a short welcome in `#start-here`, then open `#find-a-task`. These channel names and their pinned instructions are planned; their setup has not been confirmed.
3. **Choose a numbered task.** Each Discord listing links to a GitHub issue and uses the same issue number, for example **Task #37**. The issue describes the problem, files to inspect and what finished means. Never publish personal financial records.
4. **Claim it.** Currently, comment `/take` on that GitHub issue and wait for assignment; `/drop` releases it. The future Discord claim button is described below. Nobody, including an AI, starts work on someone else's assigned issue.
5. **Make the change separately.** Contributors create a fork (their own copy) and a branch (a workspace for this change). Codespaces is an optional browser workspace using the contributor's own allowance. Owner-authorized AIs use branches through the owner's existing connected account. Nobody pushes directly to `main`.
6. **Send it for review.** A pull request proposes the change. Include `Closes #37` using the real issue number, describe the change and explain how it was tested.
7. **Check and improve it.** Automated tests run. A maintainer or owner-authorized AI reviews the latest changes. The contributor answers questions and fixes problems on the same branch until checks pass and discussions are resolved.
8. **Merge and finish.** The owner or an authorized AI squash merges using the owner account. The change enters `main`, the official shared version. The linked issue closes. Update the changelog before merging, then remove the completed branch after a successful merge. Planned Discord role/task updates happen only once the bot is implemented.

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

## Discord: welcome, tasks and help

The intended route is **website → Discord → numbered task → GitHub claim → branch → pull request → review → merge**. Discord welcomes people, lists tasks and provides help. GitHub records the issue, assignee, changes and review.

Planned channels:

- `#start-here`: read-only welcome, with one short explanation and a link to `#find-a-task`.
- `#find-a-task`: owner/moderator task listings, each showing the issue number, plain-language title, useful skills and GitHub link.
- `#help`: contributors can ask questions with their task link.

Suggested pinned welcome:

> Welcome to Lightning. Open #find-a-task and choose something small. Follow its GitHub link, comment `/take`, and wait until it is assigned to you. Make the change on your own branch and send a pull request. Ask in #help whenever you get stuck.

These are instructions to set up and verify, not a claim that the channels already exist. Copy decisions made in Discord onto the GitHub issue so contributors and AI sessions can find them.

## Proposed: numbered Discord claims and roles

The owner proposed using the GitHub issue number for a corresponding Discord role, for example **Task #37** and **Working on #37**. The bot must store the repository together with the number; if multiple repositories have an issue #37, show the repository name too so their claims cannot be confused. This is a proposal; no role assignment or Discord claim button has been implemented by these documentation changes.

The intended bot flow, once built:

1. Show a task card with **Claim task #37** and its GitHub issue link.
2. Verify which GitHub account belongs to the Discord member before recording a claim.
3. Check that the issue is open and available. Reserve it on GitHub first, then confirm the Discord role/task assignment. Two simultaneous requests must not both succeed.
4. Confirm the claim visibly and give the collaborator a place to discuss that task.
5. Remove the task role or update its discussion when the contributor drops it, the task is completed/merged, or an eligible inactive claim expires. An open active PR should retain its claim.
6. Keep GitHub and Discord consistent when someone claims or drops work from either place. Retry/report failed synchronization rather than showing a false success.

A task role is a label for coordination. It must not grant repository write access, merging, admin access, signing keys or permission to manage the server. The bot needs only the access required for its task, with secrets stored privately.

An alternative suggested in the conversation is one **Contributor** role plus a task discussion such as **#37 — Fix Arabic label**, with its assignee shown clearly. This avoids a separate role for every issue. **The role-per-issue versus shared-role/task-discussion choice remains open.** Do not treat either option as selected or deployed.

Until this integration exists, claim by commenting `/take` on GitHub; Discord is used for task links and help.

## Next implementation steps

1. Set up or verify the three Discord channels and pinned welcome.
2. Make the Roadmap's main invitation lead to Discord, retaining a secondary link to available GitHub issues.
3. Confirm whether numbered roles or a shared role with numbered discussions should represent assignments.
4. Build and configure the Discord/GitHub claim integration, including verified account linking, duplicate-claim protection and cleanup.
5. Activate and verify the stronger app/website GitHub protection with the owner-side setup tool. Merged source files do not activate live rules.
6. Run one harmless contribution from website entry through claim, branch, PR, checks and AI merge. Verify assignment cleanup and notifications, including drop and competing-claim cases, before calling the integration complete.

## Separate work

All four repositories have transferred to `LightningEg`. This setup changes collaboration protection only for the app and website. Downloads and scheduled market publication need their own publishing workflow decisions before protection changes.

The forgotten Android signing key is unresolved. No key or secret has been deleted or replaced. Investigate the existing signing capability before making a separate key-replacement change.

Previous deployment and security-audit procedures remain available in [the earlier document](https://github.com/LightningEg/Lightning/blob/a500d72f2a0b549dcdc35bd90fb9cc9a0aca8cbb/docs/COLLABORATION.md). They are reference material, not prerequisites or additional account rules adopted by this collaboration plan.
