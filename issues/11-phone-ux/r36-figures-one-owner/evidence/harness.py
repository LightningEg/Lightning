"""r31 figures harness: one household (demo or Mohab's sample year) on one pinned day, rendered by the PC app and
by the phone app over the same database; writes each page's text tokens and prints every registry label that shows
more than one value. Dummy data in a temporary folder.

    python issues/11-phone-ux/r31-figures-one-owner/evidence/harness.py demo 2026-11-09 OUT.json ["Label one,Label two"]
    python issues/11-phone-ux/r31-figures-one-owner/evidence/ctx.py OUT.json "Left in plan|Net worth"   # what follows a label
Most differences are two periods or a row under a heading: read the context before calling one a fault.
"""
import os, sys, re, json, html, tempfile
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
KIND, DAY, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.environ.update(LIGHTNING_TODAY=DAY, LIGHTNING_PRICES_OFFLINE="1"); sys.path.insert(0, str(REPO))
from fastapi.testclient import TestClient
from lightning.bootstrap import build
from lightning.ui.web import create_app
from lightning.core import figures

def make():
    tmp = tempfile.mkdtemp()
    c = build(Path(tmp) / "audit.db")
    if KIND == "demo":
        from lightning.demo import build_demo; build_demo(c)
    else:
        from lightning.samples import load_mohab_2026; load_mohab_2026(c)
    try:
        from lightning.workflows.profile_open import open_profile_tasks
        for _ in open_profile_tasks(c, wait=True): pass
    except Exception as e: print("open tasks:", e)
    return c

def client(c, phone):
    app = create_app(c)
    if phone:
        from lightning.ui.phone.router import mount_phone
        mount_phone(app)
        inner = app
        async def phone_app(scope, receive, send):
            if scope["type"] == "http": scope.setdefault("state", {})["phone"] = True
            await inner(scope, receive, send)
        app = phone_app
    return TestClient(app, follow_redirects=True)

PC = ["/", "/birdview/expenses", "/spending/compare", "/reports", "/budget", "/payday", "/plan", "/plan/recurring", "/plan/loans", "/plan/reserves",
      "/financial-health", "/investments", "/investments/planner", "/accounts/currencies", "/transactions", "/accounts", "/money-from-others", "/zakat", "/review"]
PHONE = ["/home", "/budget/flexible", "/budget", "/activity", "/money", "/money/accounts", "/money/bills", "/money/report", "/plan", "/plan/loans", "/plan/recurring",
         "/plan/reserves", "/financial-health", "/investments", "/accounts", "/zakat", "/payday", "/", "/money-from-others", "/review", "/birdview/expenses"]

def text_of(body):
    body = re.sub(r"<(script|style|template)\b.*?</\1>", " ", body, flags=re.S)
    m = re.search(r"<main\b.*?</main>", body, re.S)
    main = m.group(0) if m else body
    main = re.sub(r"<[^>]+>", " | ", main)
    main = html.unescape(main).replace("−", "-").replace("⁦", "").replace("⁩", "").replace("‭", "").replace("‬", "")
    toks = [t.strip() for t in main.split("|")]
    return [t for t in toks if t]

NUM = re.compile(r"^[+-]?\d[\d,]*(\.\d+)?\s*%?$")
def figures_on(tokens, labels):
    found = []
    for i, t in enumerate(tokens):
        key = t.rstrip(":").strip()
        if key in labels:
            for u in tokens[i + 1:i + 5]:
                u2 = u.replace("EGP", "").strip()
                if NUM.match(u2): found.append((key, u2)); break
                m = re.match(r"^([+-]?\d[\d,]*(?:\.\d+)?)\b", u2)
                if m and len(u2) < 60: found.append((key, m.group(1) + " …" + u2[len(m.group(1)):][:40])); break
    return found

if __name__ == "__main__":
    c = make()
    labels = {f[1] for f in figures._TABLE} | {"Total", "Spent", "Planned", "Kept", "Left", "Due now", "Everyday spending", "Still to pay", "Lowest point ahead", "Foreign money"}
    out = {"kind": KIND, "day": DAY, "pages": {}}
    for surface, pages in (("pc", PC), ("phone", PHONE)):
        cl = client(c, surface == "phone")
        for p in pages:
            r = cl.get(p)
            toks = text_of(r.text)
            out["pages"][f"{surface}:{p}"] = {"status": r.status_code, "final": str(r.url.path), "figures": figures_on(toks, labels), "tokens": toks[:900]}
    json.dump(out, open(OUT, "w"), indent=0, ensure_ascii=False)
    by = {}
    for page, d in out["pages"].items():
        for k, v in d["figures"]: by.setdefault(k, {}).setdefault(v, []).append(page)
    for k in sorted(by):
        if len(by[k]) > 1 and (len(sys.argv) < 5 or k in sys.argv[4].split(",")):
            print(f"\n{k}:")
            for v, pages in by[k].items(): print(f"   {v:<28} {', '.join(sorted(set(pages)))}")
    print("\nstatus!=200:", [(p, d["status"]) for p, d in out["pages"].items() if d["status"] != 200])
