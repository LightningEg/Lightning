---
title: Offer the next step where a figure or row raises the question, always with a preview and an explicit confirmation
type: feature
pillar: plan
size: L
status: new
created: 2026-11-06
by: Claude
---

## Report

Audit r24 ("Smarter connections") found the pieces already exist: recurring recognition, salary matching, certificate receipts, reimbursements, reserve-backed bills, cash funding, saved reports, early loan repayment and the asset-to-loan link. What is missing is the next action appearing at the moment of need, with one shared preview. These are extensions, not missing modules. Evidence: [r24 smarter connections](r24-desktop-phone-ux/report.md#smarter-connections-extend-what-exists).

Rules for every step: use posted cash and recorded facts, never assume receipt; one economic event, one posting; ambiguous matches stay questions; the user picks the scope; every action shows its before and after and can be undone; forecasts are never treated as received cash. Cross-device completion (phone capture, PC review, phone confirmation) waits on 4A and 4B.

## Fix

Take one step at a time, each with its own test and Mohab step.

Done: 3AZ1 (`partials/payday_proposal.html` on PC and phone, `funding.preview()['proposal']`; `tests/test_salary_day_review.py`, Mohab `_confirm_payday_proposal`). Needs you › Salary received opens the proposal; looking assigns nothing; Confirm assigns once; Undo restores.

3AZ4: `routes/planning.py::_payment_effects`, `planning/pay.html`; a close match blocks a second expense; `tests/test_bill_sheet.py`.

3AZ3: `RuleService.record_correction/suggestion`, `/rules/offer`, journal commands `rules.record_correction/clear_corrections`; `tests/test_rule_from_corrections.py`.

3AZ2: `bank_import_proposals.py` offers the link by default when only an SMS backs the one candidate, marks it "recorded from your SMS", and asks when several fit; `tests/test_statement_links_sms.py`.

## 3AZ5 A reimbursable expense offers Create claim, and the receipt offers Match reimbursement · M

Claim outstanding and cash received stay separate and a partial match reduces the claim once. Done when both entry points reach the same claim.

## 3AZ6 Can I afford this checks the chosen account on the chosen date · M

Show "fits your plan" and "this account has enough on that date" together, with assumptions, and record only on confirmation. Done when the answer names the account, the date and the scheduled-only versus budget-inclusive basis.

## 3AZ7 Emergency refill proposes an affordable schedule · M

Builds on the refill preview (BT-2AH): a schedule after upcoming needs, with a manual alternative. Done when each instalment shows its forecast after-state.

## 3AZ8 A maturing certificate shows the expected date, then allocation choices after the receipt is recorded · M

The forecast is never received cash; receipt matching stays explicit. Done when allocation choices appear only after a recorded receipt.

## 3AZ9 An investment result explains what changed · M

Contributions, prices, FX and income, with the affected rows; missing or stale values stay visible; allocation suggestions are not advice. Done when a period result lists its parts and links to the rows.

## 3AZ10 Needs you groups by job and consequence · M

Money at risk, unreconciled events, optional cleanup; reviewed or snoozed never silently means resolved. Done when Overview, Needs you and Weekly review lead to the same task and state.
