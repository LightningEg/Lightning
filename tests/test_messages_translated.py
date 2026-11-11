"""IV-3BD2: every message a person can read from ValidationError / NotFoundError / ProfileError has Arabic.

Walks lightning/**/*.py, takes the first argument of each such call: a plain string must be a key of ARABIC_UI;
an f-string is turned into a pattern ("{n}" for each hole) and must match a pattern key."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from lightning.ui.i18n import ARABIC_UI, translate

ROOT = Path(__file__).resolve().parents[1] / "lightning"
CALLS = {"ValidationError", "NotFoundError", "ProfileError"}
ALLOWED: dict[str, str] = {  # message -> reason (keep under 10)
    "changed": "internal marker: restore.py catches it and never shows it",
    "{n}: {n}": "a record reference plus an already-translated message: the UI translates each side of the colon",
    "damaged": "internal marker: session.py catches it and never shows it",
}


def _messages():
    for path in sorted(ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and node.args):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if name not in CALLS:
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                yield path, node.lineno, arg.value, False
            elif isinstance(arg, ast.JoinedStr):
                parts = [v.value if isinstance(v, ast.Constant) else "{n}" for v in arg.values]
                yield path, node.lineno, "".join(parts), True
            # a variable or a call (str(exc), exc.message) is not a literal: not read here


def _covered(text: str, is_f: bool) -> bool:
    if text in ARABIC_UI:
        return True
    if text in ALLOWED:
        return True
    shown = translate(re.sub(r"\{n\}", "7", text) if is_f else text, "ar")
    return bool(re.search(r"[؀-ۿ]", shown)) and not re.search(r"[A-Za-z]{3}", shown.replace("CSV", ""))


def test_every_validation_message_has_arabic():
    missing = sorted({(str(p.relative_to(ROOT)), line, text) for p, line, text, f in _messages() if not _covered(text, f)})
    assert not missing, f"{len(missing)} messages without Arabic, e.g.\n" + "\n".join(f"{p}:{l} {t}" for p, l, t in missing[:15])


def test_allowlist_is_short():
    assert len(ALLOWED) <= 10
