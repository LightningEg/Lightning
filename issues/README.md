# Issues: the plan and every open item

Everything still to do lives here: bugs, polish, features, under-the-hood work and what only the owner can do. It is grouped
into numbered **milestones**, worked on in order. The repo is public: no names, emails, real financial data or private links.

**To find something, read [INDEX.md](INDEX.md) only** (every milestone with its items under it), then open the one item you
need. The index is generated: `python tools/issues.py` rewrites it, `--check` verifies it (a test runs the check).

## Codes

Every item has a code: the milestone's number, then a letter. **3C** is the third item of milestone 3. A big item is split one
step down with a number: **3C1**, **3C2**. Write the code wherever you mention the item: commit messages, the changelog,
`NOW.md`, pull requests and GitHub issue titles (`[3C] Charts: two end labels overlap`).

- A code is never reused. `python tools/issues.py next 3` prints the next free one.
- An item moving to another milestone gets a new code there; write `was: 3C` in its front matter.
- A finished item's file is **deleted in the commit that finishes it**, and its code is added to `done:` in the milestone's
  README. The record is the test, the changelog line and the commit message (name the code there).

## Where things go

```
issues/
  INDEX.md                          generated: the whole plan
  3-polish-and-arabic/              milestone 3
    README.md                       its title, goal, "done when" and finished codes
    3C-chart-end-labels-overlap.md  item 3C
```

A file is named `<code>-<what>.md`, lower case after the code, hyphens. A step inside a big item is a heading in the item's
own file: `## 3C1 Move the lower label down`. A new milestone is a new numbered folder with a README; the owner picks the
order.

## Types

| Type | Use it for |
|---|---|
| `bug` | Something is wrong: a figure, a crash, lost data, a broken layout, Arabic or direction faults |
| `polish` | It works, but could be clearer, shorter or kinder |
| `feature` | Something new to build, often with a design (what used to be a proposal) |
| `tech` | Under the hood: speed, structure, tests, tooling, security; nothing a person sees change |
| `owner` | Needs the owner: a decision, an account, a key, a check on their PC or phone |

**Area** is the screen or module in one word: `overview`, `budget`, `investments`, `accounts`, `import`, `phone`, `arabic`,
`website`, `tools`...

## Status

`new` (found, not looked at) · `ready` (understood; anyone can build it) · `building` (someone has it: a claim in `NOW.md`
or a `/take` on GitHub) · `blocked` (say what it waits for in `blocked_by`). Finished is never a status: delete the file.

## Front matter (required, between two `---` lines, first in the file)

```
---
title: Short sentence saying what is wrong or wanted
type: bug
area: overview
status: new
created: 2026-10-19
by: Claude Opus 5.5                  # the AI or "owner"; never a person's name
github: 35                           # optional: its GitHub issue, if people may take it
blocked_by: 3B                       # only when status is blocked
---
```

Bugs found by a skill also keep `skills`, `app_version`, `commit` and `repo` (app, website or both).

## Body

```
## Report
What was seen or wanted, where (page, file, step), how to reproduce it, what should happen instead. Evidence: numbers,
a command and its output, a screenshot path. Severity for bugs: high (wrong money or lost data), medium, low.

## Investigation        (added later; who and with which skill)
What is true, what is not, the cause with file:line, what you ruled out.

## Fix
What will change, the branch, the test that proves it.
```

A `feature` may instead be a full design (as [4A](4-edit-journal-and-devices/4A-edit-journal.md) is). When part of it is
built, move what holds into [Architecture](../docs/ARCHITECTURE.md) and shrink the item to what is left.

## People and GitHub

A small, self-contained item also gets a GitHub *Good first issue* (its template), titled with the code and linking the file,
with `github: n` in the front matter. Never start an item whose GitHub issue has an assignee or the `taken` label: a person
has it. Fixing it closes the issue (`Closes #n`). `tools/stale_check.py` lists `new` bugs older than 30 days, except those
waiting for a person on GitHub.
