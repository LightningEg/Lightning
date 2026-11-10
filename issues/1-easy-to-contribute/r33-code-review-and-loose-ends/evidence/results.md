# r33 evidence: what was run and what it printed

Commit 24e3cf8, Python 3.13, one cloud machine, 2026-11-09. Dummy data only: Mohab's sample year, the demo household,
and the sample plus 4,000 invented expenses. Timings are warm (second request).

## 1. The documented install

```
$ pip install -r requirements-dev.txt
$ python tools/perf_check.py        # any import of lightning.bootstrap does the same
  File "lightning/core/matching.py", line 9, in <module>
    from rapidfuzz.fuzz import ratio
ModuleNotFoundError: No module named 'rapidfuzz'
$ pip install -e .
error: Multiple top-level packages discovered in a flat-layout: ['ai', 'skills', 'assets', 'issues', ...]
```

`requirements.txt`: fastapi, uvicorn, jinja2, python-multipart. `pyproject.toml` adds pypdf, openpyxl, defusedxml, rapidfuzz.

## 2. Every page on the sample year (`crawl.py`)

162 PC pages and 182 phone pages. One server error: `GET /transactions/sorted` on the PC,
`jinja2.exceptions.TemplateNotFound: 'transactions/sorted.html'`.

| Page (PC) | Warm ms | Queries | Most repeated query |
| --- | --- | --- | --- |
| `/accounts/1/import/1` (90-row review) | 322 | 1,136 | 360x `SELECT 1 FROM bank_import_rows r JOIN bank_import_batches b ...` |
| `/activity` | 130 | 1,039 | 100x `SELECT * FROM transactions WHERE id = ?` |
| `/accounts/2/import/2` | 302 | 669 | 204x the same import query |
| `/` | 115 | 375 | 39x `SELECT purity_e6 FROM financial_assets WHERE id=?` |
| `/plan/reserves` | 98 | 286 | 80x the planning payments read (`planning/repository.py:158`) |
| `/plan` | 75 | 228 | 28x the same |
| `/needs-you`, `/review` | 100 | 198 | 28x the same |
| `/investments` | 107 | 184 | 42x the purity read |

| Page (phone) | Warm ms | Queries | Most repeated query |
| --- | --- | --- | --- |
| `/plan/reserves` | 110 | 286 | 80x the planning payments read |
| `/investments` | 198 | 250 | 60x the purity read |
| `/money` | 108 | 241 | 30x the purity read |
| `/` (Home) | 81 | 213 | 28x the planning payments read |
| `/activity` | 111 | 201 | 28x the same |
| `/budget` | 47 | 32 | |

The budget in skill `perf-check` is 150 ms and 400 queries. `/plan/reserves` (80 repeats of one read) is the next
candidate after the three over budget; it is under the limit and was not filed.

## 3. The same pages at 4,374 transactions (`scale.py 4000`)

| Page | Sample | 4,374 rows | Queries (unchanged) | Where the time goes |
| --- | --- | --- | --- | --- |
| `/` | 131 ms | 426 ms | 385 | 82 ms: the investment report's full-ledger read, 4 times; `reimbursements.suggested_pairs` 173 ms of Python |
| `/birdview/expenses` | 54 | 407 | 108 | 186 ms: the same read, 4 times |
| `/investments` | 120 | 237 | 184 | 44 ms: the same read, twice |
| `/needs-you` | 114 | 234 | 198 | reimbursement pairing |
| `/transactions` | 41 | 227 | 59 | one grouped balance read 33 ms, the rest rendering |
| `/counterparties` | 56 | 190 | 42 | SQL 21 ms; the rest is Python and the template (144 names) |
| `/budget` | 46 | 55 | 73 | |
| `/activity` | 77 | 95 | 1,039 | |

Query counts do not grow with the ledger. Time does, through reads that load whole tables.

`investment_query.py`:

```
load_mohab_2026 extra 0    identical: True  before 4 ms  after 3 ms per period; rows 413
build_demo      extra 0    identical: True  before 1 ms  after 1 ms per period; rows 79
load_mohab_2026 extra 4000 identical: True  before 61 ms after 4 ms per period; rows 4414
```

## 4. Static measures

- 333 Python files, 78,558 lines, 4,093 functions; 35 functions over 100 lines; 196 at radon complexity D or worse.
- Longest: `runtime/app.py:profile_app` 589 lines, `ui/journal.py:create_journal_app` 361, `ui/routes/budget.py:_page` 330.
- Most complex: `budget._page` 168, `register.page` 132, `bank_import_posting._post_import_row` 101,
  `bank_import_proposals._preview` 77, `investments.portfolio` 72, `settings.settings_page` 62, `restore.resume_interrupted_restore` 62.
- Unused names: see IT-1Z for the list and how each was confirmed.
- `style.css`: 1,486 class names; 378 appear in no template, script or Python file under `lightning/ui/` after
  leaving out every name that starts with a prefix some template builds (`tone-`, `is-`, `surface-`, ...); 941 of 3,823
  rules use only such names. Examples: `.birdview-position-grid`, `.allocation-bar-row`, `.budget-bridge`, `.avatar`.

## 5. Links

Routes with no inbound link from any fetched page and no mention in a template or script: `/explain/{kind}` (three
pages). Every other GET route is linked, fetched by a script, or is a deliberate endpoint (`/__health`,
`/reminders/due.json`, `/amount-sum`). `/checks` is linked from Settings pages only.

## 6. Test suite on main

`python -m pytest -n auto --dist loadfile -q` with the website repository checked out beside the app: 3696 passed, 62 skipped,
7 failed. Six of the seven were the plan and docs tests reading files this review was writing at that moment; they pass on
the final tree (`python -m pytest tests/test_docs_structure.py tests/test_issues.py -q`). The seventh is finding F10:
`test_the_app_and_website_guidelines_are_all_mirrored` fails on `main` until website #174 and #176 merge. CI does not
check out the website, so it does not see it.
