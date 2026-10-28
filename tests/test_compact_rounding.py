"""Compact labels omit .0 after rounding in either language."""
import pytest

from lightning.ui import web


@pytest.mark.parametrize("locale,thousand,million", [("en", "k", "M"), ("ar", " ألف", " مليون")])
def test_compact_rounding_keeps_labels_short(monkeypatch, locale, thousand, million):
    monkeypatch.setattr(web, "ui_locale", lambda: locale)
    for value, expected in [
        ("9999", "10" + thousand),
        ("-9999", "−10" + thousand),
        ("1999999", "2" + million),
        ("9700", "9.7" + thousand),
        ("1000", "1" + thousand),
        ("950", "950"),
        (None, "—"),
    ]:
        assert web._compact(value) == expected
