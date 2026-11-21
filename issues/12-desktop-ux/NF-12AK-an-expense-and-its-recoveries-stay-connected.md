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

1. **Leave one transaction out of estimates.** A table `budget_estimate_exclusions(transaction_id UNIQUE)` (journaled, exported, undoable; skill `add-migration`). An excluded expense, and every refund or reimbursement receipt linked to it, is left out of the estimate basis only. Category exclusions stay as they are (named by IV-12AH; see `tests/test_budget_exclusions_ui.py`). Offered as an optional switch on add/edit and from the review in step 12AK5; never automatic, never because a purchase is large.
2. **Returns count in their purchase's month (owner: link + floor).** A refund can name its purchase: `refund_links(refund_id UNIQUE, expense_id, amount_e6)` with the reimbursement link's capacity checks (never more than the purchase's net). For the estimate basis a linked refund or a claim's linked receipt moves to the purchase's month. After moves, each category's month in the basis is floored at zero (an unlinked refund lowers its month to zero, never below). Cash and Spent keep real dates.
3. **Pending claims count in full until money arrives (owner).** The basis counts the whole expense; Budget and the transaction show *paid · returned · expected back*. When a receipt is linked, rule 2 moves it to the expense's month, so the estimate corrects itself.
4. **A reserve-funded refund goes back to the reserve (owner).** A refund linked to a reserve-funded purchase first lowers that purchase's reserve-funded part (`budget_funding` adjustments), so the reserve keeps what came back and the month shows 0, not −200. A refund beyond the reserve-funded part reduces monthly-plan spending as today.
5. **Occasional spending is averaged over the whole window, labelled (owner).** When the profile has data before the window starts, `_tree_average` divides by every month in the window (6,000 in 3 months → 2,000) and says "1 purchase in 3 months"; a profile newer than the window keeps months-with-spending and says "little history". Fill shows the label beside the source.

Acceptance: the #626 cases above give 1,000 (laptop left out), 2,000 labelled, 0 not −6,000, "1,200 expected back", and reserve 200 restored with the month at 0; Cash flow and the ledger are byte-for-byte unchanged in every case; Mohab's year still passes; PC and phone, English and Arabic.

## 12AK4 Reserve-funded refunds go back to the reserve · M · opus · #647
Rule 4 in `workflows/budget_funding.py` for linked refunds; the reserve page and the month say where the 200 went. Done when: #626's reserve case shows reserve used 800, 200 still in the reserve, the month's plan spending 0; reserve balances otherwise unchanged (number-audit skill).

## 12AK5 Paid, returned, expected back on Budget, and the unusual-purchase review · M · opus · #648
Already built, so not part of this step (inventory 2026-11-21): the transaction page shows *Claimed · received · still owed* and links refunds (`partials/linked.html`, #694); work purchases are kept out of personal spending with their own period card (NF-12AM, #722, migration 0089); one purchase can be left out of estimates (#704). Left: (a) the Budget category sheet shows *paid · returned · expected back · yours* for the category's personal claims and linked refunds (work claims stay in the work-claim card, never counted twice); (b) the review line "Food's average includes a 9,000 purchase on 3 Nov: leave it out of estimates?" with Keep / Leave out (the #704 exclusion), dismissal remembered, only when one purchase is over half the category's window total, offered as one row of 12AL3's card. Done when: the four figures match `ReimbursementService` and `refunds.py`, the review appears once and its choice is undoable, PC and phone in English and Arabic.
