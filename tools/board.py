"""The board: what is open, who can take it, what blocks what. Read from GitHub; nothing is stored in the repo.

    python tools/board.py              the tally: shipped, running, ready, needs a person, blocked
    python tools/board.py --next       the issues to start now, with the model for each (at most --cap, default 2)
    python tools/board.py --html FILE  the roadmap page
    python tools/board.py --json       everything, for another tool

State is worked out, never typed: an issue is *running* when an open pull request says `Closes #n` or it has an
assignee; *blocked* when a GitHub "blocked by" issue is open, or its `Blocked by:` line names an open pull request or
something outside the repo; *held* when a running issue touches the same `Area:`; *for a person* when it is
`can:owner` or `can:human`; otherwise *ready*. A sub-issue takes `when:`, `can:` and `Area:` from its parent unless its
own body says `Can:` or `Area:`. Rules for taking an issue: skills/dispatch/SKILL.md. Needs the `gh` CLI.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

REPO = "LightningEg/Lightning"
URL = f"https://github.com/{REPO}"
CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.I)
GENERIC_AREAS = {"tests", "none", "see item file", "ai", "docs", "tools"}
ORDER = {"launch": 0, "after-launch": 1, "someday": 2, "unsorted": 3}
PEOPLE = {"owner", "human"}


def gh(path: str):
    out = subprocess.run(["gh", "api", f"repos/{REPO}/{path}"], capture_output=True, text=True)
    if out.returncode:
        sys.exit(f"gh api {path} failed: {out.stderr.strip()[:300]}")
    return json.loads(out.stdout)


def pages(path: str) -> list:
    rows, page = [], 1
    while True:
        got = gh(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        rows += got
        if len(got) < 100:
            return rows
        page += 1


def fetch() -> dict:
    """Everything the board needs, as plain data (also what the tests feed in)."""
    raw = [i for i in pages("issues?state=open") if "pull_request" not in i]
    issues = []
    for i in raw:
        n = i["number"]
        kids = [k["number"] for k in gh(f"issues/{n}/sub_issues?per_page=100") if k["state"] == "open"] \
            if (i.get("sub_issues_summary") or {}).get("total") else []
        blockers = [b["number"] for b in gh(f"issues/{n}/dependencies/blocked_by") if b["state"] == "open"] \
            if (i.get("issue_dependencies_summary") or {}).get("blocked_by") else []
        issues.append({"n": n, "title": i["title"], "body": i.get("body") or "",
                       "labels": [x["name"] for x in i["labels"]], "assignees": [a["login"] for a in i["assignees"]],
                       "children": kids, "blocked_by": blockers,
                       "blocking": (i.get("issue_dependencies_summary") or {}).get("blocking", 0)})
    prs = [{"n": p["number"], "title": p["title"], "body": p.get("body") or "", "branch": p["head"]["ref"],
            "draft": p["draft"], "updated": p["updated_at"]} for p in pages("pulls?state=open")]
    merged = [{"n": p["number"], "title": p["title"], "merged": p["merged_at"]}
              for p in gh("pulls?state=closed&sort=updated&direction=desc&per_page=40") if p.get("merged_at")]
    return {"issues": issues, "prs": prs, "merged": merged, "now": datetime.now(timezone.utc).isoformat()}


def _label(labels: list[str], key: str) -> str | None:
    return next((x.split(":", 1)[1] for x in labels if x.startswith(key + ":")), None)


def _line(body: str, key: str) -> str | None:
    m = re.search(rf"^{key}:[ \t]*(.+)$", body, re.M | re.I)
    return m.group(1).strip() if m else None


def _areas(text: str | None) -> set[str]:
    return {a.strip().strip("`").rstrip("/") for a in (text or "").split(",")} - GENERIC_AREAS - {""}


def _overlap(a: set[str], b: set[str]) -> bool:
    return any(x == y or x.startswith(y + "/") or y.startswith(x + "/") for x in a for y in b)


def derive(data: dict) -> list[dict]:
    """One row per open issue with its worked-out state. Pure: no network."""
    by_n = {i["n"]: dict(i) for i in data["issues"]}
    parent = {k: i["n"] for i in data["issues"] for k in i["children"]}
    open_prs = {p["n"]: p for p in data["prs"]}
    linked: dict[int, list[dict]] = {}
    for p in data["prs"]:
        for n in {int(x) for x in CLOSES.findall(p["body"])}:
            linked.setdefault(n, []).append(p)
    now = datetime.fromisoformat(data["now"])
    rows = []
    for n, i in by_n.items():
        up = by_n.get(parent.get(n), {})
        i["parent"] = parent.get(n)
        i["when"] = _label(i["labels"], "when") or _label(up.get("labels", []), "when") or "unsorted"
        i["can"] = (_line(i["body"], "Can") or _label(i["labels"], "can") or _label(up.get("labels", []), "can")
                    or "any-ai").lower()
        i["areas"] = _areas(_line(i["body"], "Area")) or _areas(_line(up.get("body", ""), "Area"))
        i["prs"] = linked.get(n, [])
        said = _line(i["body"], "Blocked by") or ""
        why = [f"#{b}" for b in i["blocked_by"] + [b for b in up.get("blocked_by", []) if b not in i["blocked_by"]]]
        why += [f"PR #{p}" for p in map(int, re.findall(r"PR #(\d+)", said)) if p in open_prs]
        outside = re.sub(r"(PR )?#\d+( \([^)]*\))?", "", said).strip(" ,;.").lower()
        if outside and not outside.startswith("none") and not re.fullmatch(r"(and|for|the|,|\s)*", outside) \
                and not re.search(r"#\d+", said):
            why.append(said)
        i["why"] = why
        rows.append(i)
    for i in rows:
        stale = i["prs"] and all(now - datetime.fromisoformat(p["updated"].replace("Z", "+00:00")) > timedelta(hours=48)
                                 for p in i["prs"])
        if i["children"]:
            i["state"] = "group"
        elif i["prs"] or i["assignees"]:
            i["state"] = "stale" if stale else "running"
        elif i["why"]:
            i["state"] = "blocked"
        elif i["can"] in PEOPLE:
            i["state"] = "person"
        else:
            i["state"] = "ready"
    busy = [i for i in rows if i["state"] in ("running", "stale")]
    for i in rows:
        if i["state"] == "ready":
            clash = [b["n"] for b in busy if _overlap(i["areas"], b["areas"])]
            if clash:
                i["state"], i["why"] = "held", [f"same area as #{c}" for c in clash]
    return sorted(rows, key=lambda i: (ORDER.get(i["when"], 3), -i["blocking"], i["n"]))


def pick(rows: list[dict], cap: int) -> list[dict]:
    """What to start now: launch work that is ready, most-unblocking first, never two in one area."""
    room = cap - sum(i["state"] == "running" and i["can"] not in PEOPLE for i in rows)
    chosen: list[dict] = []
    for i in rows:
        if len(chosen) >= room:
            break
        if i["state"] == "ready" and i["when"] == "launch" and not any(_overlap(i["areas"], c["areas"]) for c in chosen):
            chosen.append(i)
    return chosen


def _short(i: dict) -> str:
    return f"#{i['n']} {i['title'][:78]}"


def tally(data: dict, rows: list[dict], cap: int) -> str:
    since = datetime.fromisoformat(data["now"]) - timedelta(hours=24)
    shipped = [p for p in data["merged"] if datetime.fromisoformat(p["merged"].replace("Z", "+00:00")) > since]
    out = [f"Board {data['now'][:16]}Z: {sum(i['when'] == 'launch' and i['state'] != 'group' for i in rows)} launch "
           f"issues open, {len(rows)} in all.", "", f"Shipped in the last 24 hours ({len(shipped)}):"]
    out += [f"  PR #{p['n']} {p['title'][:80]}" for p in shipped[:8]] or ["  nothing"]
    if len(shipped) > 8:
        out.append(f"  and {len(shipped) - 8} more")

    def block(title: str, pred, extra=lambda i: ""):
        got = [i for i in rows if pred(i)]
        out.extend(["", f"{title} ({len(got)}):"] + ([f"  {_short(i)}{extra(i)}" for i in got] or ["  nothing"]))

    block("Running", lambda i: i["state"] == "running",
          lambda i: "  <- " + ", ".join(f"PR #{p['n']} ({p['branch']})" for p in i["prs"]) + " ".join(i["assignees"]))
    block("Stale claims, no activity for 48 hours", lambda i: i["state"] == "stale")
    out += ["", f"Start now (cap {cap}):"] + ([f"  {_short(i)}  [{i['can']}]" for i in pick(rows, cap)] or ["  nothing"])
    block("Ready, launch", lambda i: i["state"] == "ready" and i["when"] == "launch", lambda i: f"  [{i['can']}]")
    block("Needs a person", lambda i: i["state"] == "person" and i["when"] == "launch", lambda i: f"  [{i['can']}]")
    block("Blocked or held, launch", lambda i: i["state"] in ("blocked", "held") and i["when"] == "launch",
          lambda i: "  <- " + "; ".join(i["why"])[:90])
    later = [i for i in rows if i["when"] != "launch" and i["state"] != "group"]
    out += ["", f"Not for launch: {sum(i['when'] == 'after-launch' for i in later)} after launch, "
                f"{sum(i['when'] == 'someday' for i in later)} someday, {sum(i['when'] == 'unsorted' for i in later)} unsorted."]
    return "\n".join(out)


PAGE = """<title>Lightning Roadmap</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
:root{--bg:#f6f7f5;--surface:#fff;--ink:#14231c;--mute:#5d6b64;--line:#dfe4e0;--green:#0b8a5f;--amber:#b26a00;--red:#b3261e;--blue:#1f5fbf;--chip:#eef1ee}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0f1713;--surface:#17211b;--ink:#e8efe9;--mute:#9aa9a0;--line:#2a3830;--green:#47c796;--amber:#e3a140;--red:#ff8a80;--blue:#7fb0ff;--chip:#1f2c25;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0f1713;--surface:#17211b;--ink:#e8efe9;--mute:#9aa9a0;--line:#2a3830;--green:#47c796;--amber:#e3a140;--red:#ff8a80;--blue:#7fb0ff;--chip:#1f2c25;color-scheme:dark}
body{background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,sans-serif;padding-block:24px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
main{max-width:1180px;margin:0 auto}h1{font-size:26px;margin:0 0 4px}.sub{color:var(--mute);margin:0 0 18px}
.lanes{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;align-items:start}
@media(max-width:900px){.lanes{grid-template-columns:minmax(0,1fr)}}
h2{font-size:16px;margin:0 0 10px}h2 small{color:var(--mute);font-weight:500;margin-left:8px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:0 0 8px;min-width:0}
.card.kid{margin-left:16px}.card a{color:var(--ink);font-weight:500;text-decoration:none;overflow-wrap:anywhere}
.meta{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}.pill{border-radius:999px;padding:1px 9px;font-size:12px;background:var(--chip);color:var(--mute)}
.ready{color:var(--green)}.running{color:var(--blue)}.blocked,.held,.stale{color:var(--red)}.person{color:var(--amber)}
.why{font-size:12px;color:var(--red);margin-top:5px}
</style><main><h1>Lightning Roadmap</h1><p class="sub">__SUB__</p><div class="lanes">__LANES__</div></main>"""


def page(data: dict, rows: list[dict]) -> str:
    e = html.escape
    lanes = []
    for key, name in (("launch", "Launch"), ("after-launch", "After launch"), ("someday", "Someday")):
        mine = [i for i in rows if i["when"] == key]
        tops = [i for i in mine if not i["parent"] or i["parent"] not in {m["n"] for m in mine}]
        cards = []
        for top in tops:
            for i, kid in [(top, False)] + [(k, True) for k in mine if k["parent"] == top["n"]]:
                why = f'<div class="why">{e("; ".join(i["why"]))}</div>' if i["why"] and i["state"] != "group" else ""
                state = f'{len(i["children"])} open steps' if i["state"] == "group" else i["state"]
                cards.append(f'<div class="card{" kid" if kid else ""}"><a href="{URL}/issues/{i["n"]}" target="_blank" '
                             f'rel="noopener">{e(i["title"])}</a><div class="meta"><span class="pill">#{i["n"]}</span>'
                             f'<span class="pill">{e(i["can"])}</span><span class="pill {i["state"]}">{state}</span>'
                             f'</div>{why}</div>')
        lanes.append(f'<section><h2>{name}<small>{sum(i["state"] != "group" for i in mine)} open</small></h2>'
                     f'{"".join(cards)}</section>')
    sub = f"From GitHub at {data['now'][:16]}Z. Red is blocked, held or stale; amber needs a person."
    return PAGE.replace("__SUB__", sub).replace("__LANES__", "".join(lanes))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--cap", type=int, default=2)
    ap.add_argument("--html")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--from", dest="source", help="read saved --json data instead of GitHub")
    args = ap.parse_args(argv)
    if args.source:
        with open(args.source, encoding="utf-8") as f:
            data = json.load(f)["data"]
    else:
        data = fetch()
    rows = derive(data)
    if args.json:
        print(json.dumps({"data": data, "rows": rows}, default=sorted))
    elif args.html:
        with open(args.html, "w", encoding="utf-8") as f:
            f.write(page(data, rows))
        print(f"Wrote {args.html}")
    elif args.next:
        for i in pick(rows, args.cap):
            print(f"{i['n']}\t{i['can']}\t{i['title']}")
    else:
        print(tally(data, rows, args.cap))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
