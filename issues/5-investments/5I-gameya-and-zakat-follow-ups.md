---
title: Gam'eya and zakat follow-ups: no circle in the sample, no phone breakdown, an early-turn circle shown below zero
type: bug
look: visual
severity: medium
pillar: own
size: M
status: new
created: 2026-10-19
by: Claude
---

## Report
- Investments shows an early-turn circle below zero, while Position moves it to What you owe. **Open, needs an owner decision** (below).

2026-11-02, built: the demo household has an office circle whose pot he took early (the 2026 sample already had one), and the phone Overview's What you owe opens on its parts, the circle among them (`tests/test_demo_and_visuals.py::test_the_demo_has_a_gameya_circle_the_pot_of_which_is_already_taken`, `::test_the_phone_overview_breaks_what_you_owe_into_bills_loans_and_the_gameya`).

## Decision needed: where does an owed circle live?
The investment report treats a circle like a deposit (balance = value; instalments and the payout cross the boundary), so it reconciles, but an owed circle then reads as a negative holding. Choices:
1. **Keep it below zero there**, but label it "You owe the circle" with a link to What you owe (one figure, shown twice, no reconciliation change).
2. **Leave an owed circle out of Investments** while its balance is negative, flows included, in the opening and closing values alike (needs a per-date rule so the period reconciles).
3. **Clamp the value at zero** and add a reconciliation line "Owed to the circle (in What you owe)" (one home; the line keeps the sum at zero).

**Read:** Architecture › Gam'eya, `lightning/investments/report.py` (`balance_ids`).
