"""r32: fetch every page of the sample household on the PC (or --phone), time it, count its queries and record who links to what.

    python issues/1-easy-to-contribute/r32-code-review-and-loose-ends/evidence/crawl.py out.json [--phone]

Dummy data only (Mohab's sample year in a temporary folder)."""
import sys, re, tempfile, time, collections, json
from pathlib import Path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[4]))
from fastapi.testclient import TestClient
from lightning.bootstrap import build
from lightning.ui.web import create_app
from lightning.samples import load_mohab_2026
phone = "--phone" in sys.argv
with tempfile.TemporaryDirectory() as folder:
    c = build(str(Path(folder) / "p.db"), backup_on_start=False)
    load_mohab_2026(c)
    counts = collections.Counter()
    for name in ("all", "one", "scalar", "execute"):
        o = getattr(c.db, name)
        def counted(sql, *a, _o=o, **k):
            counts[re.sub(r"\s+", " ", str(sql))[:90]] += 1
            return _o(sql, *a, **k)
        setattr(c.db, name, counted)
    app = create_app(c)
    if phone:
        from lightning.ui.phone.router import mount_phone; mount_phone(app)
    routes = []
    def walk(rs, prefix=""):
        for r in rs:
            if hasattr(r, "original_router"):
                o = r.original_router
                walk(o.routes, prefix + (getattr(o, "prefix", "") if not any(getattr(x,"path","").startswith(getattr(o,"prefix","") or "~") for x in o.routes) else ""))
            elif hasattr(r, "routes") and not hasattr(r, "methods"):
                walk(r.routes, prefix + getattr(r, "path", ""))
            elif hasattr(r, "methods"):
                routes.append((prefix + r.path, sorted(r.methods or [])))
    walk(app.routes)
    if phone:
        inner = app
        async def app(scope, receive, send):
            if scope["type"] == "http":
                scope.setdefault("state", {})["phone"] = True
            return await inner(scope, receive, send)
    client = TestClient(app, base_url="http://127.0.0.1", follow_redirects=False)
    gets = sorted({p for p, m in routes if "GET" in m})
    posts = sorted({p for p, m in routes if "POST" in m})
    print("GET", len(gets), "POST", len(posts), file=sys.stderr)
    static = [p for p in gets if "{" not in p]
    seen_links = collections.defaultdict(set); forms = collections.defaultdict(set)
    res = {}
    queue = list(static); done = set(); variants = collections.Counter()
    while queue:
        p = queue.pop(0)
        base=re.sub(r'\d+','N',p.split('?')[0]); variants[base]+=1
        if p in done or variants[base] > 3: continue
        done.add(p)
        if p.startswith(("/static", "/docs", "/openapi", "/redoc")): continue
        try:
            client.get(p); counts.clear(); t = time.perf_counter(); r = client.get(p)
        except Exception as e:
            res[p] = ("EXC " + type(e).__name__, 0, 0, ""); continue
        ms = (time.perf_counter() - t) * 1000
        top = counts.most_common(1)
        res[p] = (r.status_code, round(ms), sum(counts.values()), f"{top[0][1]}x {top[0][0][:60]}" if top else "")
        if "text/html" in r.headers.get("content-type", ""):
            for h in re.findall(r'(?:href|hx-get|data-href|data-url|data-fold-src|src)="(/[^"#]*)', r.text):
                h = h.replace("&amp;", "&")
                seen_links[h.split("?")[0]].add(p)
                if h not in done and not h.startswith("/static") and len(queue) < 5000: queue.append(h)
            for a in re.findall(r'(?:action|formaction|hx-post|data-action)="(/[^"#]*)', r.text):
                forms[a.split("?")[0]].add(p)
        if r.status_code in (301, 302, 303, 307):
            loc = r.headers.get("location", "")
            if loc.startswith("/"): seen_links[loc.split("?")[0]].add(p + " (redirect)")
    def pat(p): return re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", p) + "/?$")
    out = {"gets": gets, "posts": posts, "res": res,
           "unlinked_get": [p for p in gets if not p.startswith(("/static","/docs","/openapi","/redoc")) and not any(pat(p).match(l) and (srcs - {p}) for l, srcs in seen_links.items())],
           "unposted": [p for p in posts if not any(pat(p).match(l) for l in forms)]}
    out["links"]={k:sorted(v)[:40] for k,v in seen_links.items()}; out["forms"]={k:sorted(v)[:10] for k,v in forms.items()}
    json.dump(out, open(sys.argv[1], "w"), indent=1)
