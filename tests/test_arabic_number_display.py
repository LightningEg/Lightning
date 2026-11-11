from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "lightning/ui/static/arabic-numbers.js"


def test_arabic_number_display_script_is_loaded_in_both_shared_shells():
    for template in ("base.html", "phone/base.html"):
        source = (ROOT / "lightning/ui/templates" / template).read_text(encoding="utf-8")
        assert "static_url('arabic-numbers.js')" in source


def test_arabic_display_localizes_numeric_tokens_but_keeps_identifiers():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable for the browser display helper test")
    result = subprocess.run(
        [node, "-e", "const {localizeNumericText:f}=require(process.argv[1]); process.stdout.write(f(process.argv[2]));",
         str(SCRIPT), "المتاح 12,345.67 ج.م · 2026-10-09 · 25% · TXN-2026-001 · V1.0.0-beta.1 · 9.7k"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert result == "المتاح \u2066١٢٬٣٤٥٫٦٧\u2069 ج.م، \u2066\u202d٢٠٢٦-١٠-٠٩\u202c\u2069، \u2066٢٥٪\u2069، TXN-2026-001، V1.0.0-beta.1، \u2066٩٫٧k\u2069"


def test_arabic_display_keeps_the_minus_on_the_left_of_its_digits():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable for the browser display helper test")
    result = subprocess.run(
        [node, "-e", "const {localizeNumericText:f}=require(process.argv[1]); process.stdout.write(f(f(process.argv[2])));",
         str(SCRIPT), "-6,000.00"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert result == "\u2066-٦٬٠٠٠٫٠٠\u2069"


def test_the_arabic_overview_says_gm_percent_and_its_period_in_arabic_digits(c, monkeypatch):
    """Owner, 2026-11-08 (IV-3BK5, IV-3BK7): EGP is ج.م, a percent after a figure is ٪, and the period chip's month
    is in Arabic with Arabic-Indic digits; fields and links keep their own form."""
    import html as _html
    import re

    from starlette.testclient import TestClient

    from lightning.samples import load_mohab_2026
    from lightning.ui.web import create_app

    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-02")
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    load_mohab_2026(c)
    client = TestClient(create_app(c))
    client.post("/settings/locale", data={"locale": "ar"})
    page = client.get("/").text
    shown = _html.unescape(re.sub(r"(?s)<(script|style|svg|textarea)\b.*?</\1>|<[^>]+>", "\n", page))
    assert "ج.م" in shown and not re.search(r"(?<![A-Za-z/])EGP(?![A-Za-z/=])", shown)
    assert "٪" in shown and not re.search(r"\d%", shown)
    assert not re.search(r"\b\d{4}-\d\d(?:-\d\d)?\b", shown.replace("OUT-", "").replace("IN-", ""))
    assert "أكتوبر ٢٠٢٦" in shown  # the period chip: the month in words and Arabic-Indic digits
