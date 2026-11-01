---
title: The phone feels slow - every tap reloads the whole page, and on a phone's CPU the browser side costs most of the time, not Python
type: tech
pillar: everywhere
size: L
status: ready
post: no
created: 2026-11-01
by: Claude
skills: perf-check
app_version: 1.5.4
commit: 4ba2732
repo: app
---

## Report
The owner (2026-11-01): "the app is also very slow; do we need to write it in a different language than Python?"
Measured with [Audit 13](../../reports/2026-11-01-phone-convenience-audit/report.md)'s setup (sample household, phone
frame, Chromium at 360 × 800):

**Python's part is small.** `python tools/perf_check.py --phone`: warm server time 54-228 ms per page (Overview 167 ms,
231 queries; Spending 228 ms; Transactions 66 ms) on the cloud machine.

**The browser's part is large, and grows on a phone's CPU.** One navigation, split by the browser's own timing; "x4" is
Chromium's CPU throttle, a fair stand-in for a mid-range Android phone (the server is not throttled):

| Page | x1: server · parse and scripts · total | x4: parse and scripts · total |
| --- | --- | --- |
| Overview | 102 · 96 · 237 ms | 683 · 905 ms |
| Budget | 33 · 72 · 201 ms | 560 · 725 ms |
| Transactions | 27 · 70 · 193 ms | 639 · 927 ms |
| More | 73 · 35 · 180 ms | 633 · 844 ms |
| Spending | 40 · 109 · 231 ms | 864 · 1,083 ms |

Why: every tap is a full page load (`no-store`), so the WebView parses the HTML again, recalculates every style
(style recalculation is the biggest single cost: about 60-135 ms a load at x4) and runs seven scripts again
(`app.js` alone is 165 KB), even when only the list under the tab bar changes. In Arabic each page also parses
`ui-ar.js`, 264 KB of translations, so an Arabic user pays about twice the script cost. On the phone Python also runs slower
(Chaquopy on ARM), so the 100-200 ms server time grows too, but it stays the smaller share.

**Answer to the owner: no rewrite.** A faster language would shrink the smallest share of the wait. The same Python
server would feel fast if the phone stopped reloading the frame on each tap and the pages it draws were lighter. Before
any bigger decision, measure again.

**Built 2026-11-01** (owner: "fix it then"): the phone keeps its frame and swaps the page (`phone-nav.js`, test
`tests/test_phone_nav_browser.py`); at 4x CPU a tab switch went from about 1.0 s to 0.25-0.3 s (Budget 1,004 to 287 ms,
Transactions 970 to 224, More 942 to 308, Overview 1,088 to 309); a tab's page is asked for as the finger lands (the
old `<link rel=prefetch>` could not be used by a no-store page and only doubled the work). Settings and categories are
read once per request: Overview 231 to 196 queries, Budget 57 to 33, Cash planning 198 to 176, Financial health 168
to 142. Then every phone page swaps (3AO2): set-up moved behind `lightning:page`, and a page's own scripts run again
when they carry the response's nonce; on all 30 phone pages a swap shows the same content as a full load. Payer names,
aliases and by-id lookups read once (Overview 176 queries, Counterparties 44 to 9, Spending about 155 ms). The owner
dropped the real-phone measurement (3AO1, 2026-11-01). Each step below says only what is left.

## Fix
Measure on a device, then the cheapest change with the biggest effect first; `tools/perf_check.py` and Audit 13's
`evidence/flows.py` before and after each step; page text identical before and after (perf-check skill, step 5).

## 3AO3 Lighter pages for the browser · M
Measured 2026-11-01 at 4x: leaving out the PC's rules from the phone bundle (526 KB, `style.css` included) or `app.js`
alone barely changed a full load; the cost is building a whole document, which 3AO2 now avoids. Left for the first
load and the pages that still load whole: Arabic text translated on the server so `ui-ar.js` (264 KB) is not parsed on
every page, and the forced layouts while the page loads (about 55 ms at 4x).

## 3AO4 Fewer queries on the heaviest pages · M
Done but for Spending, about 155 ms against the perf-check skill's 150: most of what is left builds its two money-flow
diagrams, which IV-3AL6 moves off the phone's first page. Bill matching's per-item reads (12 on Overview and Cash
planning) stay: every page is under the skill's 400 queries, and that is money logic.
