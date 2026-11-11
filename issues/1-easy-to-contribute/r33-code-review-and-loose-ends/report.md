# Code review: what is slow, loose, complicated or cut off from the rest

Date: 2026-11-09 · Author/reviewer: Claude
Repository: both (app in depth, website for the mirror only) · Reviewed commit: 24e3cf821043faa0e4ce7fc8349fc067e1c2d95e
Code: r33 · App version: 2.1.2
Pillar: build · Related pillars: understand, capture, protect

## Assessment

The engine is in good shape. Nothing in this review found wrong money. Query counts do not grow with the size of the
ledger, the import contracts hold, every one of the 130 pages answers on the PC and on the phone except one, and the
navigation registry reaches every feature.

What is loose is around the engine, not in it:

1. **A new contributor cannot start.** The documented install misses four packages, so the first command after it fails.
2. **Three pages are far over the query budget and nobody measures them**, and one read makes the Overview slow once a
   profile passes about 4,000 transactions. All four have a small, proven fix.
3. **The process is producing faster than it finishes.** Eight audits in four days, four of them open at once with the
   same codes; eight size L items "building"; a guideline change merged in the app and still waiting in the website.
4. **Two useful pieces are cut off:** Data checks never reach Needs you, and the three "explain this figure" pages
   have no link anywhere.

Ten items come out of this report. Each is written so the smallest model can do it alone: the files, the change, the
test command and what done looks like. Suggested order is at the end.

## Scope and method

The owner asked for a complete code review: what can be better or more efficient, what is missing, what loose ends
remain, what is next, what can be tighter, what is complicated and which feature lives in a desert.

Measured, not read. On Mohab's sample year (374 transactions) and on the same year plus 4,000 invented expenses over
four years (4,374 transactions):

- every GET route asked on the PC and on the phone (phone routes mounted as `profile_app` does), with status, warm
  milliseconds, query count and the most repeated query ([crawl.py](evidence/crawl.py));
- the link graph of those pages: which page links to which, so a route nothing links to shows up;
- the slowest queries and functions at 4,374 transactions ([scale.py](evidence/scale.py));
- static checks over `lightning/` (333 files, 78,558 lines): unused code (vulture, then each name searched in
  `lightning/`, `tools/`, `android/` and `tests/`), complexity (radon), function length (AST), and the class names of
  `style.css` searched in every template, script and Python file;
- the install path in the README, run in a clean interpreter;
- the plan, the hand-off, the open pull requests of both repositories and the guideline copies.

Read first, so nothing here repeats them: r2, r3, r5 and r22 (the earlier code audits), IT-9K, IT-9A, IT-9F.

Not done: no native Windows or Android run, no browser layout check, no security sweep (skill `security-sweep`
owns that), no review of the journal and pairing code under an active claim, and the website's own code beyond its
guideline copies and open pull requests. Timings are from one cloud machine; treat them as ratios, not as what an
ordinary PC shows.

