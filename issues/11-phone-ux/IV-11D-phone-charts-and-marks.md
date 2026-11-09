---
title: The phone has no charts - build the guideline's phone charts and meters, one per tab, so each tab is seen, not read
type: polish
pillar: everywhere
size: L
model: opus
status: ready
created: 2026-11-09
by: Claude Opus 5.5
---

## Report

Report [r29](r29-google-play-readiness/report.md) T1, T4, T10, and the owner (2026-11-09): "The phone does not have a single
visual, which defeats the purpose of convenience and quick actions." Five tabs, no chart; Budget has bars. Guideline C06.1 and C07
already define every phone form; none is built on the phone. Figures stay in Python services; the template draws positions the
service gives (as `lightning/ui/charts.py` does for the PC).

## How to work on this item

Each step is one pull request. Read `python tools/guideline.py C07` and `C06` first, never the whole guideline. Every chart: full
width, 140-180 tall, three time labels at most, no y-axis labels, tap or drag to read (C07.1), mirrored rows but not axes in Arabic,
one 400 ms entrance under `prefers-reduced-motion: no-preference`. Tests: the service's numbers equal the figure beside them;
`python tools/phone_check.py` and `--arabic` print nothing; Mohab (`tests/test_mohab_phone.py`).

## 11D2 Home and Budget: This month as one segmented bar · S · sonnet
**Built** on Budget and Home (`month_bar`, `tests/test_phone_budget_flexible.py`, `tests/test_phone_home.py`). Ahead-of-pace bars use soft rose, not amber: A03 has no amber.
Spent, left in plan, over (rose) on one bar under the This month row and under Budget's hero; Budget's category bars take state colours (at plan: amber, over: rose, A03).
Done when: the bar's parts add to the plan and a test checks it.


## 11D5 Budget: where the month went · S · sonnet
**Built** (`spend_donut`, `charts.ranked_donut`): soft-rose steps by rank, the rows name each slice; fixed costs paid is one slice.
One donut, 168 wide, total in the hole, four then Other, rows under it (C07.2), above Your categories.
