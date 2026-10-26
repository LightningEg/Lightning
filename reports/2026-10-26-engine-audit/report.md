# Audit 8: backbone engine gaps and loose ends

Date: 2026-10-26 · Author/reviewer: Claude
Repository: app · Reviewed commit: 705945c5e99ee4845b653253083f32be1c2d165a
Historical ID: audit-8

## Scope and method

The owner asked: does the backbone engine have gaps or loose ends, and fix them. Scope: the shared posting writer, every write path around it (deposits, reserves, circles, reimbursements, accounts, categories, counterparties, undo), planning and loans, investments, workbook onboarding, reporting, valuation and the integrity checks. Excluded: the edit journal (`lightning/sync/journal/`, claimed), UI layout and Arabic wording.

Two passes. First, the open engine items from Audits 1 and 4 (2I, 2J, 2L, 2M). Second, three independent read-only reviews of areas earlier audits did not cover, each confirming a suspected defect with a probe on a temporary dummy database before reporting it. Every finding below was reproduced and now has a regression test in [`tests/test_engine_loose_ends.py`](../../tests/test_engine_loose_ends.py) (34 cases), which is the evidence for this report: `python -m pytest -q tests/test_engine_loose_ends.py`.

## Findings

| ID | Severity | Observation and expected behavior | Follow-up |
| --- | --- | --- | --- |
| 2I | medium | `post()`/`repost()` accepted USD cash in an EGP account, EGP cash at a rate other than 1, and an investment posted as cash. The shared writer now checks every new line against master data inside the write. | fixed |
| 2J | medium | Resending one add form saved two expenses. Register, all-accounts register and add popups now carry a one-time token saved in `audit_log` with the posting; a resend returns the first save, a changed resend is refused. | fixed on ordinary profiles; journal profiles remain in [2J](../../issues/2-safe-for-real-money/2J-register-submit-idempotency.md) |
| 2L | medium | A sub-cent purchase price or fee made an unpayable final instalment; early-payment principal and fee had the same gap. Now refused at entry. | fixed |
| 2M | high | Conversion, ownership and investment edit forms lacked the revision field their routes already checked. Applied Audit 4's patch; stale saves are refused and keep the typed values. | fixed |
| B1 | medium | After voiding a CD redemption, redeeming again crashed (HTTP 500, unique constraint). The voided redemption's row is now replaced; restoring it is refused by the holding check. | fixed |
| B2 | medium | Restoring a voided expense could make a reserve pay out more than was assigned (allocated 300, spent 500). Restore and undo now refuse it. | fixed |
| B3 | medium | An account could be deactivated while a live certificate, circle, active reserve or plan still paid into it. Now refused, naming the record. | fixed |
| B4 | low–medium | Deleting a category or counterparty used only by a plan or reserve crashed; a claim's payer was silently removed. Delete now asks every foreign key and archives instead. | fixed |
| B5 | low | A circle could record a second payout (void, record, restore) or a fourth instalment of three (plain transfer). The holding check now enforces the circle's terms on every path. | fixed |
| B6 | low | Reimbursement amounts accepted 10.0001. Now whole minor units. | fixed |
| B7 | low | Editing an expense's amount silently unlinks it from its reserve (deliberate trigger, no message). | owner decision: [7R](../../issues/7-planning-import-and-search/7R-money-edit-drops-reserve-links.md) |
| C1 | medium | A backdated early payment could pay off an already settled loan again (600 paid on a 300 loan). Capped by what is owed after every recorded repayment. | fixed |
| C2 | medium | Paying 250 on a 100 instalment moved 250 but counted 100; the rest vanished. Paying or linking more than an instalment owes is now refused; the excess goes through early payment. | fixed |
| C3 | medium | "Already paid up to today" moved a bill's day for good (the 31st became the 30th; a weekend-moved 4th became the 6th). The anchor is now the calendar date and monthly plans keep their day. | fixed |
| C4 | medium | Workbook onboarding accepted future-dated transactions and holdings below zero units, which manual entry refuses. Now refused before import. | fixed |
| C5 | low–medium | Editing a brokerage buy could pay it from a bank account, bypassing "pay from the broker's own cash". The edit now runs the same check. | fixed |
| A1 | medium | Investment fees in a month raised a false ISSUE in "Budget actual equals categorized spending" (the budget leaves them out by design). Compared like for like now. | fixed |
| A2 | medium | Two integrity checks could never fail. "Categorized expenses equal reported spending" (one sum against itself) is replaced by an independent ledger check, "Profile-currency cash moves at face value". The net-worth bridge check remains. | bridge: [2Z](../../issues/2-safe-for-real-money/2Z-net-worth-bridge-check-cannot-fail.md) |
| A3 | medium | An Other-asset estimate hid money moved out of that account after the estimate's date (net worth unchanged after a 100,000 outflow). The estimate now carries later movement. | fixed |
| A4 | low | Money out under an income category counts as spending, not as less income; follows the documented `flow_of` rule. | owner decision: [7S](../../issues/7-planning-import-and-search/7S-money-out-of-an-income-category.md) |
| A5 | low | `monthly_flow_between` overflowed in December 9999. | fixed |

Checked and sound, per the three reviews: Decimal-only money with consistent rounding; empty ledgers and leap days; FX direct/inverse/cross selection and its 45-day floor; average-cost pools and realized gain on partial sells; selling more than held; dividend currency and tax; schedule month-end clamping; bank CSV confirm atomicity and duplicate flags; SMS read and assign; merge checks; undo/redo replay validation; reconciliation locks; CD and circle write atomicity; the reserve amount limits.

## Validation and limits

Full suite on the final head: all pass except `test_the_app_and_website_guidelines_are_all_mirrored`, which fails on `main` too (`guideline/themes.md` is newer in the website repo; another session's change). Import contracts: 4 kept. Mohab's year (PC and phone) passes.

Not checked: the edit journal, native Windows/Android behavior, real power loss, concurrency beyond the existing tests. 2E items 6–8 (dates before an account opened, rounded parts, revaluation churn) remain as filed. 5J (a conversion's rate revalues every dollar holding) still waits for the owner's decision.

## Dated follow-ups
