"""r32: prove the narrower investment-report query returns the same report as today's, and time both.

    python issues/1-easy-to-contribute/r32-code-review-and-loose-ends/evidence/investment_query.py

Dummy data only."""
import sys, tempfile, time, itertools, random, datetime
from pathlib import Path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[4]))
from lightning.bootstrap import build
from lightning.samples import load_mohab_2026
from lightning.demo import build_demo
import lightning.investments.report as R
OLD = "WHERE t.status='POSTED' AND t.type<>'VAL' AND le.owner_id IS NULL AND le.date<=? "
def patched(db_all, ids):
    marks = ",".join(str(int(i)) for i in sorted(ids)) or "NULL"
    def all_(sql, params=()):
        if OLD in sql and "dividend_asset_id" in sql and "le.*" in sql:
            sql = sql.replace(OLD, OLD + f"AND le.transaction_id IN (SELECT x.transaction_id FROM ledger_entries x JOIN financial_assets fa ON fa.id=x.asset_id WHERE fa.is_cash=0 OR x.account_id IN ({marks})) ")
        return db_all(sql, params)
    return all_
for loader, big in ((load_mohab_2026, 0), (build_demo, 0), (load_mohab_2026, 4000)):
    with tempfile.TemporaryDirectory() as f:
        c = build(str(Path(f) / "p.db"), backup_on_start=False); loader(c)
        if big:
            NAMES=["".join(w) for w in itertools.product(["Zam","Bru","Kli","Opt","Vex","Qua","Dro","Fyn","Gal","Hux","Jor","Myr"],["tek","lon","dax","mir","pho","sul","wen","yat","rig","buz","cov","nel"])]
            cats=[r["id"] for r in c.db.all("SELECT id FROM categories WHERE movement='OUTFLOW' AND is_system=0 AND parent_id IS NOT NULL AND active=1 LIMIT 12")]
            acct=c.db.scalar("SELECT id FROM accounts WHERE account_type='BANK' ORDER BY id LIMIT 1"); inc=c.db.scalar("SELECT id FROM categories WHERE movement='INFLOW' AND is_system=0 AND parent_id IS NOT NULL AND active=1 LIMIT 1")
            c.transactions.record_inflow("2022-01-01", acct, "5000000", inc, "seed"); random.seed(1)
            for i in range(big): c.transactions.record_outflow((datetime.date(2022,1,2)+datetime.timedelta(days=i%1400)).isoformat(), acct, str(random.randint(20,900)), random.choice(cats), "", NAMES[i%len(NAMES)])
        from lightning.accounts.domain import AccountType
        accts = c.accounts.list(active_only=False)
        ids = {a.id for a in accts if a.account_type in R.INVESTMENT_ACCOUNT_TYPES or a.account_type in (AccountType.DEPOSIT, AccountType.GAMEYA)}
        periods = [("2026-01-01","2026-10-31"),("2026-03-01","2026-03-31"),("2020-01-01","2026-11-09"),("2026-06-15","2026-08-02"),("2025-01-01","2025-12-31")]
        orig = c.db.all; same = True; t0=t1=0
        for s, e in periods:
            t=time.perf_counter(); a = R.investment_period(c.db, c.accounts, c.assets, c.reporting, s, e); t0+=time.perf_counter()-t
            c.db.all = patched(orig, ids)
            t=time.perf_counter(); b = R.investment_period(c.db, c.accounts, c.assets, c.reporting, s, e); t1+=time.perf_counter()-t
            c.db.all = orig
            if repr(a) != repr(b): same = False; print("  DIFF", s, e, [k for k in a if repr(a[k]) != repr(b.get(k))])
        print(loader.__name__, "extra", big, "identical:", same, f"before {t0*1000/len(periods):.0f} ms after {t1*1000/len(periods):.0f} ms per period; rows", c.db.scalar("SELECT COUNT(*) FROM ledger_entries"))
