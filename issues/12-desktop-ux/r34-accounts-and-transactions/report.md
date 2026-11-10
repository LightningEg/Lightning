# Audit 19: accounts and transactions - the register, transfers, fixing mistakes and matching the bank

Date: 2026-11-10 · Author/reviewer: Claude
Repository: app · Reviewed commit: a4f696b8a697acf5f08f1f3b0a85bc9ae4ff8643
Code: r34 · App version: 2.1.2

## Assessment

This is the most finished area audited so far. The PC register is fast and forgiving: type a payee and its category
fills, type one of your accounts and the row becomes a transfer, every refusal says what to do instead, and a delete
can be undone. Three things are wrong or stuck: the phone's Money tab reports the month's change in net worth with the
wrong sign for anyone paid on the 1st (N1); a cash wallet that is far from the books cannot be brought back (B2); and
Held for others explains how to do things instead of offering them (H1).

## Scope and method

Transactions (all accounts and one account), entering rows and transfers, editing, deleting and undoing, Adjust
balance, bulk selection, search, the Accounts page, Held for others; on the phone Activity, Money, the accounts list,
an account, a transaction's sheet, Move and search. Sample household on throwaway encrypted profiles, date
2026-11-09, PC at 1366 x 768 and the phone app at 390 x 800, driven by Playwright through the real forms
([flows/](evidence/flows/): `python host.py hosts.json`, Chromium on debug ports 9333 and 9334, `node login.js`, then
`t1.js`, `t3.js`, `t4.js`, `t5.js`, `t6.js`). The net-worth difference was traced in code.

## Findings

Severity: high = a wrong figure or a job that cannot be done; medium = the long way round; low = polish.

| ID | Severity | Observation and expected behavior | Follow-up |
| --- | --- | --- | --- |
| N1 | high | Phone Money: "Net worth 198,821 · −10,438 since the start of the month"; the PC Overview: "+36,395 this month". Money compares with the end of day 1, after the salary lands (36,395 − 46,833 = −10,438). [Screenshot](evidence/phone-money.png). | Fixed: `tests/test_phone_money.py::test_change_this_month_is_the_overviews_figure_even_when_pay_lands_on_the_first` |
| B1 | low | Adjust balance is one bare form (a date and a number); the figure keeps piastres. A small difference is then handled well. [Screenshot](evidence/pc-adjust-small.png). | IV-12V |
| B2 | high | A cash wallet 1,975 off is "Too big to adjust": review row by row or "import the statement again". A wallet has no statement. [Screenshot](evidence/pc-adjust-too-big.png). | IV-12V |
| B3 | low | The adjustment is filed as "Other Personal spending", inside the budget; *Unaccounted Spending* exists and is not used. | IV-12V |
| T1 | medium | A positive amount for a shop (Carrefour, 200) saves as a refund with no question, and the budget's "left" rises. A forgotten minus is silent. | IV-12W |
| T2 | medium | PC search lists actions, accounts and names, then a link to find transactions; the phone shows the payments first. [PC](evidence/pc-search.png), [phone](evidence/phone-search.png). | IV-12W |
| T3 | low | Bulk bar with two rows selected: "Set category for 0" beside "Delete 2". [Screenshot](evidence/pc-bulk-bar.png). | IV-12W |
| T4 | low | Notes is the narrowest column; ".00" on every row. | IV-12W, IV-3AM |
| T5 | low | Zakat is a tab under Transactions; when off it opens Settings with a message. | IV-12W |
| T6 | low | The phone account page shows running balances with piastres beside whole amounts. [Screenshot](evidence/phone-account.png). | IV-12W |
| T7 | low | The phone's Move and From lists offer the CD portfolio, the gam'eya and the broker (r31 A3). | IV-7AL |
| H1 | medium | Held for others has no action on a row; a paragraph explains to use the register with a negative amount. [Screenshot](evidence/pc-held-for-others.png). | IV-12X |

### What works

- **Entering:** payee fills its category; one of your accounts as the payee makes a transfer shown on both sides;
  the toast names what is left in that budget, with Undo. [Register](evidence/pc-account-register.png).
- **Refusals that help:** "Choose a category — or pick one of your accounts as the counterparty for a transfer";
  "2027-01-01 is in the future"; "This would leave Cash wallet at −989,024.00 EGP ... Move money in first".
- **Fixing:** edit in the row; Delete asks once, then "You can restore it from its history page" with Undo.
- **Matching the bank:** a small difference becomes one adjustment row, or *Review rows instead*.
- **Search in the register** finds by name, category and amount (3250, 3,250.75).
- **Bulk:** set category, replace text, make a rule, export, merge, delete.
- **Phone:** Activity with money in and out for the month, a transaction's sheet with what is left in its plan.

## Validation and limits

Browser evidence on sample data; the full suite was not run because no code changed. Not checked: saving an edit,
merge, find and replace, saved views, splitting a row, currency conversion, ownership changes, adding, editing or
deactivating an account, statement import (r23, r31), Arabic, the Android app itself.

## Dated follow-ups

- **2026-11-10, owner decisions (question dialog).** A cash or wallet account may adjust any size, filed as
  Unaccounted Spending; bank accounts keep the limit (IV-12V). A positive amount on a spending category asks once,
  "Refund, or a payment?" (IV-12W).
