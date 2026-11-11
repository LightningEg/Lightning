---
title: A slow page makes every other request wait - the routes are async def with synchronous database work, so one 76 ms Overview holds back a 4 ms stylesheet for about 110 ms
type: tech
pillar: build
size: M
model: opus
status: new
created: 2026-11-10
by: Claude
app_version: 2.1.2
commit: fd84a3e
---

## Report
Found by IT-9F3. On the sample year (Mohab, dummy data), a real uvicorn server on loopback, `httpx` clients on threads, medians of five runs, a second pair of requests starting 10 ms after the first:

| First request (alone) | `/static/style.css` while it runs (alone 4 ms) | `/transactions` while it runs (alone 25 ms) |
| --- | --- | --- |
| `/` (76 ms) | 118 ms | 114 ms |
| `/budget` (24 ms) | 51 ms | 50 ms |

Each second request waits for the first to finish (about 110 ms behind the Overview, about 45 ms behind Budget): the routes are `async def` and read SQLite on the event loop, so nothing else is served meanwhile. One person on the PC will rarely notice (the page, then its CSS, are mostly cached), but a phone talking to the PC and the PC's own page loads share the one loop.

## Fix
Turn the slowest read-only routes (`/`, `/investments`, `/budget`, `/plan`, `/activity`) into plain `def` routes so Starlette runs them in its thread pool, one at a time, and measure again with the same script (the second requests must wait under 50 ms).

Risk to settle first: the database connection's thread rules (`check_same_thread` in `lightning/database/`, the strict owning-thread checks of encrypted profiles) and the request cache in `lightning/core/memo.py` (`request_cache`, a `ContextVar`: a threadpool run copies the context, so check that a write in one request still empties only its own cache). A `def` route also loses the `await request.form()` calls: only convert routes that read nothing from the body.

Test: `tests/test_every_page_answers.py` plus `tests/test_reporting_performance.py` unchanged; add a test that two overlapping requests on a threaded server both answer 200 and the shorter one does not wait for the longer.

Release-note: none.
