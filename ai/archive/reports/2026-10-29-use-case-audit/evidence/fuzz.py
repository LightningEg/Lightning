"""Use-case audit 2026-10-29: random money writes on a dummy profile; after each one that saves, every integrity
check must pass and every transfer must net to zero, at year end and at a random month end.

Run from the repo root: python reports/2026-10-29-use-case-audit/evidence/fuzz.py 0 30   (seeds 0 to 29)
"""
import os, random, sys, tempfile
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
os.environ.setdefault("LIGHTNING_TODAY", "2026-12-31")
os.environ["LIGHTNING_PRICES_OFFLINE"] = "1"
from lightning.bootstrap import build  # noqa: E402
from lightning.core.errors import LightningError  # noqa: E402

FINDINGS = []


def new():
    return build(Path(tempfile.mkdtemp()) / "dummy.db")


def invariants(c, label, day):
    bad = [f"transfer {r[0]} nets {r[1]}" for r in c.db.all(
        "SELECT transaction_id, SUM(amount_base_e6) s FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id "
        "WHERE effect='INTERNAL' AND t.status='POSTED' GROUP BY transaction_id HAVING s<>0")]
    bad += [f"{x.name}: {x.actual} vs {x.expected}" for x in c.integrity.checks(day) if x.status == "ISSUE"]
    if bad:
        FINDINGS.append((label, bad))
        print("  INVARIANT", label, bad)


def report():
    print("findings:", FINDINGS or "none")


def run(seed, steps=250):
    rnd = random.Random(seed)
    c = new(); T = c.transactions; I = c.investments
    cats = [c.categories.get_by_code(x).id for x in ("EXP.PERSONAL.FOOD", "EXP.WORK.SOFTWARE")]
    sal = c.categories.get_by_code("EXP.WORK.SALARY").id
    F = c.account_flows
    accts = [F.open_account("CIB", "BANK", "2026-01-01", "20000"), F.open_account("Wallet", "CASH", "2026-01-01", "1000"),
             F.open_account("THNDR", "BROKERAGE", "2026-01-01", "5000")]
    c.currencies.register("USD"); c.fx.save("USD", "2026-01-01", "50"); c.fx.save("USD", "2026-06-01", "48")
    usd = F.open_account("USD", "BANK", "2026-01-01", "100", currency="USD")
    cash_accts = accts[:2] + [usd]
    stock = c.assets.create_investment("COMI", "STOCK", "COMI")
    for m in range(1, 13):
        c.assets.set_price(stock.id, f"2026-{m:02d}-28", str(70 + m))
    dad = c.counterparties.ensure_person("Dad")
    txns = []
    def day(): return f"2026-{rnd.randint(1,12):02d}-{rnd.randint(1,28):02d}"
    def amt(): return rnd.choice(["1", "10.50", "99.99", "250", "1000", "5000", "12000", str(rnd.randint(1, 20000))])
    ops = 0
    for step in range(steps):
        op = rnd.choice(["in", "out", "out", "trf", "edit", "void", "restore", "buy", "sell", "custody", "cnv", "split", "div", "delete", "owner"])
        a = rnd.choice(cash_accts); b = rnd.choice(accts)
        try:
            if op == "in": txns.append(T.record_inflow(day(), a.id, amt(), sal).id)
            elif op == "out": txns.append(T.record_outflow(day(), a.id, amt(), rnd.choice(cats)).id)
            elif op == "trf" and a.currency == b.currency and a.id != b.id: txns.append(T.record_transfer(day(), a.id, b.id, amt()).id)
            elif op == "edit" and txns:
                t = T.get(rnd.choice(txns))
                if t.type.value in ("IN", "OUT") and len(t.lines) == 1:
                    ln = t.lines[0]
                    T.update_money(t.id, rnd.choice([t.date, day()]), ln.account_id, rnd.choice([amt(), str(abs(ln.quantity))]), ln.category_id)
                elif t.type.value == "TRF" and len(t.lines) == 2 and all(c.assets.get_asset(l.asset_id).is_cash for l in t.lines):
                    src = next(l for l in t.lines if l.quantity < 0); dst = next(l for l in t.lines if l.quantity > 0)
                    T.update_transfer(t.id, day(), src.account_id, dst.account_id, amt())
                else: continue
            elif op == "void" and txns: T.void(rnd.choice(txns))
            elif op == "restore" and txns: T.restore(rnd.choice(txns))
            elif op == "delete" and txns: T.delete_many(rnd.sample(txns, min(len(txns), rnd.randint(1, 3))))
            elif op == "buy": txns.append(I.buy(day(), accts[2].id, stock.id, str(rnd.randint(1, 50)), str(rnd.randint(60, 90)), rnd.choice(["0", "5"])).id)
            elif op == "sell": txns.append(I.sell(day(), accts[2].id, stock.id, str(rnd.randint(1, 30)), str(rnd.randint(60, 95))).id)
            elif op == "div": txns.append(I.dividend(day(), accts[2].id, stock.id, str(rnd.randint(1, 300))).id)
            elif op == "custody": c.money_from_others.record(day(), "Dad", rnd.choice(accts[:2]).id, D(rnd.choice(["100", "-100", "500", "-50"])))
            elif op == "owner": txns.append(T.record_expense_paid_by_person(day(), rnd.choice(accts[:2]).id, amt(), dad, rnd.choice(cats)).id)
            elif op == "cnv": txns.append(T.record_conversion(day(), accts[0].id, usd.id, str(rnd.randint(50, 2000)), str(rnd.randint(1, 40))).id)
            elif op == "split" and txns:
                t = T.get(rnd.choice(txns))
                if t.type.value == "OUT" and len(t.lines) == 1:
                    q = abs(t.lines[0].quantity); part = (q / 2).quantize(D("0.01"))
                    T.update_expense_split(t.id, [(cats[0], str(part)), (cats[1], str(q - part))])
                else: continue
            else: continue
        except LightningError:
            continue
        except Exception as e:
            print(f"seed {seed} step {step} op {op}: CRASH {type(e).__name__}: {e}")
            FINDINGS.append((f"seed{seed}/{step}/{op}", [repr(e)]))
            continue
        ops += 1
        before = len(FINDINGS)
        for d in ("2026-12-31", f"2026-{rnd.randint(1,12):02d}-28"):
            invariants(c, f"seed{seed} step{step} op{op} as-of {d}", d)
        if len(FINDINGS) > before:
            return ops
    return ops

for seed in range(int(sys.argv[1]), int(sys.argv[2])):
    n = run(seed)
    print("seed", seed, "ok ops", n, flush=True)
report()
