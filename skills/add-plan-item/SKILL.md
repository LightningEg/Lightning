---
name: add-plan-item
description: File a bug, improvement, feature, technical task or owner decision as one coded item in issues/, with the right milestone, pillar, size and front matter, and regenerate the plan. Use when you find or plan something that is not finished in this session.
---

# Add a plan item

Tool-neutral. Everything still to do is an item in `issues/`; the plan is `issues/INDEX.md`. The repo is public: no names, emails, real financial data or private links.

## Steps

1. **Duplicate check.** Read `issues/INDEX.md`, then `grep -rln "<key words>" issues`. Add to an existing item when it is the same problem.
2. **Milestone.** Pick the folder whose goal it serves (`issues/<n>-<name>/README.md` states each goal). Get the next code: `python tools/issues.py next <n>` (for example `3AN`). A code is never reused.
3. **File.** `issues/<n>-<name>/<code>-<what-in-hyphens>.md`, front matter first:

```
---
title: One sentence saying what is wrong or wanted
type: bug            # bug | polish | feature | tech | owner
look: visual         # bugs, and polish when technical: visual or technical
severity: medium     # bugs only: high (wrong money or lost data), medium, low
pillar: capture      # capture plan understand own protect everywhere feel build reach
size: M              # S small fix, M a few files with tests, L money logic or a feature; none on an owner task
status: new          # new | ready | building | blocked (blocked needs blocked_by: <code>)
created: 2026-10-31  # from the date command
by: Claude           # the AI or "owner"; never a person's name
---
```

4. **Body.** `## Report` (what, where, how to reproduce, evidence: a command and its output or a sample-data screenshot), then `## Fix` (what will change and the test that proves it). Add `post: no` to the front matter if it is sensitive (security, restore, owner-run); say why in a last line.
5. **Large?** If it is size L, split it now (skill `split-large-item`).
6. **Regenerate and check.** `python tools/issues.py` then `python tools/status.py`; `python -m pytest tests/test_issues.py tests/test_docs_structure.py -q`.
7. **Commit** with the full code in the subject (`[BT-5J] ...`) and the `Release-note:` and `Detail:` trailers (skill `write-release-notes`; `Release-note: none` for a plan-only change).

A finished item is deleted in the commit that finishes it, and its code is added to `done:` in the milestone README.
