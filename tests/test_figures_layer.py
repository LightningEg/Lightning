"""The figures layer stays in one place (Architecture › Figures layer): services compute, the drawing
code only draws. These checks fail when a page starts reading the ledger or doing money arithmetic
on its own, which is how two screens end up showing two numbers for one figure."""
import re
from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "lightning" / "ui"


def test_the_drawing_code_never_reads_the_ledger():
    for path in (UI / "visuals.py", UI / "charts.py", UI / "keynotes.py"):
        text = path.read_text()
        assert not re.search(r"\.db\.|\.q\.|from_e6|to_e6|_e6\b", text), path.name


def test_routes_read_figures_from_services_not_the_database():
    for path in (UI / "routes").glob("*.py"):
        text = path.read_text()
        reads = re.findall(r"\.db\.(?:all|one|scalar|execute)\(|\.q\.\w+\(", text)
        assert not reads, f"{path.name} reads the database directly: {reads}"


def test_every_money_path_uses_the_one_rule():
    service = (UI.parent / "reporting" / "service.py").read_text()
    for name in ("cash_flow", "flows_by_date", "_money_out_by_category", "money_in_by_category",
                 "spending_by_category", "_spending"):
        body = service.split(f"    def {name}(", 1)[1].split("\n    def ", 1)[0]
        assert "flow_of(" in body, name


# IT-12AE3: a ratchet on arithmetic in the UI. Every `+ - * /` (and `//`, `%` on numbers, augmented forms) and every
# `sum(...)` in lightning/ui is counted per file; the counts live in tests/ui_arithmetic.json and may fall, never rise.
# A file not listed must have none. Geometry, a count of rows or a date is not money: end that line with
# `# not money` and it is skipped. Drawing and words are outside the count (charts, visuals, i18n, journal, claimed).
# After moving a figure to its owner service, lower the file's count: `python -m tests.test_figures_layer`.
import ast
import json

RATCHET = Path(__file__).resolve().parent / "ui_arithmetic.json"
_SKIP = ("charts.py", "visuals.py")
_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv)


def _ui_files():
    for path in sorted(UI.rglob("*.py")):
        rel = path.relative_to(UI).as_posix()
        if path.name in _SKIP or "i18n" in path.name or rel.startswith(("journal", "templates/")):
            continue
        yield rel, path


def _arithmetic_lines(path: Path) -> list[int]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    tree = ast.parse(text)
    found = []
    for node in ast.walk(tree):
        line = None
        if isinstance(node, ast.BinOp) and isinstance(node.op, _OPS):
            # "a" + "b" and f-string glue are words, not money
            if any(isinstance(side, ast.Constant) and isinstance(side.value, str) or isinstance(side, ast.JoinedStr)
                   for side in (node.left, node.right)):
                continue
            line = node.lineno
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, _OPS):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                continue
            line = node.lineno
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "sum":
            line = node.lineno
        if line and "# not money" not in lines[line - 1]:
            found.append(line)
    return found


def ui_arithmetic_counts() -> dict[str, int]:
    counts = {rel: len(_arithmetic_lines(path)) for rel, path in _ui_files()}
    return {rel: n for rel, n in sorted(counts.items()) if n}


def test_arithmetic_in_the_ui_only_falls():
    allowed = json.loads(RATCHET.read_text(encoding="utf-8"))
    now = ui_arithmetic_counts()
    rose = {rel: (allowed.get(rel, 0), n) for rel, n in now.items() if n > allowed.get(rel, 0)}
    assert not rose, ("money arithmetic grew in the UI (allowed, now); move it to the service that owns the figure, "
                      f"or mark geometry/counts/dates `# not money`: {rose}")


def test_the_ratchet_is_lowered_when_arithmetic_moves_out():
    allowed = json.loads(RATCHET.read_text(encoding="utf-8"))
    now = ui_arithmetic_counts()
    fell = {rel: (n, now.get(rel, 0)) for rel, n in allowed.items() if now.get(rel, 0) < n}
    assert not fell, f"lower these in tests/ui_arithmetic.json (run python -m tests.test_figures_layer): {fell}"


def test_the_ratchet_catches_a_subtraction_on_a_phone_screen(tmp_path):
    sample = tmp_path / "screen.py"
    sample.write_text("def left(planned, spent):\n    return planned - spent\n\ndef width(n):\n    return n * 8  # not money\n")
    assert _arithmetic_lines(sample) == [2]


if __name__ == "__main__":
    RATCHET.write_text(json.dumps(ui_arithmetic_counts(), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {RATCHET}")
