"""List the rules in a stylesheet that nothing in lightning/ can reach (IT-9F1).

    python tools/css_unused.py                       # lightning/ui/static/style.css
    python tools/css_unused.py --file other.css [--json]

A class token is *seen* when it occurs as a whole word in any .html, .js or .py file under lightning/. A token
built at run time ("tone-" + x, f"is-{state}", `chip-${k}`) is *dynamic*: its prefix up to a "-" appears before a
quote, "{", "$" or "+", and it counts as seen. A selector is dead when one of its class tokens is not seen; a rule is
dead when every selector in it is. No browser: hover, focus and themes are not guessed, a class is judged by its name.
Exit status is always 0."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "lightning" / "ui" / "static" / "style.css"
SKIP_AT = ("@font-face", "@keyframes", "@-webkit-keyframes", "@charset", "@import")
CLASS = re.compile(r"\.(-?[A-Za-z_][\w-]*)")


def corpus(root: Path) -> str:
    parts = []
    for suffix in ("*.html", "*.js", "*.py"):
        for path in sorted(root.rglob(suffix)):
            try:
                parts.append(path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    return "\n".join(parts)


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), css, flags=re.S)


def rules(css: str) -> list[tuple[int, str, int]]:
    """(line, selector text, bytes) of each top-level or @media/@supports rule, skipping at-rules with no classes."""
    text = _strip_comments(css)
    found: list[tuple[int, str, int]] = []

    def walk(start: int, end: int) -> None:
        i = start
        while i < end:
            while i < end and text[i].isspace():
                i += 1
            if i >= end:
                return
            head_start = i
            while i < end and text[i] not in "{;":
                i += 1
            if i >= end:
                return
            head = text[head_start:i].strip()
            if text[i] == ";":
                i += 1
                continue
            depth, j = 1, i + 1
            while j < end and depth:
                depth += (text[j] == "{") - (text[j] == "}")
                j += 1
            line = text.count("\n", 0, head_start) + 1
            if head.startswith("@"):
                if head.startswith(("@media", "@supports", "@layer", "@container")):
                    walk(i + 1, j - 1)
            elif head != ":root" and not head.startswith(":root"):
                found.append((line, head, j - head_start))
            i = j

    walk(0, len(text))
    return found


def vocabulary(text: str) -> tuple[set[str], set[str]]:
    """(every whole word, every word that ends in "-" right before a quote, "{", "$" or "+")."""
    words = set(re.findall(r"[\w-]+", text))
    stems = set(re.findall(r"(?<![\w-])([\w-]*-)(?=[\"'`{$+])", text))
    return words, stems


def seen_token(token: str, vocab: tuple[set[str], set[str]]) -> bool:
    words, stems = vocab
    return token in words or any(token[:m.end()] in stems for m in re.finditer("-", token))


def dead_rules(css: str, text: str) -> tuple[list[dict], int]:
    vocab = vocabulary(text)
    dead = []
    found = rules(css)
    for line, head, size in found:
        selectors = [s.strip() for s in head.split(",") if s.strip()]
        verdicts = []
        for selector in selectors:
            tokens = CLASS.findall(selector)
            verdicts.append(bool(tokens) and any(not seen_token(t, vocab) for t in tokens))
        if verdicts and all(verdicts):
            dead.append({"line": line, "selector": head, "bytes": size})
    return dead, len(found)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", default=str(DEFAULT))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", default=str(ROOT / "lightning"), help="the folder whose templates and scripts are read")
    args = parser.parse_args()
    css = Path(args.file).read_text(encoding="utf-8")
    dead, total = dead_rules(css, corpus(Path(args.root)))
    if args.json:
        print(json.dumps(dead))
        return 0
    name = Path(args.file).name
    for rule in dead:
        print(f"{name}:{rule['line']} {rule['selector']}")
    print(f"dead rules: {len(dead)} of {total}, about {sum(r['bytes'] for r in dead)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
