# Same-category repayments

Date received: 2026-11-03 · Reviewed: 2026-11-03
Product/build/surface: Lightning reimbursement workflow
Source: direct user request, sanitized

## Observations and themes

| ID | Observation | Expected outcome | Theme | Investigation verdict | Issue / disposition |
| --- | --- | --- | --- | --- | --- |
| FB1 | A user requested suggested reimbursement pairing and prefers recording money back in the original expense category. | Repayments reduce category spending and remain linked to the expense, including partial receipts. | Reimbursement flow | Existing bookkeeping behavior; requested discovery and entry improvements | Implemented reimbursement portion of NF-7L4; [regression tests](../tests/test_reimbursement_pairing.py). Import/certificate parts remain open. |

One observation from one respondent. No personal or financial source data retained.

## Dated follow-ups

2026-11-03: Verified Money in to an expense category already reduces spending through the shared flow rule. Added reviewable same-category pairs, prefilled claim review and receipt entry using the original category. Confirmations reuse existing synchronized commands and preserve ledger cash, income and spending totals. Tests cover partial repayments, duplicates, changed candidates, ambiguity, undo, currency, ownership and PC/phone flow.
