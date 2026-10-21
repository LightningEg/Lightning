---
title: The engine accepts some bad input - split decimals, money on a gold account, cash below zero, an unknown owner, dates before an account opened
type: bug
area: transactions
status: ready
created: 2026-10-20
by: Claude
skills: bug-hunt, number-audit
app_version: 1.3.0
commit: 7591231
repo: app
---

## Report
Found by [Audit 1](../../reports/audit-1.md) (§1 Engine). The formulas hold; these are gaps in what the write paths refuse. Severity: high for 1, medium for 2–5, low for the rest.

1. **A split loses a piaster.** Split a 1,000 expense as 333.334 / 333.333 / 333.333 (`POST /transactions/{id}/split`): accepted; each line keeps
   333.333 but its EGP value rounds to 333.33, so the account's EGP balance and its own balance differ by 0.01. Cause: `transactions/service.py:602`
   calls `to_decimal` without `check_places(..., asset.quantity_decimals)`. Should say "Use at most 2 decimal places" like every other money form.
2. **Money in or out on a gold account.** The register's quick-add offers "Gold at home"; an expense of 250 there is saved and leaves negative cash
   inside the gold account. `_money_lines` (`transactions/service.py:883`) refuses only DEPOSIT accounts; refuse physical-asset accounts too, as transfers already do.
3. **Cash goes below zero, even into money held for others.** Demo: CIB 71,328 (10,000 is Mom's); a 65,000 transfer then a 65,000 expense leave
   CIB at −58,672 while Held for others still lists Mom's 10,000, and all data checks pass. A single expense of 999,999,999,999 is also accepted.
   CD purchases, brokerage buys and money-from-others already refuse when cash is short: refuse or warn the same way, and add a data check.
4. **500 on an unknown owner.** `POST /accounts/{id}/transaction/new` with `owner_id=99999`: `ui/routes/accounts.py:291-292` reads `party["active"]`
   without checking `party` (do as `investments.py:595`).
5. **Planner crashes on 0 or a negative amount.** `POST /investments/planner amount=0`: 500. `investments.py:442` raises `LightningError`; only
   `ValidationError` is handled (`web.py:480`).
6. Low: dates before an account opened are accepted (1900-01-01; one 10 EGP entry in July cut average spending from 24,049 to 16,036 and lifted the
   emergency fund from 0.8 to 1.2 months). Crafted posts 500 on a bad bucket (`investments.py:570/572`), a bad category direction
   (`categories/service.py:209`) and ids ≥ 2^63 (`OverflowError`). A plan amount of 350.555 is silently rounded; a reserve of 12.345 is accepted.
7. Low: shown parts don't add up by rounding: "If you sold today" 130,586 against parts summing to 130,585; "Where money in went" 46,834 against 46,833.
   Round the parts so they sum to the shown total (largest remainder).
8. Low (tech): every investment post voids and reposts the month-end revaluation entries; a fuzz run left 456 void VAL transactions. Reuse them when unchanged.

## Fix
One branch per group (1–3, 4–6, 7–8), each with a test that posts the bad input and expects a refusal or matching totals.
