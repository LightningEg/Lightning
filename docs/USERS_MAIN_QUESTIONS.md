# Users' Main Questions

The user-facing questions each Lightning screen must answer, including known gaps and follow-ups. From [Project overview](PROJECT_OVERVIEW.md); related scenario coverage: [`tests/test_mohab_year.py`](../tests/test_mohab_year.py).


Each tab answers one main question, then its follow-ups. Reviewed 2026-10-13; `tests/test_mohab_year.py` checks the answers, so only open gaps are listed below.

| Screen | Main question | Leads with |
|---|---|---|
| Overview | Where do I stand, and what needs me? | Needs you, Net worth, Free cash, what it is made of, cash flow |
| Expense analysis | Where did my money go? | Money out, ranked categories, change from last period |
| Budget | Am I on plan? | Left in plan, everyday spending against pace, categories over plan |
| Investments | What do I hold, and how did it do? | Net gain or loss, holdings, allocation |
| Cash planning | How much can I actually spend? | Safe to spend, What you owe, forecast |
| Reserves | Am I safe if something goes wrong? | Emergency fund in months |
| Financial health | How do my figures compare with my limits? | Emergency fund, Savings rate, debt and fixed-cost ratios |
| Account | What happened here? | One balance, add/import, register |
| Held for others | Whose money am I holding? | Balances by person |
| Settings · Checks | Is my data right? | Integrity checks |

Every other follow-up (net worth breakdown, what I owe, spend until payday, due next, forecast low point, categories over plan, loans in the plan, class returns, sale value, target mix, payoff date, debt ratios, bonus and job-change effects, fees) is answered. Open gaps:

| Question | Gap |
|---|---|
| Why did net worth change: saving, prices or new money? | Partial: no wealth-change bridge (M3.2) |
| Can I afford this purchase now? | Partial: no "what if I buy it" check |
| A merchant or a few categories I care about | Built locally: named live-date register views, matching report and export |
| A refund: did my spending go down? | Partial: it lowers the category in the month the refund arrives, not the purchase month (Mohab 13) |
| Work spending my employer owes me back | Built locally: explicit claims and partial receipt/refund links list outstanding amounts |
| What about next month's plan? | Partial: rules repeat; a future month cannot be opened |
| Where should the rest of my income go? | Built locally: optional funded payday preview using actual cash, with reserve top-ups |
| Have I actually set aside the goal's monthly amount? | Partial: nothing asks him to assign it |
| I paid from the emergency fund: what now? | Partial: nothing reminds him to refill (Mohab 14) |
| Pay the loan off early | Missing: no lump-sum payment |
| When does my certificate mature? | Portfolio dates and explicit interest receipt reconciliation built; legacy account-level conversion remains |
| How are my dollar savings and US stocks doing? | Built in v1.1; open: bank-imported pairs across currencies, Europe and GCC listings |
| No pay this month: does the average fall? | Known gap: zero-income months are skipped by the average (Mohab 27) |
| Was I paid my raise? | Partial: the scheduled payment stays Due until linked by hand |
| Is my salary late? | Left out by decision |
| Stale prices | Needs you flags prices older than about two months; month-end price gaps are listed |

Early pay, raise and rent changes need explicit confirmation by design: Lightning suggests, Mohab confirms, neither plan nor reserve changes silently. Left open by the 2026-10-05 audit: a payment scheduled on the 31st moves to the 30th after a shorter month and stays there.
