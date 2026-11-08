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

3AZ8: `DepositService.maturity_outlook`, the portfolio page forecast line and allocation choices; `tests/test_maturity_choices.py`.

3AZ7: `CashForecaster.refill_schedule`, instalments and a manual preview on `/plan/reserves`; `tests/test_refill_schedule.py`.

3AZ6: `planning/afford.py::account_check`, `DatedCashForecast.account_series`, `/plan?afford_account=&afford_date=`; `tests/test_afford_account_date.py`.

3AZ5: `LinkedSections._reimbursement_offer`, `partials/linked.html`, `/reimbursements?receipt_id=`; `tests/test_claim_entry_points.py`.

3AZ4: `routes/planning.py::_payment_effects`, `planning/pay.html`; a close match blocks a second expense; `tests/test_bill_sheet.py`.

3AZ3: `RuleService.record_correction/suggestion`, `/rules/offer`, journal commands `rules.record_correction/clear_corrections`; `tests/test_rule_from_corrections.py`.

3AZ2: `bank_import_proposals.py` offers the link by default when only an SMS backs the one candidate, marks it "recorded from your SMS", and asks when several fit; `tests/test_statement_links_sms.py`.

## 3AZ9 An investment result explains what changed · M

Contributions, prices, FX and income, with the affected rows; missing or stale values stay visible; allocation suggestions are not advice. Done when a period result lists its parts and links to the rows.

## 3AZ10 Needs you groups by job and consequence · M

Money at risk, unreconciled events, optional cleanup; reviewed or snoozed never silently means resolved. Done when Overview, Needs you and Weekly review lead to the same task and state.
