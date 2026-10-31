"""Check every item in issues/ and rebuild issues/INDEX.md, the plan: milestones in order, their items under them.

    python tools/issues.py            # rewrite issues/INDEX.md
    python tools/issues.py --check    # exit 1 if an item is malformed or INDEX.md is out of date; warnings never fail
    python tools/issues.py next 3     # the next free code in milestone 3, e.g. 3K
    python tools/issues.py tag 3B     # its full code with the kind tag, e.g. BV-3B

A full code is a kind tag, then the item's code: BV-3B. The tag says what the item is; the code after it never changes.

A milestone is issues/<n>-<name>/ with a README.md (title, done codes, goal). An item is <n><LETTER>-<what>.md in it,
code 3C; a step inside a big item is a `## 3C1 Title` heading. issues/README.md explains the fields.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ISSUES = ROOT / "issues"
TYPES = ("bug", "polish", "feature", "tech", "owner")
STATUSES = ("new", "ready", "building", "blocked")
SEVERITIES = ("high", "medium", "low")  # bugs only: high is wrong money or lost data
# The pillar is what part of the product an item serves. One list for issues, reports, feedback, docs and GitHub
# labels; see docs/README.md. Add one only when no existing pillar fits, and say so in issues/README.md.
PILLARS = {"capture": "Capture", "plan": "Plan", "understand": "Understand", "own": "Own", "protect": "Protect",
           "everywhere": "Everywhere", "feel": "Feel", "build": "Build", "reach": "Reach"}
# Size sets the Lightning Coins on a task for contributors. A large item is split into steps before it is posted.
COINS = {"S": 200, "M": 500, "L": 800}
LOOKS = ("visual", "technical")  # visual: how a screen looks or reads; technical: what the app computes, stores or does
TAGS = {"BV": "bug, visual", "BT": "bug, technical", "IV": "improvement, visual", "IT": "improvement, technical",
        "NF": "new feature", "OW": "owner task"}
DONE = ("done", "fixed", "built", "declined")  # a finished item is deleted and its code listed as done, never kept
REQUIRED = ("title", "type", "pillar", "status", "created", "by")
MILESTONE = re.compile(r"^(\d+)-[a-z0-9]+(-[a-z0-9]+)*$")
ITEM = re.compile(r"^(\d+)([A-Z]+)-[a-z0-9]+(-[a-z0-9]+)*\.md$")
# A step: `## 3C1 Title · M` (size S, M or L, or `owner` for a step only the owner can do), once posted `· #123`.
STEP = re.compile(r"^## (\d+[A-Z]+\d+) (.+?)(?: · (S|M|L|owner))?(?: · #(\d+))?[ \t]*$", re.M)


def front_matter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return data
        key, sep, value = line.partition(":")
        if sep:
            data[key.strip()] = value.strip()
    return {}


def letters(n: int) -> str:
    """1 → A, 26 → Z, 27 → AA."""
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def number(code_letters: str) -> int:
    n = 0
    for ch in code_letters:
        n = n * 26 + ord(ch) - 64
    return n


def tag(meta: dict) -> str:
    """The two-letter kind tag: bug or improvement (polish, tech), visual or technical; NF a feature, OW the owner's."""
    kind, look = meta.get("type"), meta.get("look")
    if kind == "feature":
        return "NF"
    if kind == "owner":
        return "OW"
    if kind == "tech":
        look = "technical"
    elif kind == "polish":
        look = look or "visual"
    return ("B" if kind == "bug" else "I") + ("V" if look == "visual" else "T")


def look_problem(meta: dict) -> str | None:
    kind, look = meta.get("type"), meta.get("look")
    if kind == "bug" and look not in LOOKS:
        return f"a bug says whether it is visual or technical: look: {' or '.join(LOOKS)}"
    if look is not None and (kind not in ("bug", "polish") or look not in LOOKS):
        return f"look is {' or '.join(LOOKS)}, and only on a bug or polish item (tech is always technical)"
    return None