## Findings

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F1 | high (build) | `pip install -r requirements-dev.txt` then `python -m lightning --demo` stops with `ModuleNotFoundError: No module named 'rapidfuzz'`. `requirements.txt` lists 4 of the 8 runtime packages in `pyproject.toml` (`pypdf`, `openpyxl`, `defusedxml`, `rapidfuzz` are missing); Codespaces, `run.sh`, `run.bat` and `tools/install_source.py` install from the same file. `pip install -e .` also fails (several top-level folders, no package list). CI installs from lock files, so it never sees this. | [results.md](evidence/results.md) §1 | BT-1V (done; `tests/test_source_install.py`) |
| F2 | medium | The Overview takes 426 ms at 4,374 transactions (131 ms on the sample), over the 400 ms line IT-9A waits for. The cause is one read: `build_investment_report` loads every posted ledger line of the profile, four times per Overview, to use the few that touch investments. A narrower query returns the identical report on three datasets and takes 4 ms instead of 61 ms per period. | [results.md](evidence/results.md) §3, [investment_query.py](evidence/investment_query.py) | [IT-9L](../../9-later/IT-9L-investment-report-reads-the-whole-ledger.md) |
| F3 | medium | `/activity` on the PC asks 1,039 queries for 100 rows (budget: 400). `ActivityReview.recent` builds each row with about ten single-row reads. | [results.md](evidence/results.md) §2 | [IT-9M](../../9-later/IT-9M-activity-asks-ten-queries-a-row.md) |
| F4 | medium | The import review asks 4 queries per statement row: 1,136 queries and 322 ms for the sample's 90-row file. A 1,000-row statement would ask about 12,000. | [results.md](evidence/results.md) §2 | [IT-9N](../../9-later/IT-9N-import-review-asks-four-queries-a-row.md) |
| F5 | low | `ReportQueries.asset_purity` is the most repeated query on five pages (39 times on the Overview, 60 on the phone's Investments) and has no per-request memo. The Overview sits at 375 of its 400 queries. | [results.md](evidence/results.md) §2 | [IT-9L](../../9-later/IT-9L-investment-report-reads-the-whole-ledger.md) step 9L2 |
| F6 | medium (tooling) | `tools/perf_check.py` measures 18 fixed pages; the three pages over budget (F3, F4) are not among them. Its `--phone` only sets a flag and never mounts the phone's own routes, so it times the old shared pages, not Home, Budget, Activity or Money. No test asks every page once. | `tools/perf_check.py:25`, `lightning/ui/phone/router.py:193` | [IT-1Y](../IT-1Y-every-page-asked-once-and-measured.md) |
| F7 | low | `GET /transactions/sorted` answers 500 on the PC (`TemplateNotFound`): the template exists only under `templates/phone/` and the route lacks the phone guard its neighbour `transaction_sheet` has. Not linked on the PC; reached by a typed address or an old link. | [results.md](evidence/results.md) §2 | [IT-1Y](../IT-1Y-every-page-asked-once-and-measured.md) step 1Y1 |
| F8 | medium (repo) | Four wheel files sit in the repository root, 49 MB together (`playwright-1.64.1` alone is 48 MB), added by accident in #375. Nothing reads them. Every clone and every CI checkout downloads them. | `git log -- playwright-1.64.1-py3-none-manylinux1_x86_64.whl` | IT-1W (done; `tests/test_repo_hygiene.py`) |
| F9 | medium (process) | Parallel sessions take the same codes. `tools/issues.py next` and `tools/docs_check.py next-report` look only at the local checkout, so on 2026-11-09 pull requests #460 and #462 both took r30 and 12H-12N (one is merged), #461 and #463 both took r31, and #464 took r32. Whoever merges second must renumber by hand. `tests/test_docs_structure.py` requires report codes without a gap, so this report first took r31 too, lost it when #463 merged minutes earlier, was renamed r32, lost that to #464 the same way, and is r33 after two hand renames; its item codes are in folders, or past ranges, the open pull requests do not use. | Open pull requests #460, #461, #463, #464 | IT-1X (done; `tests/test_issues.py`, `tests/test_docs_structure.py`) |
| F10 | medium (process) | The guideline is at 3.40 in the app and 3.39 in the website: app #450 and #456 are merged, their mirrors (website #174, #176) are still open. With both repositories checked out, `tests/test_docs_structure.py::test_the_app_and_website_guidelines_are_all_mirrored` fails on `main`. AGENTS.md says never leave one copy behind. | `cmp guideline/phone.html ../Lightning_website/guideline/phone.html` | IT-1X (done; `tests/test_issues.py`, `tests/test_docs_structure.py`) step 1X3 |
| F11 | low | Unused code that only tests keep alive, or nothing does: ten functions and four unused names (list in the item). | [results.md](evidence/results.md) §4 | IT-1Z (done; kept list in Overview §2) |
| F12 | medium (desert) | Data checks (`/checks`, eight reconciliations of the ledger against the screens on the sample) are reachable only from Settings. A check that reads ISSUE raises nothing on the Overview, in Needs you, in the weekly review or in a reminder. The one feature that can say "a figure is wrong" is the one nobody is led to. | `grep -n "integrity\|/checks" lightning/workflows/review.py lightning/workflows/reminders.py` prints nothing | [NF-2AJ](../../2-safe-for-real-money/NF-2AJ-a-failed-data-check-reaches-needs-you.md) |
| F13 | low (desert) | `GET /explain/owned`, `/explain/free-cash` and `/explain/flow` are finished pages (parts of the figure, its meaning, freshness notes, a way back) that no template, script or screen links to, on the PC or the phone. Tests are their only visitor. | [results.md](evidence/results.md) §5 | Built (IV-12T): `tests/test_ui.py::test_overview_links_each_figure_to_its_explain_page` |
| F14 | low | About a quarter of `style.css` cannot be reached: 378 of 1,486 class names appear in no template, script or Python string, and 941 of 3,823 rules use only such names. The RTL sheet doubles it. | [results.md](evidence/results.md) §4 | IT-9F (open; this is its step 1 measured a second way) |

### What is complicated

Size alone is not a fault. These are the places where a small model, or a new person, will get lost:

| Where | Measure | Why it is hard | Follow-up |
| --- | --- | --- | --- |
| `ui/routes/budget.py:_page` | 330 lines, complexity 168 | One function sums months, groups, estimates and KPI rows, then renders two surfaces. It does money arithmetic in a route, against AGENTS §4. | IT-12N in pull request #461 (a screen cannot work out money); no second item here |
| `ui/routes/register.py:page` | 164 lines, complexity 132 | Filters, paging, saved views, tags and two surfaces in one function. | same |
| `runtime/app.py:profile_app` | 589 lines | Nested routes for restore, devices and lock. | IT-9K (steps 9K1 onward, already written for a small model) |
| `bank_import_posting._post_import_row`, `bank_import_proposals._preview` | complexity 101 and 77 | Already split by file (IT-9K); the two functions themselves are still one long decision each. | IT-9N touches `_preview`; leave posting alone until NF-7AB rebuilds the review |
| `runtime/restore.py` | three functions of complexity 35 to 62 | Crash-safe restore is hard by nature. | IT-2A (claimed work) |
| `ui/i18n.py` + `ui/i18n_system.py` | 6,503 lines | Two hand-kept dictionaries keyed by the English sentence. It works and is tested; it is only long. | none |
| `ui/static/app.js` | 3,123 lines, one file, no section marks | Every PC behaviour in one script. | none now; split only when a change needs it |

In all: 35 functions over 100 lines and 196 with complexity D or worse, of 4,093. Twelve of the twenty most
complex are page routes. That is the one pattern worth fixing as a pattern, and IT-12N (pull request #461) already
proposes the ratchet for it.

### What can be tighter

- **Finish before starting.** 51 open items before this report: 22 are size L and 8 are "building". The journal claim in `NOW.md` dates from
  2026-10-16. Reports r26 to r33 were written in four days and each started four to seven items.
- **One hand-off list.** `NOW.md` has a dated *Next* list and, below it, an older numbered list of eleven lines that
  nobody has trimmed (items 1 to 6 are "paused", "held" or "built"). It is at 4,498 of its 4,500 bytes.
- **One install source.** `pyproject.toml`, `requirements.txt`, `requirements-dev.txt` and eight lock files name the
  same packages in four ways (F1 is what that costs).
- **Measure every page, not eighteen** (F6).

### Features and how well they connect

Measured as: how many other sections link to it, and whether its figures feed the Overview, the plan or Needs you.

| Feature | Linked from | Feeds the rest? | Verdict |
| --- | --- | --- | --- |
| Data checks | Settings only | No | Desert (F12) |
| Explain pages | nothing | Uses position and freshness | Desert (F13) |
| Zakat | Transactions section, Plan (one dated line), reminders | Reads the position; by decision it is "not in the plan" | Connected enough; an owner choice whether its amount should be reservable (not filed) |
| Financial health (Limits) | Safety section, Needs you, Reserves | Alerts reach Needs you | Connected |
| Gam'eya, Reimbursements, Held for others | Accounts, Needs you, the transaction page | Yes (position, plan, inbox) | Connected |
| Saved views, Tags | Transactions and Reports only | Read-only reports | Fine as they are |
| AI prompts | Import, Spending, Budget, Settings | Copy-only by design | Fine |

## What is next for Lightning

In the order the plan and the code point to, not a new plan:

1. **Ship the phone on Google Play** (NF-11B): the code is done; what is left is the owner's list in `NOW.md` and
   **BT-2AI (phone data must survive every update and reinstall)**, the only open high-severity bug. It should be
   closed before a store listing invites updates.
2. **Close the long claims:** edit journal and devices (NF-4A, NF-4B, claimed since 2026-10-16) and restore safety
   (IT-2A, IT-2C). They hold IT-9K's last steps and the native acceptance runs.
3. **Make the first hour work for a stranger:** BT-1V and IT-1W here, then IT-1N (post the contributor issues).
4. **The r28 polish queue** in the owner's order (3BC, 3BE, 3BD, 3BF), which is ready and sized for Sonnet.
5. **Then speed:** IT-9L, IT-9M, IT-9N. With IT-9L done, IT-9A (stored month-end figures) can stay blocked: the
   measurement that would unblock it is caused by one query, not by missing storage.

## Validation and limits

- Crawl: 162 PC pages and 182 phone pages fetched; one 500 (F7). `/categories/new` (404 without a parent) and
  `/exports/import/template` (400 without a kind) are correct refusals.
- `python issues/1-easy-to-contribute/r33-code-review-and-loose-ends/evidence/investment_query.py`: "identical: True"
  on Mohab's year, the demo household and the 4,374-transaction profile, over five periods each.
- Full suite on `main` with the website checked out beside it: see [results.md](evidence/results.md) §6.
- The 4,000 invented rows are plain expenses on one bank account. A real long profile also has more holdings, loans
  and reserves; pages that loop over those were not stressed.
- The unused-CSS count is a source search. It cannot see a class name built from two strings unless the prefix is
  visible; such prefixes were excluded, so the count errs low.

## Suggested order for the items

| Order | Item | Size | Model |
| --- | --- | --- | --- |
| 1 | BT-1V source install | S | Sonnet |
| 2 | IT-1W stray wheels | S | Sonnet |
| 3 | IT-1Y every page asked once (fixes F7 first) | M | Sonnet |
| 4 | IT-9L investment query and purity memo | M | Sonnet |
| 5 | IT-9M Activity | M | Sonnet |
| 6 | IT-9N import review | M | Sonnet |
| 7 | NF-2AJ data checks reach Needs you | M | Opus |
| 8 | IT-1X codes across sessions | M | Sonnet |
| 9 | ~~IV-12T explain pages~~ done | S | Sonnet |
| 10 | IT-1Z unused code | S | Sonnet |

## Dated follow-ups

None yet.
