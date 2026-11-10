"""Names sort folded, the same way in Python and in the browser (IT-3BI2)."""
from __future__ import annotations

import re
from pathlib import Path

from lightning.core.matching import fold_search_text

NAMES = ["إيمان", "احمد", "Zed", "ahmed"]
ROOT = Path(__file__).resolve().parent.parent


def test_folded_order_is_latin_then_arabic_by_letter():
    assert sorted(NAMES, key=fold_search_text) == ["ahmed", "Zed", "احمد", "إيمان"]


def test_every_locale_compare_in_the_app_names_a_locale():
    source = (ROOT / "lightning/ui/static/app.js").read_text(encoding="utf-8")
    calls = re.findall(r"localeCompare\([^)]*\)[^)]*\)?", source)
    assert calls and all("documentElement.lang" in call for call in calls), calls
