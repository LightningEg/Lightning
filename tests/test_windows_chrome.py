"""Windows chrome (IV-3BF3): names are not spell-checked, scrollbars are thin, selection is a soft wash."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "lightning" / "ui"
INPUT = re.compile(r"<input\b(?:[^>{]|\{\{.*?\}\}|\{%.*?%\})*>", re.S)


def test_every_name_input_turns_spellcheck_off():
    missing = []
    for path in (ROOT / "templates").rglob("*.html"):
        for tag in INPUT.findall(path.read_text(encoding="utf-8")):
            if re.search(r'name="(name|counterparty|merchant)"', tag) and 'type="hidden"' not in tag and 'spellcheck="false"' not in tag:
                missing.append(f"{path.relative_to(ROOT).as_posix()}: {tag[:80]}")
    assert not missing, missing


def test_css_has_thin_scrollbars_selection_and_balanced_headings():
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    for rule in ("scrollbar-width: thin", "scrollbar-gutter: stable", "::selection", "text-wrap: balance"):
        assert rule in css, rule
