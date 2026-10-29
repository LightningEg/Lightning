# Audit 10: the backend walked through use cases

Date: 2026-10-29 · Author/reviewer: Claude
Repository: app · Reviewed commit: `045ccd48dcb6a0d69605f6e0226259dcd823f119`
Historical ID: audit-10

## Scope and method

The owner asked for a use-case audit of the backend: loose ends, bugs, and whether refactoring is needed. A salaried
person's year was driven through the services and, where a screen decides the outcome, through the routes, on throwaway
dummy profiles:

- **Everyday money:** amounts and dates at their limits (zero, negative, `1e3`, `NaN`, Arabic digits, sums, 31 February,
  year 1 and 9999), spending more than an account holds, transfers, splits, edits that would break a later balance, void,
  restore, Undo, deactivating an account, moving an opening date or balance.
- **Investments:** buys and sells against cash and units, fractional and zero quantities, edits and voids a later sale
  depends on, dividends with tax, broker fees, moving units.
- **Plans:** loans and bills paid, part paid, skipped, reopened, voided and edited afterwards; budgets (months, amounts,
  income percentages, carryover, moving room); reserves (targets, allocation, links, edits of a linked expense).
- **Other people's money, currencies, checked accounts:** custody in and out, conversions (fee, same currency, extreme
  rates), rates, closing an account against the bank and then editing, backdating or adjusting inside it.
- **Certificates, gam'eya, reimbursements, rules:** purchase, redeem, void; instalments and payout; claims and receipts;
  apply to the past and its undo.
- **Reports at odd periods:** reversed, empty, future and 1,000-month ranges; zero income; positions in 2020.
- **A fuzzer:** 30 seeds × 250 random writes (money in and out, transfers, edits, voids, restores, bulk deletes, buys,
  sells, dividends, custody, payments by another person, conversions, splits); after each of the ~4,500 writes that saved,
  every integrity check and the zero-sum of every transfer were checked at year end and at a random month end.
- **Structure:** `ruff`, `import-linter`, `vulture`, the longest functions, duplicated helpers, the items already filed.

Out of scope: `lightning/sync/journal/` and the journal runtime (claimed by a Claude session), `runtime/restore.py` and
Windows promotion (claimed by Luna), native devices, the website. All data was dummy data.

## Findings

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F1 | low | The cash guard checks only from an account's opening date, so moving the opening date past existing spending (or spending before it) leaves −9,000 on 2026-01-31, which Integrity then reports as an ISSUE. The rule is the owner's (history before opening is allowed on purpose). | `evidence/use_cases.py` F1 | [BT-2E](../../issues/2-safe-for-real-money/2E-engine-input-checks.md) item 6 |
| F2 | medium | After paying 1,000 of a 2,500 loan instalment, the pay page offered "Move to the end of the loan"; it replaced the payment with a skip, so still to pay went from 29,000 back to 30,000 and the 1,000 was unlinked. The service also skipped a fully paid date from a stale page, accepted a date off the schedule (lengthening the loan by one more instalment) and failed with a database error on a malformed date. | `evidence/use_cases.py` F2 | Fixed on this branch: `PlanningService.skip` refuses an unscheduled or settled date; the button shows only for unpaid ones. `tests/test_planning.py::test_skip_never_forgets_a_payment_or_lengthens_a_loan_off_its_schedule` |
| F3 | low | Editing a paid bill's transaction (500 → 5,000, February → December) keeps the bill PAID for 500 in February and 0 bills due on 2026-02-28. Loans refuse the edit and reserves drop the link (7R): three rules for one situation. | `evidence/use_cases.py` F3 | [BT-7U](../../issues/7-planning-import-and-search/7U-bill-link-after-payment-edit.md) |
| F4 | medium | The same conversion, certificate purchase or gam'eya instalment form sent twice saved twice (double the dollars, two certificates, the next instalment recorded as well). The busy button stops an ordinary double click; a resent request was not stopped. Five more forms remain. | `evidence/use_cases.py` F4 | Fixed for the three: the one-time `submission` token of 2J. `tests/test_engine_loose_ends.py::test_a_resent_money_form_saves_once`. The rest: [BT-2AD](../../issues/2-safe-for-real-money/2AD-resent-money-forms-save-twice.md) |
| F5 | medium | A conversion with sent and received swapped (100 EGP → 5,000 USD) saves without a question though its quote reads 100% below market; its rate then values every dollar at 0.02 EGP, so net worth drops from 100,000 to 95,002. | `evidence/use_cases.py` F5 | [BT-5J](../../issues/5-investments/5J-conversion-raises-net-worth.md) |

**What held.** Every amount and date edge was refused with a plain message or read as intended. No edit, void, bulk
delete, restore or Undo left a wallet or bank below zero, a sale above the units held, or a transfer unbalanced, in the
probes or in ~4,500 fuzzed writes: no crash and no broken invariant. Checked months refused every financial change
including backdated inserts and adjustments. Loan payments refuse edits until reopened; a voided payment reopens its bill;
reserves refuse links above the expense or the cash assigned; certificates refuse a redemption before lockup or in the
future; reports return empty, sensible figures for empty, future and reversed periods, and `None` (not a division error)
for a savings rate without income.

**Smaller observations, not filed.** A dividend dated after every share was sold is refused (a dividend paid after selling
past the ex-date must be dated on or before the sale). Undoing "Apply rule to the past" restores the old categories even
on rows recategorised since. A crafted form value (`transaction_id=abc`) reaches the calm error page instead of a field
message. A bridge or cash flow asked with the dates reversed returns meaningless figures; no screen asks it.

## Is refactoring needed?

No broad refactor. The layer contracts (import-linter: 4 kept), `ruff` and the money rules hold, and the open structure
work is already filed and right-sized: [IT-9K](../../issues/9-later/9K-layers-and-copies.md) (the 767-line
`runtime/app.py:profile_app`, budgeting calling planning through bootstrap, three balance-floor checks, a trigger matched by
message text), [IT-9J](../../issues/9-later/9J-routes-compute-figures.md) (routes still computing figures; `budget._page`
is 304 lines, `register.page` 213) and [IT-4K](../../issues/4-edit-journal-and-devices/4K-journal-code-tidy.md). Two
consolidations this audit adds, each inside an item:

1. **One way to save a form once.** Seven routes now repeat the `submitted` / `remember_submission` pattern and five more
   need it (2AD). When 2AD is built, move it into one helper beside `container()` so a new money form cannot forget it.
2. **One rule for links when the linked transaction changes.** Loans, reserves and bills each answer differently (F3); the
   decision in 7R and 7U should give one rule in one place.

`vulture` found six unused locals and parameters (`sms_imports.py:225`, `workflows/ai_analysis.py:41` and
context-manager `exc_type` arguments); none is a defect.

## Validation and limits

- Before the fixes: `python -m pytest -n auto --dist loadfile` 2,747 passed, 41 skipped. Each new test fails without its
  fix and passes with it; the full suite and Mohab's year were run again before pushing (see the pull request).
- `python reports/2026-10-29-use-case-audit/evidence/use_cases.py` reproduces F1–F5 (F2 and F4 show the fixed behaviour);
  `python reports/2026-10-29-use-case-audit/evidence/fuzz.py 0 30` is the fuzzer (about ten minutes).
- Service and route level only, through FastAPI's test client: no browser, phone or Windows run, no journal profile, no
  restore or power loss. The fuzzer covers ordinary cash, one stock and one foreign account; it does not cover plans,
  budgets, certificates, gold or imports.

## Dated follow-ups
