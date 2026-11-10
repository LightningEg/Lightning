"""Every message a person can read from a ValidationError, NotFoundError or ProfileError has Arabic (IV-3BD2).

Walks lightning/**/*.py with `ast`: the first argument of each of those calls must be a key of ARABIC_UI, or an
f-string whose shape matches a `{name}` pattern key.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from lightning.ui.i18n import ARABIC_UI, translate

ROOT = Path(__file__).resolve().parent.parent / "lightning"
CALLS = {"ValidationError", "NotFoundError", "ProfileError"}
# A message built at run time from a variable cannot be read here; each entry says why it is allowed.
ALLOWED: dict[str, str] = {
    "transactions/service.py:574": "joins a record name and an already-translated reason: two parts, each translated on its own",
}


def _shape(node: ast.AST) -> str | None:
    """The message with each f-string hole as {x}: None when it is not a literal at all."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(p.value if isinstance(p, ast.Constant) else "{x}" for p in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _shape(node.left), _shape(node.right)
        return None if left is None or right is None else left + right
    return None


def messages() -> list[tuple[str, int, str]]:
    found = []
    for path in sorted(ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and node.args:
                name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                if name in CALLS:
                    shape = _shape(node.args[0])
                    if shape:
                        found.append((path.relative_to(ROOT).as_posix(), node.lineno, shape))
    return found


def _has_arabic(shape: str) -> bool:
    if shape in ARABIC_UI:
        return True
    if "{x}" not in shape:
        return translate(shape, "ar") != shape
    probe = shape.replace("{x}", "7")
    return translate(probe, "ar") != probe


def test_every_error_message_has_arabic():
    missing = [f"{f}:{n} {shape}" for f, n, shape in messages() if f"{f}:{n}" not in ALLOWED and not _has_arabic(shape)]
    assert not missing, f"{len(missing)} messages without Arabic:\n" + "\n".join(missing)
    assert len(ALLOWED) <= 10
