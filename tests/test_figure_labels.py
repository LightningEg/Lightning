"""IT-12AE (owner, 2026-11-10): a registry figure's name reaches the screen through `fig.<key>.label` (templates) or
`lightning.core.figures.label(key)` (Python), so renaming a figure renames it everywhere at once. Every quoted
registry label still written out by hand in lightning/ui is counted per file in tests/ui_figure_labels.json; a
count may fall, never rise. After replacing some, `python -m tests.test_figure_labels` rewrites the file."""
import json
import re
from pathlib import Path

from lightning.core.figures import FIGURES

UI = Path(__file__).resolve().parent.parent / "lightning" / "ui"
RATCHET = Path(__file__).resolve().parent / "ui_figure_labels.json"
_LABELS = re.compile(r"""(['"])(""" + "|".join(sorted((re.escape(f.label) for f in FIGURES.values()), key=len,
                                                         reverse=True)) + r""")\1""")


def _files():
    for path in sorted(UI.rglob("*")):
        if path.suffix in (".py", ".html") and "i18n" not in path.name:
            yield path.relative_to(UI).as_posix(), path


def literal_label_counts() -> dict[str, int]:
    counts = {rel: len(_LABELS.findall(path.read_text(encoding="utf-8"))) for rel, path in _files()}
    return {rel: n for rel, n in counts.items() if n}


def test_figure_names_written_by_hand_only_fall():
    allowed = json.loads(RATCHET.read_text(encoding="utf-8"))
    now = literal_label_counts()
    rose = {rel: (allowed.get(rel, 0), n) for rel, n in now.items() if n > allowed.get(rel, 0)}
    assert not rose, ("a registry figure's name is written by hand (allowed, now); use fig.<key>.label in a "
                      f"template or figures.label(key) in Python: {rose}")


def test_the_label_ratchet_is_lowered():
    allowed = json.loads(RATCHET.read_text(encoding="utf-8"))
    now = literal_label_counts()
    fell = {rel: (n, now.get(rel, 0)) for rel, n in allowed.items() if now.get(rel, 0) < n}
    assert not fell, f"lower these in tests/ui_figure_labels.json (python -m tests.test_figure_labels): {fell}"


def test_the_label_ratchet_catches_a_hand_written_name(tmp_path):
    assert _LABELS.findall("""<b>{{ 'Kept as cash'|tr(locale) }}</b> <i>{{ fig.kept_as_cash.label }}</i>""")


if __name__ == "__main__":
    RATCHET.write_text(json.dumps(literal_label_counts(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {RATCHET}")
