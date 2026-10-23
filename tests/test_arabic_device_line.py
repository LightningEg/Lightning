"""The borrowed-from device line is a template the page can translate."""

from lightning.ui.i18n import translate


def test_borrowed_from_line_is_a_template() -> None:
    text = "Borrowed from {name}"
    assert translate(text, "en", name="your phone") == "Borrowed from your phone"


def test_borrowed_from_line_arabic_has_no_english() -> None:
    out = translate("Borrowed from {name}", "ar", name="your phone")
    assert "Borrowed" not in out
    assert "your phone" not in out
    assert out.strip()


def test_read_only_pc_line_arabic_has_no_english() -> None:
    line = "Read only on this PC: the ledger is going home or needs repair."
    out = translate(line, "ar")
    assert "Read only" not in out
    assert out.strip()
