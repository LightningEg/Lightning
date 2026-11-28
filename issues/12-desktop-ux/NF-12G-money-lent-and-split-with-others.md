---
title: Money lent to others and costs split with others - who owes you what, counted honestly in what you own
type: feature
pillar: own
size: L
model: opus
status: parked
created: 2026-11-06
by: Claude
---

## Report

The owner brought this into scope on 2026-11-06 (OW-12F, from audit r26 F9: [report](r26-user-test-pc-and-phone/report.md)); credit cards and receipt photos stay out. Lending to family and friends and splitting a dinner, a trip or a flat's bills are everyday money in Egypt, and today a person can only hide them in notes or a category. What exists to build on: Held for others (money in your account that is not yours), reimbursement claims (`reimbursements.py`: an owned expense someone will pay back, matched to the receipt), Needs you, and the phone's Add sheet. The decision row is in `ai/PROJECT_OVERVIEW.md` ("Obligations count, forecasts never do").

Rules to keep: one ledger records real money; lending moves money out of your account but not out of what you own until you decide it will not come back; a split records only your share as spending; nothing is assumed repaid until the repayment is posted; one person may owe you and you may owe them, shown as one net figure per person.

## Decided

- 2026-11-08, owner (12G1): all four recommended: (1) one `RECEIVABLE` "Owed to you" account per person, lending and repayment are transfers, forgiving is spending; (2) a split is one entry, only your share is spending, the others' shares go to their accounts; (3) when you owe them, the same account goes below zero and counts in What you owe; (4) words: Owed to you «ليك عند الناس», Lend «سلّف», Paid back «رجّع», Forgive «سامح», Split «قسّم».

## Fix

The owner picks the model in 12G1. The steps below are written for the recommended pick (one "Owed to you" account
per person, of the account type `RECEIVABLE` that the `accounts` CHECK list already allows since migration
`0053_gameya.sql`, worked like a Gam'eya account: lending and repayment are transfers, forgiving is spending). If the
owner picks another option, rewrite 12G2-12G9 before anyone starts them.

2026-11-27: 12G7 built (Money out on PC and phone, with form replay and repayment covered by tests). 2026-11-22: 12G3 built (`PeopleMoneyService.split/update_split`, `TransactionService.record_split`; synced). 2026-11-10: 12G2 built (`lightning/people_money.py`, migration 0078, `tests/test_people_money.py`; synced as `people_money.lend/repay/forgive`). 2026-11-08, before it: nothing was built: `AccountType` (`lightning/accounts/domain.py`) has no
`RECEIVABLE`, no service lends or splits, and `lightning/planning/position.py` has no "Owed to you" figure. Pieces to
reuse: `ReimbursementService` (`lightning/reimbursements.py`, claims on an expense, never posts money),
`MoneyFromOthersService` (`lightning/money_from_others.py`, Held for others), `GameyaService`
(`lightning/deposits/gameya.py`, the account-per-arrangement pattern), the person page
(`lightning/ui/routes/counterparties.py` `counterparty_page`, `lightning/workflows/linked.py` `counterparty`,
`lightning/ui/templates/counterparty.html`).

## How to work on this item

Each step is one pull request. Read only the files a step names; money rules are in `ai/ARCHITECTURE.md` (grep
`^## `). Run the step's test command, then `python -m pytest tests/test_issues.py -q`; for a visible change also
`python -m pytest tests/test_mohab_year.py -q`. Delete the step's heading in the same commit (AGENTS.md §3).


## 12G4 Who owes what, per person · M · sonnet
Needs 12G2 merged first.
Files: `lightning/people_money.py` (add `by_person(as_of) -> list[(person, net)]`, non-zero only, biggest first),
`lightning/ui/routes/counterparties.py` (the list route `@router.get("")` line ~14), `lightning/ui/templates/counterparties.html`,
the phone person list if one exists (`grep -rln "counterpart" lightning/ui/templates/phone`), `lightning/ui/i18n.py`.
Do: each person row shows one signed net figure (owed to you positive, you owe negative, if 12G1 point 3 chose (a)),
tone by meaning (A03), "Remind" copies a sentence "You owe me {amount} for {last note}" to the clipboard
(`navigator.clipboard`, text built in the template from server values), "Settle" opens the Paid back form of 12G6
with the amount filled.
Done when: `tests/test_people_money_screens.py` gains a case where a person is owed 800 and owes 300 and the list shows
one row of 500. `python -m pytest tests/test_people_money_screens.py -q`.

## 12G5 Mohab, Arabic and the guideline · M · sonnet
Needs 12G4, 12G6 and 12G7 merged first.
Files: `tests/test_mohab_year.py` (read only its docstring and `_a_gameya`, line ~660, as the pattern),
`lightning/ui/i18n.py`.
Do: add `_lending_and_splits(o)` after `_a_gameya`: Mohab lends his brother 5,000, gets 3,000 back, forgives 2,000;
splits a 1,200 dinner with two friends; one pays back. Each step `o.ask(...)` the Overview, Accounts and the person
page and checks the figures moved by exactly those amounts. Check both themes and 320 px with `python tools/phone_check.py`
and A16 on a screenshot.
Done when: `python -m pytest tests/test_mohab_year.py tests/test_mohab_phone.py tests/test_arabic_no_english.py -q`
passes with the new steps.