def severity_problem(meta: dict) -> str | None:
    kind, severity = meta.get("type"), meta.get("severity")
    if kind == "bug" and severity not in SEVERITIES:
        return f"a bug says how bad it is: severity: {' or '.join(SEVERITIES)} (high is wrong money or lost data)"
    if severity is not None and kind != "bug":
        return "severity is only on a bug"
    return None


CLAIMED = re.compile(r"^## Claimed\s*$(.*?)(?=^## |\Z)", re.M | re.S)


def warnings(milestones: list[dict], now: Path = ROOT / "NOW.md") -> list[str]:
    """A building item should be claimed in NOW.md; a large one should be split into steps. Only warnings."""
    found = CLAIMED.search(now.read_text(encoding="utf-8")) if now.exists() else None
    claimed = found.group(1) if found else ""
    out = [f"warning: {i['file']} is building, but {i['code']} is not in NOW.md's Claimed table"
           for m in milestones for i in m["items"]
           if i.get("status") == "building" and not re.search(rf"(?<![0-9A-Za-z]){i['code']}(?![0-9A-Za-z])", claimed)]
    return out + [f"warning: {i['file']} is size L with no steps: split it into {i['code']}1, {i['code']}2 … before posting it"
                  for m in milestones for i in m["items"] if i.get("size") == "L" and not i["steps"]]


def load() -> tuple[list[dict], list[str]]:
    milestones, problems = [], []
    for path in sorted(ISSUES.iterdir(), key=lambda p: (int(p.name.split("-")[0]) if MILESTONE.match(p.name) else 999, p.name)):
        if path.is_file():
            if path.name not in ("README.md", "INDEX.md"):
                problems.append(f"issues/{path.name}: items live in a milestone folder")
            continue
        match = MILESTONE.match(path.name)
        if not match:
            problems.append(f"issues/{path.name}/ is not a milestone (<number>-<name>, lower case, hyphens)")
            continue
        n = int(match.group(1))
        meta = front_matter(path / "README.md") if (path / "README.md").exists() else {}
        if not meta.get("title"):
            problems.append(f"issues/{path.name}/README.md needs front matter with a title")
        goal = re.search(r"^\*\*Goal\.\*\* (.+)$", (path / "README.md").read_text(encoding="utf-8"), re.M) if meta else None
        done = [c.strip() for c in meta.get("done", "").split(",") if c.strip()]
        items = []
        for item in sorted(path.glob("*.md"), key=lambda p: (len(p.name.split("-")[0]), p.name)):
            if item.name == "README.md":
                continue
            rel = f"{path.name}/{item.name}"
            found = ITEM.match(item.name)
            if not found:
                problems.append(f"{rel}: name must be <code>-<what>.md, e.g. {n}C-chart-labels-overlap.md")
                continue
            code = found.group(1) + found.group(2)
            if int(found.group(1)) != n:
                problems.append(f"{rel}: code {code} belongs in milestone {found.group(1)}")
            if code in done:
                problems.append(f"{rel}: {code} is listed as done; codes are never reused (python tools/issues.py next {n})")
            meta_i = front_matter(item)
            if not meta_i:
                problems.append(f"{rel}: no front matter block")
                continue
            for key in REQUIRED:
                if not meta_i.get(key):
                    problems.append(f"{rel}: front matter lacks '{key}'")
            if meta_i.get("type") not in TYPES:
                problems.append(f"{rel}: type '{meta_i.get('type')}' is not one of {', '.join(TYPES)}")
            if meta_i.get("pillar") and meta_i["pillar"] not in PILLARS:
                problems.append(f"{rel}: pillar '{meta_i['pillar']}' is not one of {', '.join(PILLARS)} (issues/README.md)")
            if meta_i.get("coins"):
                floor = COINS.get(meta_i.get("size"), 0)
                if not meta_i["coins"].isdigit() or int(meta_i["coins"]) < floor or int(meta_i["coins"]) % 100:
                    problems.append(f"{rel}: coins is a multiple of 100, at least the size's {floor}: it raises the reward, never lowers it")
            if meta_i.get("post") not in (None, "no"):
                problems.append(f"{rel}: post is only ever `no` (keep this item off the public list)")
            if meta_i.get("type") == "owner":
                if meta_i.get("size"):
                    problems.append(f"{rel}: an owner task has no size (no coins)")
            elif meta_i.get("size") not in COINS:
                problems.append(f"{rel}: size must be {', '.join(COINS)} (S small fix, M a few files with tests, L money logic or a feature)")
            if severity_problem(meta_i):
                problems.append(f"{rel}: {severity_problem(meta_i)}")
            if look_problem(meta_i):
                problems.append(f"{rel}: {look_problem(meta_i)}")
            if meta_i.get("status") in DONE:
                problems.append(f"{rel}: status '{meta_i['status']}' means finished: delete this file in the commit that "
                                f"finishes it and add {code} to done: in its milestone README")
            elif meta_i.get("status") not in STATUSES:
                problems.append(f"{rel}: status '{meta_i.get('status')}' is not one of {', '.join(STATUSES)}")
            if meta_i.get("status") == "blocked" and not meta_i.get("blocked_by"):
                problems.append(f"{rel}: a blocked item says what it waits for in 'blocked_by'")
            try:
                date.fromisoformat(meta_i.get("created", ""))
            except ValueError:
                problems.append(f"{rel}: 'created' must be yyyy-mm-dd")
            steps = []
            whole = item.read_text(encoding="utf-8")
            for step, title, size, github in STEP.findall(whole):
                if not step.startswith(code) or not step[len(code):].isdigit():
                    problems.append(f"{rel}: step {step} must be {code}1, {code}2, …")
                if not size:
                    problems.append(f"{rel}: step {step} needs a size: `## {step} {title} · S|M|L|owner`")
                if meta_i.get("type") == "owner" and size and size != "owner":
                    problems.append(f"{rel}: steps of an owner task are `owner`")
                found = re.search(rf"^## {step} .*?\n(.*?)(?=^## |\Z)", whole, re.M | re.S)
                # "Needs 5A1 and 5A2 merged first": the steps named in that sentence must be finished before this one is offered.
                sentence = re.search(r"Needs ([^.]*?) (?:merged|agreed|finished) first", found.group(1) if found else "")
                steps.append({"code": step, "title": title, "size": size, "github": github,
                              "needs": re.findall(r"\d+[A-Z]+\d+", sentence.group(1)) if sentence else []})
            items.append({**meta_i, "code": code, "tag": tag(meta_i), "file": rel, "steps": steps})
        codes = [i["code"] for i in items]
        for code in {c for c in codes if codes.count(c) > 1}:
            problems.append(f"issues/{path.name}/: code {code} is used twice")
        milestones.append({"n": n, "dir": path.name, "title": meta.get("title", path.name),
                           "goal": goal.group(1) if goal else "", "done": done, "items": items})
    numbers = [m["n"] for m in milestones]
    for n in {x for x in numbers if numbers.count(x) > 1}:
        problems.append(f"issues/: milestone number {n} is used twice")
    return milestones, problems


