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
any bigger decision, measure on a real phone (3AO1).

## Fix
Measure on a device, then the cheapest change with the biggest effect first; `tools/perf_check.py` and Audit 13's
`evidence/flows.py` before and after each step; page text identical before and after (perf-check skill, step 5).

## 3AO1 Measure on a real phone · S
Add navigation timing to the Android probe (server time, parse and scripts, total) for Overview, Budget, Transactions,
More, Spending and opening Add; record a dated table in Audit 13's report. Done when the numbers above have a real-phone
column.

## 3AO2 Keep the frame, swap the page · L
The tab bar, app bar and scripts load once; a tab or row tap fetches only the page's `main` and swaps it in, with the
address, ‹ and the phone's back gesture kept right; tab pages are fetched when the finger lands, before it lifts. Sheets
already load this way. Done when a tab switch at x4 is under 300 ms.

## 3AO3 Lighter pages for the browser · M
Scripts `defer`red and only what the page uses; Arabic text translated on the server so `ui-ar.js` is not
parsed on every page; phone CSS without the PC's rules or unused theme parts; no deep selectors
that make every style recalculation expensive. Done when parse and scripts at x4 is under 250 ms on every tab.

## 3AO4 Fewer queries on the heaviest pages · M
Overview reads settings 37 times, Cash planning 24, Financial health 28 (`SELECT value FROM settings WHERE key = ?`):
read them once per request (`raw_setting`); then the category-by-code (Spending, 18) and alias (Counterparties, 36)
loops. Done when no phone page is over 150 ms warm on the sample.
