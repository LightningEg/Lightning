---
title: One short review of what changed leads Budget, income drops included, and pacing learns how you shop
type: feature
pillar: plan
size: L
model: opus
github: 638
status: ready
created: 2026-11-13
by: Claude
---

## Report
#626 (2026-11-13). Changes reach the user from separate places (Fill sources, Needs you rows, the raise offer). A scheduled salary falling from 30,000 to 18,000 leaves the budget basis at 30,000 and `HealthService.raise_offer` offers nothing (raises only). A 2,400 shop on the 2nd against 3,000 is told it runs out around day 8; adding a 100 bill to that category turns pacing off for the whole category (`BudgetService.running_out` skips any category with a scheduled payment). Budget and Fill redirect future months.

## Design (owner decisions 2026-11-13)
1. **Income drop: an offer from its date (owner).** `HealthService.income_change_offer(month)` generalises `raise_offer`: when regular scheduled income from a date is at least 10% below the budget basis, offer "Your salary falls to 18,000 from 25 Dec: plan on it from then, or keep the average", with the limits that no longer fit. Plan on it sets the basis from that month (a dated setting, not today's global switch); Keep remembers the amount like `RAISE_DECLINED`. A gap of one month (no scheduled income) is not a drop.
2. **One review leads Budget (owner).** `BudgetService.changes(month)` gathers what changed, each with its evidence, effective month and actions: a changed scheduled bill, a new category with enough history (`tracking_suggestions`), an unusual purchase (NF-12AK step 5), sustained overspending (`over_twice`), an income change (rule 1), a Fill row that differs (NF-12AI). Budget leads with one card: "Your plan continues" when the list is empty, else "N changes to look at" with Accept / Dismiss per row; dismissals are remembered by evidence version and come back only when the evidence changes. Needs you shows one row, the count, linking to it (one figure, one home). Nothing is mandatory.
3. **Pacing learns how you shop (owner).** Pace only the flexible part: the limit minus that category's bills this month, so a 100 bill no longer turns pacing off. Expected spending by day d is the category's own share-by-day curve from the last three completed months when at least two of them had spending, else a straight line; with less history the line says "may run out". Warn only when spending is past the curve by more than 10% of the flexible limit.
4. **Next month, read-only.** `/budget?month=<next>` shows next month as it will start (rules carried forward, scheduled bills, the income from rule 1) with no Save; Fill for it stays closed. Applying waits until the month begins.

Acceptance: the salary case offers 18,000 from 25 Dec; an unchanged month shows "Your plan continues" with nothing to tick; a front-loaded shopper with that history gets no day-8 warning; the bill case still paces the flexible 2,900; next month opens read-only; PC and phone, English and Arabic; Mohab's year passes.


## 12AL3 The "what changed" card leads Budget · L · opus · #646
Rules 1, 3 and 4 are built (#706, #702, #710). The parts of rule 2 also exist, spread out (inventory 2026-11-21): Fill opens on What changed and says "Your plan continues" for an unchanged month (NF-12AI, #656, `partials/budget_fill_empty.html`); Needs you already lists the income change offer, `over_twice`, `running_out` and `below_scheduled` rows (`workflows/review.py`); `tracking_suggestions` exists. Left: `BudgetService.changes(month)` gathering those sources (plus 12AK5's unusual-purchase row) with evidence versions and remembered dismissals; one card leading PC and phone Budget; Needs you replaces its separate budget rows with one row and the count (one figure, one home). Done when: an unchanged month shows "Your plan continues"; each change type appears once with its evidence and stays dismissed until its evidence changes; A16 checked; PC and phone, English and Arabic.
