import os, sys, tempfile, json
from pathlib import Path
from datetime import date, timedelta
"""r31: the owner functions' own values for the headline figures (the registry in lightning/core/figures.py names them).

    python issues/11-phone-ux/r31-figures-one-owner/evidence/owners.py demo 2026-11-09
"""
KIND, DAY = sys.argv[1], sys.argv[2]
sys.argv = [sys.argv[0], KIND, DAY, os.devnull]
sys.path.insert(0, str(Path(__file__).parent))
import harness
c = harness.make()
day = date.fromisoformat(DAY); month = DAY[:7]; first = day.replace(day=1)
pos = c.position.at(day)
def r(x):
    try: return f"{x:,.0f}"
    except Exception: return repr(x)
print("== position.at(day)")
for k in ("what_you_own","what_you_owe","net_worth","in_your_accounts","held_for_others","cash_you_own","holdings_value","portfolio_value","free_cash","reserves","bills_due","gameya_still_to_pay","deposits"):
    print(f"  {k:22} {r(getattr(pos,k))}")
print("== position service", [n for n in dir(c.position) if not n.startswith('_')])
for name in ("change_in_net_worth","change_in_what_you_own"):
    for s in (first, first - timedelta(days=1)):
        try: print(f"  {name}({s},{day}) = {r(getattr(c.position,name)(s.isoformat(), day.isoformat()))}")
        except Exception as e:
            try: print(f"  {name}({s},{day}) = {r(getattr(c.position,name)(s, day))}")
            except Exception as e2: print("  ", name, "err", e2)
print("  net_worth at first:", r(c.position.at(first).net_worth), " at last month end:", r(c.position.at(first - timedelta(days=1)).net_worth))
cf = c.reporting.cash_flow(first.isoformat(), day.isoformat())
print("== cash flow", r(cf.inflows), r(cf.outflows), r(cf.net), cf.savings_rate)
sched = c.schedules.view()
plan = c.budgets.plan_summary(month, schedule=sched)
print("== plan_summary", {k: r(v) if not isinstance(v,(list,tuple,dict,str)) else '…' for k, v in plan.items()})
e = c.forecaster.everyday(month, day)
print("== everyday", {k: (r(getattr(e,k)) if not isinstance(getattr(e,k),(list,tuple)) else '…') for k in dir(e) if not k.startswith('_') and not callable(getattr(e,k))})
print("== forecaster", [n for n in dir(c.forecaster) if not n.startswith('_')])
