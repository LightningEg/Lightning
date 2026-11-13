---
title: Move room asks whether to cover this month or change the usual plan
type: feature
pillar: plan
size: M
model: opus
status: ready
created: 2026-11-13
by: Claude
---

## Report
#626 stress test (2026-11-13): moving 500 from Transport to Food for December also changes January (3,000/2,000 becomes 3,500/1,500), because `BudgetService.move_room` changes the rules from that month on. Owner decision 2026-11-13: offer both.

## Fix
The Move dialog (PC `budget_move.html`, phone `phone/budget_move.html`) has two choices, each with its before/after: *Cover this month* (this-month-only limits on both categories) and *Change my usual plan* (today's behaviour). The default follows the reason the dialog already works out: pace or over this month → this month; over two months running → usual plan. `move_room` takes the duration; the service owns it. Tests: this-month move leaves January as it was; usual-plan move changes it; the total plan is unchanged either way; undo restores both.