def next_code(milestone: dict) -> str:
    used = [number(re.sub(r"^\d+", "", c)) for c in [i["code"] for i in milestone["items"]] + milestone["done"]]
    return f"{milestone['n']}{letters(max(used, default=0) + 1)}"


def render(milestones: list[dict]) -> str:
    count = sum(len(m["items"]) for m in milestones)
    lines = [
        "# The plan",
        "",
        "Generated by `python tools/issues.py`; do not edit by hand. Read this, then open only the item you need.",
        "Rules: [README.md](README.md). Status: new · ready · building · blocked.",
        "",
        "Each code starts with what the item is: " + " · ".join(f"**{k}** {v}" for k, v in TAGS.items()) + ".",
        "",
        f"{len(milestones)} milestones, {count} open items, in the order they are worked on.",
    ]
    for m in milestones:
        lines += ["", f"## {m['n']} {m['title']}", ""]
        if m["goal"]:
            lines += [m["goal"], ""]
        lines += ["| Code | Item | Kind | Pillar | Size | Status |", "|---|---|---|---|---|---|"]
        for i in m["items"]:
            status = i["status"] + (f" on {i['blocked_by']}" if i.get("blocked_by") else "")
            github = f" ([#{i['github']}](https://github.com/LightningEg/Lightning/issues/{i['github']}))" if i.get("github") else ""
            kind = TAGS[i["tag"]] + (f" · {i['severity']}" if i.get("severity") else "")
            lines.append(f"| **{i['tag']}-{i['code']}** | [{i['title']}]({i['file']}){github} | {kind} | {PILLARS[i['pillar']]} | {i.get('size', '')} | {status} |")
            for s in i["steps"]:
                gh = f" ([#{s['github']}](https://github.com/LightningEg/Lightning/issues/{s['github']}))" if s["github"] else ""
                lines.append(f"| {i['tag']}-{s['code']} | ↳ {s['title']}{gh} | | | {s['size'] or ''} | |")
        done = sorted(m["done"], key=lambda c: number(re.sub(r"^\d+", "", c)))
        lines += ["", f"Done: {', '.join(done) or 'nothing yet'}. Next free code: {next_code(m)}."]
    return "\n".join(lines) + "\n"


