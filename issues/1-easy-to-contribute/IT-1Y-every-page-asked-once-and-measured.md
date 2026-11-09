---
title: Every page is asked once and measured - one test fetches all 130 pages on the PC and the phone, and perf_check times the pages people use
type: tech
pillar: build
size: M
model: sonnet
status: ready
created: 2026-11-09
by: Claude
app_version: 2.1.2
commit: 24e3cf8
---

## Report
Found by [r33](r33-code-review-and-loose-ends/report.md) F6 and F7.

- `tools/perf_check.py` times the 18 addresses in its `PAGES` tuple. `/activity` (1,039 queries), an import review (1,136), `/needs-you`, `/review`, `/search`, `/payday`, `/zakat` and every phone slot are not in it.
- Its `--phone` sets `request.state.phone` but never calls `mount_phone`, so it times the old shared pages; the phone's own Home, Budget, Activity and Money (`lightning/ui/phone/router.py`) are never measured.
- No test asks every page. `GET /transactions/sorted` on the PC raises `TemplateNotFound` (500): its template exists only under `templates/phone/`.

The crawl that found these is `issues/1-easy-to-contribute/r33-code-review-and-loose-ends/evidence/crawl.py`; copy from it.

## 1Y1 The PC never gets a phone-only sheet · S
Files: `lightning/ui/routes/transactions.py` (`sorted_sheet`, about line 158), `tests/test_phone_capture.py` (read only, for the phone behaviour to keep).
Do: at the top of `sorted_sheet`, when `getattr(request.state, "phone", False)` is false, `return redirect(_return_to(request.query_params.get("return_to")))`, the same guard `transaction_sheet` has 60 lines above.
Test: add to `tests/test_ui.py` (or the nearest PC route test): `client.get("/transactions/sorted", follow_redirects=False).status_code == 303`. Run `python -m pytest tests/test_phone_capture.py tests/test_ui.py -q`.

## 1Y2 One test asks every page · M
Files: new `tests/test_every_page_answers.py`; read `tests/conftest.py` for the sample-profile fixture and `lightning/ui/phone/router.py:mount_phone`.
Do: build the app on Mohab's sample year twice (PC; phone with `mount_phone(app)` and the phone flag set as `evidence/crawl.py` does). Collect every GET route (walk `app.routes`; an included router keeps its routes on `route.original_router.routes`, see `crawl.py`). Replace `{...:int}` parameters with `1` and other parameters with `x`. Ask each address with `raise_server_exceptions=False` and assert no status is 500 or above. Print the failing addresses in the assertion message. Skip `/static`.
Done when: the test passes after 1Y1 and fails if 1Y1 is reverted.

## 1Y3 perf_check measures the real pages · S
Files: `tools/perf_check.py`, `skills/perf-check/SKILL.md` (the "Known hotspots" paragraph), `tests/test_reporting_performance.py` (read only).
Do: (a) with `--phone`, call `mount_phone(app)` before wrapping, and use a phone list: `/`, `/budget`, `/add`, `/activity`, `/money`, `/money/accounts`, `/investments`, `/plan`. (b) add to the PC `PAGES`: `/activity`, `/needs-you`, `/review`, `/search?q=a`, `/payday`, `/zakat`, `/reimbursements`, `/spending/compare`, `/reports`, and the first waiting import review if the sample has one (`SELECT account_id, id FROM bank_import_batches WHERE status='PENDING' LIMIT 1`; check the real status name in `lightning/bank_imports.py` first). (c) replace the skill's hotspot paragraph with the table in `evidence/results.md` §2 and its date.
Done when: `python tools/perf_check.py` lists the new pages and exits 1 today because of `/activity` and the import review (IT-9M and IT-9N fix them); `python tools/perf_check.py --phone` prints the phone's own pages with HTTP 200.

Release-note: none for all three.
