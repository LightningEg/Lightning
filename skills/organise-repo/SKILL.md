---
name: organise-repo
description: Decide where a new document, fact or finished piece of work belongs (docs/ for people, ai/ for AI sessions, issues, reports, feedback, archive), keep the generated pages current and the documents small. Use when adding or moving a document, when the repo feels cluttered, or before merging a docs change.
---

# Organise the repo

Tool-neutral. One fact lives in one file; everything else links to it. Two readers: **people** read `docs/` (one screen or two each), **AI sessions** read `ai/` (depth, found through `ai/INDEX.md`).

## Where does it go?

| Question | Answer |
|---|---|
| Who reads it? | People: `docs/`. An AI that needs depth: `ai/`. |
| A fact (how it works, a term, a decision) or a record (something that happened)? | A fact has one home: product and decisions `ai/PROJECT_OVERVIEW.md`, how it is built `ai/ARCHITECTURE.md`, a term `ai/GLOSSARY.md`, competitors `ai/COMPETITION.md`. A record is a dated report in `reports/`, a sanitized observation in `feedback/`, or a plan item in `issues/`. |
| Is it work still to do? | An item in `issues/` (skill `add-plan-item`), never a new document. |
| Is it still true? | If not: `ai/archive/`, or delete it. History stays in git. |
| Which pillar? | One of `capture plan understand own protect everywhere feel build reach` (`issues/README.md`). |

## Steps

1. Grep for the fact first (`grep -rn "<phrase>" docs ai issues`). If it exists, link to it; do not copy it.
2. Put it in its home. Do not add a file under `docs/` or `ai/` unless `tests/test_docs_structure.py` lists it; change that list in the same commit and say why.
3. Moving a file: `git mv`, then fix every link and every mention of the old path (`grep -rn "<old path>" .` including Python strings that build paths from parts), then `python tools/docs_check.py`.
4. Never hand-edit a generated page. Regenerate: `python tools/status.py` (docs/STATUS.md, the work block on each pillar page, ai/INDEX.md), `python tools/issues.py` (issues/INDEX.md), `python tools/release_notes.py` (RELEASES.md).
5. Archiving: a report whose follow-ups are all closed, a design that is built (fold what holds into Architecture, delete the file), an old changelog: move to `ai/archive/` and keep commit-pinned references that issues already use.
6. Keep it small: `NOW.md` under 4,500 bytes; a page for people fits a screen or two; a long AI file is read by section (`python tools/status.py sections <file>`).
7. Check: `python tools/docs_check.py`; `python -m pytest tests/test_docs_structure.py tests/test_issues.py tests/test_changelog.py -q`; `python tools/claims.py --me <Claude|Codex|Luna>`.

**Where findings go.** Read `issues/README.md` once. Fix a small finding now and file no item. File anything bigger as one item (skill `add-plan-item`).
