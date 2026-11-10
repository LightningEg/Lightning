"""r31 move-it test: record one expense (or one transfer) of 123 and read the headline figures on PC and phone before
and after: each must move by exactly 123 or not at all.

    python issues/11-phone-ux/r31-figures-one-owner/evidence/moveit.py demo 2026-11-09 expense|transfer
"""
import os, sys, re
from pathlib import Path
KIND, DAY = sys.argv[1], sys.argv[2]
sys.path.insert(0, str(Path(__file__).parent))
_argv = sys.argv; sys.argv = [_argv[0], KIND, DAY, os.devnull]
import harness
c = harness.make()
WATCH = [("pc", "/", "Net worth"), ("pc", "/", "Safe to spend"), ("pc", "/", "Left in plan"), ("pc", "/", "Free cash"), ("pc", "/", "What you own"),
         ("pc", "/budget", "Left in plan"), ("pc", "/plan", "Safe to spend"), ("pc", "/plan", "Free cash"), ("pc", "/accounts", "What you own"),
         ("pc", "/accounts", "In your accounts"), ("pc", "/spending/compare", "Total"), ("pc", "/financial-health", "Net worth"),
         ("phone", "/home", "Safe to spend"), ("phone", "/home", "This month"), ("phone", "/budget/flexible", "Left in plan"), ("phone", "/budget/flexible", "Spent"),
         ("phone", "/money", "Net worth"), ("phone", "/money", "What you own"), ("phone", "/money/accounts", "Total"), ("phone", "/money/report", "Money out"),
         ("phone", "/money/report", "Kept"), ("phone", "/money/report", "Change in what you own"), ("phone", "/activity", "Out"), ("phone", "/plan", "Free cash")]
NUM = re.compile(r"[+-]?\d[\d,]*(?:\.\d+)?")
def read():
    out = {}
    for surface in ("pc", "phone"):
        cl = harness.client(c, surface == "phone")
        cache = {}
        for s, page, label in WATCH:
            if s != surface: continue
            if page not in cache: cache[page] = harness.text_of(cl.get(page).text)
            t = cache[page]; val = None
            for i, tok in enumerate(t):
                if tok == label or tok.startswith(label + " ") and len(tok) < len(label) + 40:
                    for u in ([tok[len(label):]] + t[i + 1:i + 4]):
                        u = re.sub(r"\d{4}-\d\d(-\d\d)?", "", u)
                        if "days left" in u or "until" in u or "by day" in u: continue
                        m = NUM.search(u)
                        if m: val = m.group(0); break
                    if val: break
            out[(s, page, label)] = val
    return out
def num(x): return None if x is None else float(x.replace(",", ""))
before = read()
cat = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
acct = next(a for a in c.accounts.list(active_only=True) if a.name == "CIB Payroll")
what = _argv[3] if len(_argv) > 3 else "expense"
if what == "expense": c.transactions.record_outflow(DAY, acct.id, "123", cat, "audit move-it")
elif what == "transfer":
    other = next(a for a in c.accounts.list(active_only=True) if a.name == "Cash wallet"); c.transactions.record_transfer(DAY, acct.id, other.id, "123")
after = read()
print(f"{KIND} {DAY}: one {what} of 123")
for k in WATCH:
    b, a = before[k], after[k]
    d = None if b is None or a is None else round(num(a) - num(b), 2)
    print(f"  {k[0]:5} {k[1]:18} {k[2]:24} {str(b):>12} -> {str(a):>12}   moved {d}")