REPO = "https://github.com/LightningEg/Lightning"


def coins_for(unit: dict) -> int:
    """The reward: the size's coins, or the item's own higher `coins:` (the owner: raise as you see fit)."""
    item = unit["item"]
    return int(item["coins"]) if item.get("coins") and not unit["step"] else COINS[unit["size"]]


def post_units(milestones: list[dict]) -> tuple[list[dict], list[tuple[str, str]]]:
    """What would go on GitHub for contributors, and what stays off it and why.

    A unit is a step, or an item with no steps. It is posted only if it is ready (understood, unclaimed, not blocked),
    not an owner task, not marked `post: no`, sized, and not already on GitHub. An L item with no steps waits to be split."""
    units, held = [], []
    for m in milestones:
        for i in m["items"]:
            name = f"{i['tag']}-{i['code']}"
            if i.get("post") == "no":
                held.append((name, "marked post: no (sensitive, owner-run or being built by another AI)"))
            elif i["type"] == "owner":
                held.append((name, "owner task"))
            elif i["status"] != "ready":
                held.append((name, f"status {i['status']}"))
            elif i["steps"]:
                for s in i["steps"]:
                    if s["size"] == "owner":
                        held.append((f"{i['tag']}-{s['code']}", "owner step"))
                    elif s["github"]:
                        held.append((f"{i['tag']}-{s['code']}", f"already #{s['github']}"))
                    elif any(n in {x["code"] for x in i["steps"]} for n in s.get("needs", [])):
                        waiting = [n for n in s.get("needs", []) if n in {x["code"] for x in i["steps"]}]
                        held.append((f"{i['tag']}-{s['code']}", f"waits for {', '.join(waiting)} to be finished (its heading deleted)"))
                    else:
                        units.append({"code": f"{i['tag']}-{s['code']}", "title": s["title"], "size": s["size"], "item": i, "step": s})
            elif i.get("github"):
                held.append((name, f"already #{i['github']}"))
            elif i.get("size") == "L":
                held.append((name, "size L with no steps: split it first"))
            else:
                units.append({"code": name, "title": i["title"], "size": i["size"], "item": i, "step": None})
    return units, held


def absolute_links(text: str, item_file: str) -> str:
    """Markdown links in an item are relative to its file; an issue body is not, so point them at GitHub."""
    base = Path("issues") / item_file

    def fix(match):
        target = match.group(2)
        if re.match(r"[a-zA-Z][\w+.-]*:|#|/", target):
            return match.group(0)
        path, _, frag = target.partition("#")
        resolved = Path(os.path.normpath(base.parent / path)).as_posix()
        return f"{match.group(1)}{REPO}/blob/main/{resolved}{'#' + frag if frag else ''})"

    return re.sub(r"(\[[^\]]*\]\()([^)\s]+)\)", fix, text)


