---
title: An Upcoming tab shows the month's payments on a calendar, with payday and the day cash runs short
type: feature
pillar: plan
size: L
model: opus
status: building
created: 2026-11-11
by: Claude
skills: add-screen
repo: app
---

## Report
Owner, 2026-11-11, from a competitor's video: a month calendar of what you pay and when (bills, instalments,
gam3eya, cards), led by "Left to pay in November". Lightning has every date already (`planning/schedule.py`,
`deposits/gameya.py`) but shows them only as lists on Recurring and Loans, so "which days of this month take my
money?" has no screen.

**Owner decisions (2026-11-11):** a new **Upcoming** tab in Cash planning (Plan · Upcoming · Recurring · Loans);
Recurring stays where items are added and edited. First version: the payday line and the cash dip, Mark paid /
link from a day, and a two-week strip on the phone. Later: export to the phone's calendar (.ics), busy-week
shading. A next-7-days card on the Overview links to the tab (one home, a link).

**Question the page answers:** what do I still have to pay this month, and on which days?

## Fix
Figures come from `lightning/planning/calendar.py` (`month_calendar`), never the template: every payment of the
month from planned bills, subscriptions, loans and income, plus gam3eya instalments and the payout, each with its
state (paid, skipped, late, due, upcoming). The header leads with *Left to pay* against *already paid* and last
month; chips filter All · Bills · Instalments · Gam3eya · Income; weeks start Saturday (A12.1.12); the selected
day's payments link to the existing pay sheet (`/plan/items/{id}/pay`) or the circle's page. The payday marks a
day in Meadow and the first scheduled shortfall (`DatedCashForecast.first_shortfall`) in Strong rose (A03).

## Steps
- **7AR1 PC tab (L, opus):** built 2026-11-11 (`tests/test_upcoming_calendar.py`, Mohab
  `test_what_is_left_to_pay_this_month_and_on_which_days`); waits for the owner's PC check.
- **7AR2 Overview card (S, sonnet):** a next-7-days strip on the Summary linking to the tab. After 7AR1.
- **7AR3 Phone strip (M, opus):** the phone's Upcoming tab draws two weeks from today and the day list (built
  2026-11-11, `ui/phone/presenters/upcoming.py`). Left: the same strip on the phone's Money screen in place of
  *Coming up* (`ui/phone/screens/money.py`), then the owner's phone check.
- **7AR4 Export (S, sonnet, later):** an .ics file of the next three months' payments; nothing leaves the device
  until the person saves the file.
