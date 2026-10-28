"""Time every main page and count its database queries, on a profile you choose.

    python tools/perf_check.py              # the sample household (about ten months, 300 rows)
    python tools/perf_check.py --demo       # the small demo household
    python tools/perf_check.py --slow 150   # flag pages slower than 150 ms (default 150) or over 400 queries
    python tools/perf_check.py --phone      # the phone app's pages (phone frame, folds load when opened)

Builds a temporary database (never real data), asks each page twice (the first call is cold, the second is what a
person feels), and prints one line per page: warm milliseconds, queries, and the query asked most often. Exit status 1
when a page is over a limit. Pure Python; no browser.
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PAGES = ("/", "/budget", "/plan", "/plan/recurring", "/plan/loans", "/plan/reserves", "/investments", "/investments/prices",
         "/accounts", "/accounts/1", "/transactions", "/birdview/expenses", "/financial-health", "/categories",
         "/counterparties", "/settings", "/money-from-others", "/checks")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="the small demo household instead of the sample year")
    parser.add_argument("--slow", type=int, default=150, help="milliseconds a warm page may take")
    parser.add_argument("--queries", type=int, default=400, help="queries a page may ask")
    parser.add_argument("--phone", action="store_true", help="render the pages as the phone app does")
    args = parser.parse_args()

    from fastapi.testclient import TestClient

    from lightning.bootstrap import build
    from lightning.ui.web import create_app

    with tempfile.TemporaryDirectory() as folder:
        container = build(str(Path(folder) / "perf.db"), backup_on_start=False)
        if args.demo:
            from lightning.demo import build_demo
            build_demo(container)
        else:
            from lightning.samples import load_mohab_2026
            load_mohab_2026(container)
        counts: collections.Counter = collections.Counter()
        for name in ("all", "one", "scalar", "execute"):
            original = getattr(container.db, name)

            def counted(sql, *a, _original=original, **k):
                counts[re.sub(r"\s+", " ", str(sql))[:90]] += 1
                return _original(sql, *a, **k)
            setattr(container.db, name, counted)
        app = create_app(container)
        if args.phone:  # the phone app's frame and screens (backend roadmap B6: profile phone latency)
            inner = app

            async def app(scope, receive, send):
                if scope["type"] == "http":
                    scope.setdefault("state", {})["phone"] = True
                return await inner(scope, receive, send)
        client = TestClient(app, base_url="http://127.0.0.1")
        worst = 0
        print(f"{'page':26}{'warm ms':>8}{'queries':>9}  most repeated query")
        for page in PAGES:
            client.get(page)
            counts.clear()
            start = time.perf_counter()
            reply = client.get(page)
            ms = (time.perf_counter() - start) * 1000
            total = sum(counts.values())
            top = counts.most_common(1)
            flag = "  <-- slow" if ms > args.slow or total > args.queries else ""
            worst += bool(flag)
            note = f"{top[0][1]}x {top[0][0]}" if top else ""
            print(f"{page:26}{ms:8.0f}{total:9}  {note[:70]}{flag}" + ("" if reply.status_code == 200 else f"  HTTP {reply.status_code}"))
        return 1 if worst else 0


if __name__ == "__main__":
    sys.exit(main())