def issue_text(unit: dict) -> tuple[str, str, list[str]]:
    """Title, body and labels for one unit, in the shape the existing good-first-issues use."""
    item, step = unit["item"], unit["step"]
    path = ISSUES / item["file"]
    text = path.read_text(encoding="utf-8")
    body = text.split("\n---\n", 1)[-1].strip()
    if step:
        found = re.search(rf"^## {step['code']} .*?\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        what = (found.group(1).strip() if found else "") or step["title"]
        heading = f"What to build ({item['title']})"
    else:
        what = re.sub(r"^## .*$", "", body.split("## Fix")[0], flags=re.M).strip()
        heading = "What's wrong or wanted"
    # A step carries its own what and done-when; the item's plan would repeat every sibling step.
    fix = re.search(r"^## Fix\n(.*?)(?=^## |\Z)", body, re.M | re.S)
    done = "" if step else (fix.group(1).strip() if fix else "")
    coins = coins_for(unit)
    kind = TAGS[item["tag"]].replace(", ", "-").replace(" ", "-")
    link = f"{REPO}/blob/main/issues/{item['file']}"
    title = f"[{unit['code']}] {unit['title'] if step else item['title']}"
    out = [f"### Code\n{unit['code']}", f"### {heading}\n{what[:1800]}"]
    if step:
        report = re.search(r"^## Report\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        lead = (report.group(1).strip().split("\n\n")[0] if report else "")[:700]
        if lead:
            out.append(f"### Context\n{lead}")
    if done:
        out.append(f"### How it was planned\n{done[:1200]}")
    out.append(f"### Read first\n[{item['file']}]({link}) · financial rules in `ai/ARCHITECTURE.md` (figures are computed in Python services, never templates).")
    out.append(f"**Reward:** {coins} Lightning Coins once a pull request that says `Closes #<this issue>` is merged. "
               f"To work on it: comment `/take`. Setup: [CONTRIBUTING.md]({REPO}/blob/main/CONTRIBUTING.md).")
    labels = [f"coins:{coins}", f"pillar:{item['pillar']}", f"kind:{kind}"] + (["good first issue"] if unit["size"] == "S" else [])
    return title, absolute_links("\n\n".join(out), item["file"]), labels


def main() -> int:
    milestones, problems = load()
    if sys.argv[1:2] == ["github"]:
        if problems:
            print("\n".join(problems))
            return 1
        units, held = post_units(milestones)
        sizes = {s: sum(1 for u in units if u["size"] == s) for s in COINS}
        print(f"# Would post {len(units)} issues (dry run: nothing is sent)\n")
        print("Sizes: " + ", ".join(f"{n} {s} ({COINS[s]})" for s, n in sizes.items()) + f" · {sum(coins_for(u) for u in units):,} coins in all\n")
        for u in units:
            print(f"- {issue_text(u)[0]}  · {u['size']} · {coins_for(u)} coins · {PILLARS[u['item']['pillar']]}")
        print(f"\n# Held back ({len(held)})\n")
        for name, why in held:
            print(f"- {name}: {why}")
        return 0
    if sys.argv[1:2] == ["next"]:
        wanted = [m for m in milestones if str(m["n"]) == (sys.argv[2] if len(sys.argv) > 2 else "")]
        if not wanted:
            print("usage: python tools/issues.py next <milestone number>")
            return 1
        print(next_code(wanted[0]))
        return 0
    if sys.argv[1:2] == ["tag"]:
        wanted = [i for m in milestones for i in m["items"] if len(sys.argv) > 2 and i["code"] == sys.argv[2].split("-")[-1]]
        if not wanted:
            print("usage: python tools/issues.py tag <open item code, e.g. 3B>")
            return 1
        print(f"{wanted[0]['tag']}-{wanted[0]['code']}")
        return 0
    text = render(milestones)
    index = ISSUES / "INDEX.md"
    if "--check" in sys.argv:
        if not index.exists() or index.read_text(encoding="utf-8") != text:
            problems.append("issues/INDEX.md is out of date: run python tools/issues.py")
        print("\n".join(warnings(milestones) + problems) or "issues fine")
        return 1 if problems else 0
    if problems:
        print("\n".join(problems))
        return 1
    index.write_text(text, encoding="utf-8")
    print(f"issues/INDEX.md: {len(milestones)} milestones, {sum(len(m['items']) for m in milestones)} items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
