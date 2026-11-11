"""Builds lightning/ui/static/phone-base.css (IV-3AY4): the rules of style.css the phone layer can use, so the phone's
stylesheet bundle (web.PHONE_CSS) no longer carries the whole PC stylesheet.

A rule stays, unchanged and in its place, when one of its selectors names only classes and ids that appear somewhere in
what reaches the phone: the phone templates, the shared partials, the PC templates a phone page extends, the static
scripts (classes they add) and the UI's Python (classes written in code). Element, attribute and pseudo selectors
always stay. @media, @supports and @container blocks keep the rules inside them that stay; @font-face, @keyframes and
the like stay whole. Run it after changing style.css or when a phone page starts to use a PC class, then
tools/build_rtl_css.js (it writes phone-base.rtl.css). tests/test_phone_own_base.py fails when it is stale.

    python tools/build_phone_base_css.py
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "lightning" / "ui"
STATIC, TEMPLATES = UI / "static", UI / "templates"
SHARED = ("deposits/detail.html", "deposits/receipt_events.html", "investments/_targets.html", "investments/add.html",
          "investments/add_gold.html", "settings/_emergency_basis.html", "settings/_update.html",
          "settings/budget_section.html", "settings/currencies.html", "settings/financial_health_section.html",
          "settings/index.html", "settings/zakat_section.html")
GROUPS = ("@media", "@supports", "@container", "@layer")   # blocks whose rules are filtered one by one


def reachable_words() -> set[str]:
    files = [*(TEMPLATES / "phone").rglob("*.html"), *(TEMPLATES / "partials").rglob("*.html"),
             *(TEMPLATES / name for name in SHARED), *STATIC.glob("*.js"), *UI.rglob("*.py")]
    words: set[str] = set()
    for path in files:
        words.update(re.findall(r"[A-Za-z0-9_-]+", path.read_text(encoding="utf-8", errors="ignore")))
    return words


def top_level(selectors: str) -> list[str]:
    """A selector list split at its own commas, not those inside :is(...) or :not(...)."""
    parts, depth, start = [], 0, 0
    for at, char in enumerate(selectors):
        depth += (char == "(") - (char == ")")
        if char == "," and depth == 0:
            parts.append(selectors[start:at])
            start = at + 1
    return [*parts, selectors[start:]]


# Class families built by joining strings in templates and code ("tone-" ~ key, "is-" ~ state): never whole in a file.
FAMILIES = ("is-", "has-", "tone-", "dir-", "surface-", "scheme-", "kc-", "chart-", "class-", "level-", "health-")
FUNCTIONS = re.compile(r":(not|is|where|has|matches)\(([^()]*)\)")


def usable(selector: str, words: set[str]) -> bool:
    """Whether a selector can match what reaches the phone: every class and id it needs is there. Inside :is(),
    :where() and :has() one alternative is enough; what :not() names is never needed."""
    selector = re.sub(r"\[[^\]]*\]", "", selector)
    while (found := FUNCTIONS.search(selector)):
        kind, inner = found.groups()
        ok = kind == "not" or any(usable(alt, words) for alt in inner.split(","))   # an emptied alternative is an element or attribute: it stays
        selector = selector[:found.start()] + ("" if ok else ".-never-") + selector[found.end():]
    return all(name in words or name.startswith(FAMILIES) for name in re.findall(r"[.#]([A-Za-z_-][\w-]*)", selector))


def statements(css: str) -> list[tuple[str, str | None]]:
    """Top-level (prelude, block) pairs; a statement without a block (@import ...;) has block None."""
    out, at, depth, start = [], 0, 0, 0
    prelude_end = None
    while at < len(css):
        char = css[at]
        if char == "{":
            if depth == 0:
                prelude_end = at
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                out.append((css[start:prelude_end].strip(), css[prelude_end + 1:at]))
                start = at + 1
        elif char == ";" and depth == 0:
            out.append((css[start:at].strip(), None))
            start = at + 1
        at += 1
    return out


def keep(css: str, words: set[str]) -> str:
    kept = []
    for prelude, block in statements(css):
        if block is None:
            kept.append(prelude + ";")
        elif prelude.startswith(GROUPS):
            inner = keep(block, words)
            if inner.strip():
                kept.append(f"{prelude} {{\n{inner}}}")
        elif prelude.startswith("@") or any(usable(s.strip(), words) for s in top_level(prelude) if s.strip()):
            kept.append(f"{prelude} {{{block}}}")
    return "\n".join(kept) + "\n"


def render() -> str:
    """The text phone-base.css should hold now (tests/test_phone_own_base.py compares it with the file)."""
    source = (STATIC / "style.css").read_text(encoding="utf-8")
    body = keep(re.sub(r"/\*.*?\*/", "", source, flags=re.S), reachable_words())
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    return f"/* phone-base.css: generated by tools/build_phone_base_css.py from style.css (source {digest}); do not edit by hand. */\n{body}"


if __name__ == "__main__":
    text = render()
    (STATIC / "phone-base.css").write_text(text, encoding="utf-8")
    print(f"phone-base.css: {len(text)} bytes")
