---
title: Two sessions take the same code - report and item codes are handed out from the local checkout, and a guideline change can merge in one repository only
type: tech
pillar: build
size: M
model: sonnet
status: ready
created: 2026-11-09
by: Claude
app_version: 2.1.2
commit: 24e3cf8
post: no
---
## Report
Found by [r32](r32-code-review-and-loose-ends/report.md) F9 and F10. `python tools/issues.py next <n>` and `python tools/docs_check.py next-report` answer "highest code in this checkout, plus one". Two sessions that start from the same `main` get the same answer. On 2026-11-09: #460 and #462 both used r30 and 12H-12N (#462 merged first), #461 and #463 both used r31, #464 used r32, and this report was the third r31 until #463 merged and it was renamed r32 by hand. The second to merge must rename files, links, the index and `REPORTS.md` by hand.
The same day the guideline went to 3.40 in the app (#450, #456 merged) while its website mirrors (#174, #176) stayed open, so `tests/test_docs_structure.py::test_the_app_and_website_guidelines_are_all_mirrored` fails on `main` whenever both repositories are checked out.
## Fix
Three steps, one pull request each. Read only the functions named.
## 1X1 Reserve a code in NOW.md before using it · S
Files: `tools/issues.py` (`next_code`, the `next` branch of `main`), `tools/docs_check.py` (`next_report_code`), `NOW.md`, `AGENTS.md` §3, `skills/add-plan-item/SKILL.md`, `tests/test_issues.py`.
Do: add a line `Reserved codes: ` under `## Claimed` in `NOW.md` (comma-separated, e.g. `r33 Claude, 12U-12W Claude`). Make both `next` commands also read that line and skip every code or range on it. Document the rule in one sentence in AGENTS §3 step 2 and in the skill: "a report or more than one new item: write your codes on NOW.md's Reserved line and push that commit first; remove them in the pull request that adds the files."
Test: a unit test feeds `next_code` a reserved range and expects the code after it; same for reports.
## 1X2 CI refuses a code that main already has · S
Files: `.github/workflows/pr-checks.yml` (the docs job), `tools/issues.py --check`.
Do: `--check` already fails on a duplicate code inside one checkout. In the pull-request job, run it on the merge result (the default `refs/pull/N/merge` checkout already is) and make sure a duplicate report folder number (`r30-a`, `r30-b`) is an error in `tools/docs_check.py check`. Add the test for the duplicate report number.
## 1X3 A guideline change cannot merge alone · S
Files: `skills/ship-pr/SKILL.md`, `skills/website-sync/SKILL.md`, `.github/pull_request_template.md`.
Do: add one checkbox to the app's pull request template: "Guideline changed? Website mirror PR: #___ (merge both in the same sitting)". In `ship-pr`, add the step: when `git diff --name-only origin/main... -- guideline/` is not empty, do not merge until the website pull request with the identical files (`cmp`) has green checks, then merge the two one after the other.
Owner or the session that owns them, now: merge website #174 and #176, or close them and open one mirror of the app's current `guideline/`.
## Done when
Two sessions started from the same commit cannot both be given the same report code; the template asks for the mirror. Release-note: none.
**Not posted to contributors:** it changes the AI hand-off rules.
---
