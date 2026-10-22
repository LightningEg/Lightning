---
title: Cash planning adds up the bills before payday two ways, so the card and Safe to spend disagree; free cash has three formulas
type: bug
area: planning
status: ready
created: 2026-10-21
by: Claude
skills: number-audit
app_version: 1.3.0
commit: 6e1c043
repo: app
---

## Report
Found by [Audit 4](../../reports/audit-4.md) §4. Severity: medium (a wrong figure on screen).

1. **Payments before next income.**
   - The card and its stat (`ui/kpis.py:229`, `ui/visuals.py:535`) add up `p.amount`: the full amount, in the bill's own currency.
   - The Safe to spend breakdown (`planning/forecast.py:297`) adds up `amount_in_base(p, p.still_owed)`.
   - Reproduced: one 20 USD subscription added to Mohab shows 18,480 on the card and 19,492 in the breakdown. Partly paid bills diverge the same way.
   - `late_total` (`kpis.py:230`) also adds `still_owed` without converting it to EGP.
2. **Free cash, three formulas.**
   - `Position.free_cash` is the one the figures registry names.
   - `reserves.cash_summary` also returns a `free_cash`. Integrity uses it, and `ui/routes/budget.py:398` passes it to a template that never reads it.
   - `forecast.free_cash` has a fallback (`forecast.py:114`) built on `cash_you_own`, which leaves kept-apart cash in. Today it cannot be reached.

## Fix
- `CashForecast` stores the before-income total (in EGP, still owed), and the card, the stat and the breakdown all draw it.
- Delete the `free_cash` key of `cash_summary` and the fallback.
- Test: a foreign-currency bill and a partly paid bill give one total everywhere.
