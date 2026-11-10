"""One plural helper: English counts say "1 day", never "1 days" (IV-3BC)."""
import pytest

from lightning.ui.i18n import counted, translate


@pytest.mark.parametrize("n, text", [(0, "0 days"), (1, "1 day"), (2, "2 days"), (11, "11 days")])
def test_counted_english(n, text):
    assert counted(n, "day", "days") == text


def test_singular_keys_have_arabic():
    assert translate("1 day left", "ar") == "فاضل يوم واحد"
    assert translate("1 category", "ar") == "فئة واحدة"


def test_counted_is_a_template_filter():
    from lightning.ui.web import templates
    assert templates.env.from_string("{{ 1|counted('category', 'categories') }}").render() == "1 category"
    assert templates.env.from_string("{{ 3|counted('category', 'categories') }}").render() == "3 categories"


FORMS = {  # English key: (one, two, 3-10, 11+)
    "{n} accounts": ("حساب واحد", "حسابين", "3 حسابات", "11 حساب"),
    "{n} categories": ("فئة واحدة", "فئتين", "3 فئات", "11 فئة"),
    "{n} rows": ("صف واحد", "صفين", "3 صفوف", "11 صف"),
    "{n} items": ("عنصر واحد", "عنصرين", "3 عناصر", "11 عنصر"),
    "{n} bills": ("فاتورة واحدة", "فاتورتين", "3 فواتير", "11 فاتورة"),
    "{n} rules": ("قاعدة واحدة", "قاعدتين", "3 قواعد", "11 قاعدة"),
    "{n} years": ("سنة واحدة", "سنتين", "3 سنين", "11 سنة"),
    "{n} transactions": ("معاملة واحدة", "معاملتين", "3 معاملات", "11 معاملة"),
}


@pytest.mark.parametrize("key", sorted(FORMS))
@pytest.mark.parametrize("index, n", [(0, 1), (1, 2), (2, 3), (3, 11)])
def test_arabic_agrees_for_each_noun(key, index, n):
    assert translate(key, "ar", n=n) == FORMS[key][index]


def test_no_hand_built_plurals_in_ui_or_workflows():
    """IV-3BC3: every count goes through counted(); no `'s' if` or "noun(s)" in what people read."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "lightning"
    pattern = re.compile(r"'s' if|\"s\" if|[A-Za-z]\(s\)")
    allowed = {("ui/sections.py", "keep(s)"), ("ui/templates/phone/partials/charts.html", "(s)")}
    hits = []
    for folder in ("ui", "workflows"):
        for path in (root / folder).rglob("*"):
            if path.suffix not in {".py", ".html"}:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for match in pattern.finditer(line):
                    rel = path.relative_to(root).as_posix()
                    if any(rel == f and tok in line for f, tok in allowed):
                        continue
                    hits.append(f"{rel}:{number}")
    assert not hits, hits
