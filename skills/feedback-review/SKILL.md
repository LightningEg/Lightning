---
name: feedback-review
description: Turn new user feedback into items in issues/, investigate each ticket, have Opus design the fixes and Sonnet build them (two agents at most), then delete the reviewed files. Use when new feedback, survey rows or screenshots arrive, or when old feedback files should be retired.
---

# Feedback review: compile, investigate, design, build, delete

Written for any AI tool (Claude, Codex, others). Where it names a model, use the closest you have: the strongest for design, a fast
capable one for everything else. In Claude Code that is `model: "opus"` and `model: "sonnet"` on the Agent tool.

Each feedback ticket becomes one item in `issues/` (read `issues/README.md` once; type `bug`, `polish`, `feature` or `tech`, in the milestone it belongs to).
A processed ticket's item is deleted with its fix; only a test, a changelog line and, for what stays open, its item survive.
No separate batch files and no screenshots folder pile up: git history keeps the rest.
The repo is public: nothing personal goes into it.

**Budget: two sub-agents per batch, never more, never in a loop.** Stages 1, 2 and 5 are done by you (the main session).
Only stage 3 (one design agent) and stage 4 (one build agent) are agents. Hand each agent a file path, not a pasted history.

## Token rules

- Grep for the class, id or text a ticket names; read only the lines around it. Never open a guideline or a whole large file.
- Look at a screenshot only when the ticket cannot be understood or reproduced without it; one look, no re-reads.
- Reproduce several tickets from one demo session (`python -m lightning --demo --no-browser`, port 8766); crawl with `curl`, not a browser, unless the ticket is visual.
- Group tickets by screen and investigate each screen once. Tests: changed areas first, full suite once at the end.
- Reports are short: one line per ticket, no restating the user's text.

## 1. Compile (you)

1. Input is whatever the owner gives: pasted rows, a CSV, files with screenshots. There is no Drive access here; ask for the files if they are missing.
2. Strip what must not be public: names, emails, phone numbers, account numbers, device ids, private links. Say "a user". Keep a screenshot only if it shows dummy or sample data; otherwise describe it in words.
3. Write one item per ticket in `issues/<n>-<name>/` (code from `python tools/issues.py next <n>`; front matter per `issues/README.md`; `by` is the AI, `skills: feedback-review`). The body: what the person saw, what they want, the screen, and the screenshot if it is kept, as a relative link to `screenshots/<code>-<n>.png` in the item's milestone folder (small, dummy data only; deleted with the item). Merge tickets that are the same finding into one item.
4. Merge duplicates, mark overlaps with existing items (read `issues/INDEX.md`), drop test and diagnostic rows and say how many.
5. Tell the owner: counts by category, the three biggest themes, anything that looks like a wrong number.

## 2. Investigate (you)

For every ticket, in this order, and write the verdict beside it:

1. Reproduce on the demo app, or read the code. If you cannot reproduce it, say what you tried; it is not "fixed".
2. If a figure is reported wrong, reconcile it across tabs first. A wrong figure outranks any layout wish.
3. Verdict: **Defect** (true, needs a fix), **Request** (an enhancement), **Existing** (already works; say where), **Not reproduced**, or **Conflicts** (with the guideline or a decision; say which). Add `file:line` for the cause.
4. Owner-only questions go to the owner as one GitHub issue, not into the file.

**Stop here and show the owner the Report.** The owner says which Defects and Requests to build. Do nothing further until they do.

## 3. Design (agent 1: strongest model, one call)

Launch one agent on the strongest model available. Its prompt names only: the items, the list of chosen tickets, `AGENTS.md`, and the rule to read code by grep, not whole files. It writes `user feedback/designs-NNN.md` (deleted with the batch):

- per ticket: files to change, the approach in a few lines, the test, risks;
- one section listing tickets that touch the same file, with the order to build them;
- anything that needs an owner decision (do not guess it).

It writes designs only; it changes no code.

## 4. Build (agent 2: fast model, one call)

Launch one agent on a fast, capable model. It gets the designs file path and `AGENTS.md`. It builds the tickets in the order given, one branch per feature (`claude/<feature>`, AGENTS.md §6), one test per ticket, changed-area tests after each, and the full suite once at the end. It pushes each branch and reports branch names, test results and anything it could not do. It does not merge.

You review the diffs, merge the branches into `main` one at a time and push.

## 5. Delete (you)

Only when every ticket has a verdict and every built ticket has a test and a changelog line:

1. A ticket left Open or Request keeps its item (status `ready` or `blocked`, with why); a Fixed, Built, Existing or Declined ticket's item is deleted and its code added to `done:`. Run `python tools/issues.py`.
2. One changelog entry for the batch, three lines at most.
3. `git rm` the processed items, their screenshots and the designs file.
4. `grep -rn "user-feedback-batch-NNN"` and repoint leftovers to the test or changelog.
5. Commit, push, merge to `main`, push.

## Rules

- Never more than two agents. If the work seems to need more, build fewer tickets per batch.
- Never delete a batch with an unverified ticket, or a left-over ticket without an item.
- Never put a respondent's identity, a private link or real financial data in the repo.
- Tell the owner only: counts, what was built, what is open and needs a decision.
