# Reports

Every finding lives here, in one place, in two stages. The repo is public: no names, emails, real financial data or private links.

1. **Report** (anyone, any tool): what was found, with evidence. Written once, not rewritten.
2. **Investigating and fixing** (the same or another AI): appended to the same file under `## Investigation` and `## Fix`; the front matter `status` moves on.

**A processed report is deleted.** When it is fixed (or settled as declined or not reproduced), delete the file **in the same commit as the fix** and run `python tools/report_index.py`.
The record is the test, the changelog line and the commit message (name the report there). Only unprocessed reports (`reported`, `investigating`, `open`) stay, so the folder is a to-do list, not an archive.

**To find something, read `report/INDEX.md` only** (one line per report, open ones first), then open the one report you need.
The index is generated: `python tools/report_index.py` rewrites it, `--check` verifies it (a test runs the check). Never edit it by hand.

## Where a report goes

`report/<category>/<yyyy-mm-dd>-<area>-<what>.md`, lower case, hyphens, no spaces. The name says what it worked on:
`technical-bug/2026-10-15-plan-double-bill-payment.md`, `visual-bug/2026-10-15-investments-held-1-days.md`.

| Category | Use it for |
|---|---|
| `technical-bug` | A wrong figure, crash, lost data, double action, bad validation, test failure |
| `visual-bug` | Layout, colour, wording, spacing, overflow, Arabic or direction faults that break the guideline or look wrong |
| `technical-improvement` | Speed, structure, tests, tooling, safety; behaviour a person does not see change |
| `visual-improvement` | A screen or flow that works but could be clearer, shorter or kinder |

**Area** is the screen or module in one word: `plan`, `budget`, `overview`, `investments`, `accounts`, `import`, `settings`, `phone`, `arabic`, `website`, `tools`...

## Front matter (required, between two `---` lines, first in the file)

```
---
title: Short sentence saying what is wrong or wanted
category: technical-bug
area: plan
status: reported
created: 2026-10-15
reporter: Claude Sonnet 5.5          # the AI or "owner"; never a person's name
skills: bug-hunt, number-audit       # skills used, or "none"
app_version: 1.1.0b1                 # pyproject version the finding was made on
commit: 821db7a                      # short commit of main (or the branch) it was made on
repo: app                            # app, website or both
---
```

`status` is one of: `reported` (found, not yet looked at), `investigating`, `open` (a real request, not built; say why). Update it and run `python tools/report_index.py` whenever you move a report on.
The end states `fixed`, `declined` (conflicts with the guideline or a decision) and `not-reproduced` are never stored: the check fails on them, because they mean "delete this file now".
If a decline or a non-reproduction teaches something lasting (a rule, a decision), put one line in `docs/` or the changelog, not in a kept report.

## Body

```
## Report
What was seen, where (page, file, step), how to reproduce it, what should happen instead. Evidence: numbers, a command and its output, a screenshot path.
Severity for bugs: high (wrong money or lost data), medium, low.

## Investigation        (stage 2, added later; who and with which skill)
What is true, what is not, the cause with file:line, what you ruled out.

## Fix                  (stage 2, until the file is deleted)
What will change, the branch, the test that proves it. Copy the essentials into the changelog line, then delete the report.
```

Keep it short: facts, not narration. Do not paste code, only name `file:line`.

## No pile-up

The folder is a short to-do list, kept short by three rules that `python tools/report_index.py --check` (and a test) enforce:

1. **At most 20 reports.** Over that, nothing new is filed until some are processed.
2. **At most 30 days each.** `python tools/stale_check.py` lists older ones (not those with an `issue:`, which wait for a person): fix it, decide it (`declined` means delete it), or ask the owner. A date never fails the tests, so it never blocks someone else's PR.
3. **Fix small things instead of filing them.** If the fix is one small change you can test now (a wording, a one-line guard), do it on a branch with its test and changelog line and write **no** report.
   File a report only for what you cannot fix in the same sitting: a decision is needed, it is bigger than one change, or you are only hunting and not fixing.

A hunt that finds many small things files at most one report per area, not one per item.

## Rules

- One finding per report. If a hunt finds ten things, write ten reports (or list the minor ones in one `technical-improvement` report called `...-small-things`).
- Check `INDEX.md` first: add to an existing report instead of making a duplicate.
- Skills write their results here: `bug-hunt`, `number-audit`, `guideline-audit`, `arabic-check`, `perf-check`, `stale-check`, `website-sync`, `release-check` and `feedback-review` each create or update reports, and put their name in `skills`.
- This is where findings live. Designs for something not yet built stay in `docs/proposals/`; what the product *is* stays in `docs/`; hand-off messages stay in `NOW.md`.
