"""The borrowed/lent device line stays on screen; other flashes still auto-dismiss."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_device_line_is_not_auto_dismissed() -> None:
    js = (ROOT / "lightning/ui/static/app.js").read_text(encoding="utf-8")
    assert 'classList.contains("device-line")' in js
    # The skip sits on the same early-return as empty and error flashes.
    assert 'flash.classList.contains("device-line")' in js


def test_device_line_markup_still_present() -> None:
    for name in ("lightning/ui/templates/base.html", "lightning/ui/templates/phone/base.html"):
        html = (ROOT / name).read_text(encoding="utf-8")
        assert "device-line" in html
