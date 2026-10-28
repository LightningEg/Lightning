"""Check every item in issues/ and rebuild issues/INDEX.md, the plan: milestones in order, their items under them.

    python tools/issues.py            # rewrite issues/INDEX.md
    python tools/issues.py --check    # exit 1 if an item is malformed or INDEX.md is out of date
    python tools/issues.py next 3     # the next free code in milestone 3, e.g. 3K
    python tools/issues.py tag 3B     # its full code with the kind tag, e.g. BV-3B

A full code is a kind tag, then the item's code: BV-3B. The tag says what the item is; the code after it never changes.

A milestone is issues/<n>-<name>/ with a README.md (title, done codes, goal). An item is <n><LETTER>-<what>.md in it,
code 3C; a step inside a big item is a `## 3C1 Title` heading. issues/README.md explains the fields.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ISSUES = ROOT / "issues"
TYPES = ("bug", "polish", "feature", "tech", "owner")
STATUSES = ("new", "ready", "building", "blocked")
LOOKS = ("visual", "technical")  # visual: how a screen looks or reads; technical: what the app computes, stores or does
TAGS = {"BV": "bug, visual", "BT": "bug, technical", "IV": "improvement, visual", "IT": "improvement, technical",
        "NF": "new feature", "OW": "owner task"}
DONE = ("done", "fixed", "built", "declined")  # a finished item is deleted and its code listed as done, never kept
REQUIRED = ("title", "type", "area", "status", "created", "by")
MILESTONE = re.compile(r"^(\d+)-[a-z0-9]+(-[a-z0-9]+)*$")
ITEM = re.compile(r"^(\d+)([A-Z]+)-[a-z0-9]+(-[a-z0-9]+)*\.md$")
STEP = re.compile(r"^## (\d+[A-Z]+\d+) (.+)$", re.M)


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
            for step, title in STEP.findall(item.read_text(encoding="utf-8")):
                if not step.startswith(code) or not step[len(code):].isdigit():
                    problems.append(f"{rel}: step {step} must be {code}1, {code}2, …")
                steps.append((step, title))
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
        lines += ["| Code | Item | Kind | Area | Status |", "|---|---|---|---|---|"]
        for i in m["items"]:
            status = i["status"] + (f" on {i['blocked_by']}" if i.get("blocked_by") else "")
            github = f" ([#{i['github']}](https://github.com/LightningEg/Lightning/issues/{i['github']}))" if i.get("github") else ""
            lines.append(f"| **{i['tag']}-{i['code']}** | [{i['title']}]({i['file']}){github} | {TAGS[i['tag']]} | {i['area']} | {status} |")
            for step, title in i["steps"]:
                lines.append(f"| {i['tag']}-{step} | ↳ {title} | | | |")
        lines += ["", f"Done: {', '.join(m['done']) or 'nothing yet'}. Next free code: {next_code(m)}."]
    return "\n".join(lines) + "\n"


def main() -> int:
    milestones, problems = load()
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
        print("\n".join(problems) or "issues fine")
        return 1 if problems else 0
    if problems:
        print("\n".join(problems))
        return 1
    index.write_text(text, encoding="utf-8")
    print(f"issues/INDEX.md: {len(milestones)} milestones, {sum(len(m['items']) for m in milestones)} items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
