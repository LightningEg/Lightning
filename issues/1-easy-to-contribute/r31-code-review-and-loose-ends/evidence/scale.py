"""r31: the sample household plus N invented expenses over four years; prints each slow page with its slowest queries.

    python issues/1-easy-to-contribute/r31-code-review-and-loose-ends/evidence/scale.py 4000

Dummy data only."""
import sys, re, tempfile, time, collections, random, datetime
from pathlib import Path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[4]))
from fastapi.testclient import TestClient
from lightning.bootstrap import build
from lightning.ui.web import create_app
from lightning.samples import load_mohab_2026
N = int(sys.argv[1])
PAGES = ("/", "/budget", "/plan", "/plan/reserves", "/investments", "/accounts", "/accounts/1", "/transactions", "/birdview/expenses",
         "/financial-health", "/activity", "/needs-you", "/search?q=a", "/counterparties", "/categories", "/checks")
with tempfile.TemporaryDirectory() as folder:
    c = build(str(Path(folder) / "p.db"), backup_on_start=False); load_mohab_2026(c)
    cats = [r["id"] for r in c.db.all("SELECT id FROM categories WHERE movement='OUTFLOW' AND is_system=0 AND parent_id IS NOT NULL AND active=1 LIMIT 12")] if N else []
    acct = c.db.scalar("SELECT id FROM accounts WHERE account_type='BANK' ORDER BY id LIMIT 1")
    errs=collections.Counter(); import itertools; NAMES=["".join(w) for w in itertools.product(["Zam","Bru","Kli","Opt","Vex","Qua","Dro","Fyn","Gal","Hux","Jor","Myr"],["tek","lon","dax","mir","pho","sul","wen","yat","rig","buz","cov","nel"])]; random.seed(1); t=time.time(); ok=0
    c.transactions.record_inflow if False else None
    if N:
        inc = c.db.scalar("SELECT id FROM categories WHERE movement='INFLOW' AND is_system=0 AND parent_id IS NOT NULL AND active=1 LIMIT 1")
        c.transactions.record_inflow("2022-01-01", acct, "5000000", inc, "seed")
        for i in range(N):
            d = (datetime.date(2022,1,2) + datetime.timedelta(days=i % 1400)).isoformat()
            try: c.transactions.record_outflow(d, acct, str(random.randint(20, 900)), random.choice(cats), "", NAMES[i % len(NAMES)]); ok+=1
            except Exception as e:
                errs[str(e)[:90]] += 1
    print(errs.most_common(3)); print("rows added", ok, round(time.time()-t), "s; total txns", c.db.scalar("SELECT COUNT(*) FROM transactions"))
    spent = collections.Counter(); calls = collections.Counter()
    for name in ("all", "one", "scalar", "execute"):
        o = getattr(c.db, name)
        def counted(sql, *a, _o=o, **k):
            t=time.perf_counter()
            try: return _o(sql, *a, **k)
            finally:
                key=re.sub(r"\s+", " ", str(sql))[:150]; spent[key]+=time.perf_counter()-t; calls[key]+=1
        setattr(c.db, name, counted)
    cl = TestClient(create_app(c), base_url="http://127.0.0.1")
    import cProfile, pstats, io
    for p in ("/", "/transactions", "/needs-you", "/counterparties", "/investments", "/birdview/expenses"):
        cl.get(p); spent.clear(); calls.clear(); t = time.perf_counter(); r = cl.get(p); ms = (time.perf_counter()-t)*1000
        print(f"== {p} {ms:.0f} ms, sql {sum(spent.values())*1000:.0f} ms in {sum(calls.values())} q")
        for k,v in spent.most_common(4): print(f"   {v*1000:6.0f} ms {calls[k]:3}x {k}")
    pr=cProfile.Profile(); pr.enable(); cl.get("/"); pr.disable()
    st=io.StringIO(); pstats.Stats(pr,stream=st).sort_stats("cumulative").print_stats(60)
    print("\n".join(l for l in st.getvalue().splitlines() if "lightning/" in l)[:5000])
