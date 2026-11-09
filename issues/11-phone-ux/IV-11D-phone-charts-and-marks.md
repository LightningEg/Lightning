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

## 11D1 Home: the payday meter under Safe to spend · M · opus
A meter (C06.1) under the hero: days gone to payday against money gone from what was safe; rose when spending is ahead of the days.
Done when: the meter's two fractions come from the Safe to spend service and a test checks them on Mohab's 2026-10-04.

## 11D2 Home and Budget: This month as one segmented bar · S · sonnet
Spent, left in plan, over (rose) on one bar under the This month row and under Budget's hero; Budget's category bars take state colours (at plan: amber, over: rose, A03).
Done when: the bar's parts add to the plan and a test checks it.

## 11D4 Money: the net-worth trend and what you own as one bar · M · opus
C07.3.1's 160-tall area trend (end of each month, end value on the line) under Net worth, and what you own split by asset class (A04 colours, four then Other) as one segmented bar above Accounts.
Done when: the trend's last point equals the hero and the bar's parts add to What you own.

## 11D5 Budget: where the month went · S · sonnet
One donut, 168 wide, total in the hole, four then Other, rows under it (C07.2), above Your categories.

## 11D6 Category marks in rows · M · opus
Owner, 2026-11-09: a category mark in the row's disc, keeping the in/out colour (`ai/PROJECT_OVERVIEW.md` › Google Play launch).
First change guideline C08.2 in both repos (one PR each, `cmp` passes); then one line icon per built-in category (the app's icon set, 24 px, stroke 1.75), drawn in the disc's in/out colour; a custom category keeps the arrow. Transfers keep ⇄.
Done when: `tests/test_docs_structure.py` passes with both guideline copies; a test renders Home and every built-in category's row shows its mark.
