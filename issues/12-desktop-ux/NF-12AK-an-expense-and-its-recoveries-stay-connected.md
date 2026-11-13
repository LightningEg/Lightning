---
title: An expense and its refunds and reimbursements stay connected, and estimates stop counting one-time purchases as monthly
type: feature
pillar: plan
size: L
model: opus
github: 637
status: ready
created: 2026-11-13
by: Claude
---

## Report
#626 (2026-11-13). Budget estimates (`BudgetService._completed_months` → `plan_funded_spending` → `_tree_average`) read each month's category totals as they fell, so:
- one 9,000 laptop beside 1,000 a month of normal food makes the average 4,000, and the only tool, a category exclusion, also drops the normal 1,000;
- one 6,000 purchase in three months is suggested as 6,000 a month (only months with spending count);
- a full 6,000 refund two months later makes January's average **−6,000**;
- a 1,200 work expense with an open 1,200 claim shows nothing about the 1,200 expected back;
- a 200 refund of a reserve-funded 1,000 purchase shows −200 monthly-plan spending.
Reproductions: the scripts in #626.

## Design (owner decisions 2026-11-13)
**Three figures, never mixed.** *Cash* (what moved, on its date: ledger, Cash flow, reports) never changes. *Spent* (Budget's figure for a month: today's plan-funded spending) changes only where step 12AK4 says. *Estimate basis* (what averages and Fill read) is a new service figure, `BudgetService.estimate_spending(start, end)`, built from Spent as below. Every rule lives in Python services; templates only show.

1. **Leave one transaction out of estimates.** A table `budget_estimate_exclusions(transaction_id UNIQUE)` (journaled, exported, undoable; skill `add-migration`). An excluded expense, and every refund or reimbursement receipt linked to it, is left out of the estimate basis only. Category exclusions stay as they are (IV-12AH names them). Offered as an optional switch on add/edit and from the review in step 12AK5; never automatic, never because a purchase is large.
2. **Returns count in their purchase's month (owner: link + floor).** A refund can name its purchase: `refund_links(refund_id UNIQUE, expense_id, amount_e6)` with the reimbursement link's capacity checks (never more than the purchase's net). For the estimate basis a linked refund or a claim's linked receipt moves to the purchase's month. After moves, each category's month in the basis is floored at zero (an unlinked refund lowers its month to zero, never below). Cash and Spent keep real dates.
3. **Pending claims count in full until money arrives (owner).** The basis counts the whole expense; Budget and the transaction show *paid · returned · expected back*. When a receipt is linked, rule 2 moves it to the expense's month, so the estimate corrects itself.
4. **A reserve-funded refund goes back to the reserve (owner).** A refund linked to a reserve-funded purchase first lowers that purchase's reserve-funded part (`budget_funding` adjustments), so the reserve keeps what came back and the month shows 0, not −200. A refund beyond the reserve-funded part reduces monthly-plan spending as today.
5. **Occasional spending is averaged over the whole window, labelled (owner).** When the profile has data before the window starts, `_tree_average` divides by every month in the window (6,000 in 3 months → 2,000) and says "1 purchase in 3 months"; a profile newer than the window keeps months-with-spending and says "little history". Fill shows the label beside the source.

Acceptance: the #626 cases above give 1,000 (laptop left out), 2,000 labelled, 0 not −6,000, "1,200 expected back", and reserve 200 restored with the month at 0; Cash flow and the ledger are byte-for-byte unchanged in every case; Mohab's year still passes; PC and phone, English and Arabic.

## 12AK1 Estimate basis in one service · L · opus
Add `BudgetService.estimate_spending(start, end)` = plan-funded spending with rules 2 (receipts already linked through claims only) and the zero floor, and make `_completed_months` read it; add rule 5 to `_tree_average` with `history_months` in `category_averages` for the label. No schema change. Done when: tests reproduce #626's −6,000 and 6,000-a-month cases and show 0 and 2,000, a reimbursed claim's receipt counts in the expense's month, and `tests/test_mohab_year.py` passes.

## 12AK2 Leave one transaction out of estimates · L · opus
Migration for `budget_estimate_exclusions` (skill `add-migration`: journal, export, undo); the basis skips it and its linked returns; a switch on the PC and phone transaction edit and on add under More. Needs 12AK1 merged first. Done when: the laptop case averages 1,000 with the purchase still in Cash flow and Spent, the switch round-trips with undo, an older profile upgrades.

## 12AK3 A refund names its purchase · L · opus
Migration for `refund_links`; *This refunds…* on a refund's edit (type and pick a purchase in the same category, last 6 months) and *Record a refund* on a purchase prefilled with the link; capacity checks as reimbursement links; rule 2 reads it. Needs 12AK1 merged first. Done when: a linked 6,000 refund in November counts in September for estimates, unlinking restores it, over-linking is refused.

## 12AK4 Reserve-funded refunds go back to the reserve · M · opus
Rule 4 in `workflows/budget_funding.py` for linked refunds; the reserve page and the month say where the 200 went. Needs 12AK3 merged first. Done when: #626's reserve case shows reserve used 800, 200 still in the reserve, the month's plan spending 0; reserve balances otherwise unchanged (number-audit skill).

## 12AK5 Paid, returned, expected back, and the unusual-purchase review · M · opus
The transaction detail and the Budget category sheet show *paid · returned · expected back · yours*; a Budget review line "Food's average includes a 9,000 purchase on 3 Nov: leave it out of estimates?" with Keep / Leave out, dismissal remembered, only when one purchase is over half the category's window total. Needs 12AK2 and 12AK3 merged first. Done when: the four figures match the claims service, the review appears once and its choice is undoable, PC and phone in English and Arabic.
