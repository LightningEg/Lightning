"""Field wells are a soft green well, calm yellow on focus, defined once as --field / --field-focus (feedback batch 004, T2)."""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "lightning" / "ui" / "static"
GUIDELINE = Path(__file__).resolve().parents[1] / "guideline"


def _css():
    return {p.name: p.read_text(encoding="utf-8") for p in STATIC.glob("*.css")}


def test_the_old_grey_wells_are_gone_and_the_new_ones_are_defined_once():
    files = _css()
    for name, css in files.items():
        for old in ("#EEF4F2", "#E4EEEA"):
            assert old.lower() not in css.lower(), f"{old} still in {name}"
    assert "--field:#EAF3EE" in files["style.css"] and "--field-focus:#F5EFCF" in files["style.css"]
    assert len(re.findall(r"--field:\s*#", files["style.css"])) == 1


def test_the_guideline_names_the_same_well():
    for name in ("app.html", "app-ar.html", "phone.html", "phone-ar.html"):
        text = (GUIDELINE / name).read_text(encoding="utf-8")
        assert "--field:#EAF3EE;--field-focus:#F5EFCF" in text, name


def _luminance(hex_colour):
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def test_text_on_the_wells_stays_readable():
    for text in ("#0D2233", "#304A5C", "#566E7E"):  # Ink, Ink 2, Muted (the placeholder)
        for well in ("#EAF3EE", "#F5EFCF"):
            hi, lo = sorted((_luminance(text), _luminance(well)), reverse=True)
            assert (hi + 0.05) / (lo + 0.05) >= 4.5, (text, well)
