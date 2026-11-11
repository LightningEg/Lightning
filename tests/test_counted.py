"""IV-3BC: counts read right ("1 day", not "1 days") in English and Arabic."""
import re

import pytest
from fastapi.testclient import TestClient

from lightning.ui.i18n import counted, translate
from lightning.ui.web import create_app


@pytest.mark.parametrize("n, text", [(0, "0 days"), (1, "1 day"), (2, "2 days"), (11, "11 days")])
def test_counted_english(n, text):
    assert counted(n, "day", "days") == text


def test_a_group_with_one_category_says_category(c):
    real = c.categories.table
    c.categories.table = lambda *a, **k: [(l1, rows[:1]) for l1, rows in real(*a, **k)]
    html = TestClient(create_app(c)).get("/categories").text
    sizes = re.findall(r"<small>(\d+ categor(?:y|ies))</small>", html)
    assert "1 category" in sizes and "1 categories" not in html


@pytest.mark.parametrize("n, ar", [(1, "فاضل يوم واحد"), (5, "فاضل 5 أيام")])
def test_days_left_in_arabic(n, ar):
    assert translate(counted(n, "day left", "days left"), "ar") == ar


_NOUNS = [  # (English key with {n}, singular, two, 3-10, 11+) for every counted noun the UI uses
    ("{n} accounts", "حساب واحد", "حسابين", "حسابات", "حساب"),
    ("{n} categories", "فئة واحدة", "فئتين", "فئات", "فئة"),
    ("{n} rows", "صف واحد", "صفين", "صفوف", "صف"),
    ("{n} bills", "فاتورة واحدة", "فاتورتين", "فواتير", "فاتورة"),
    ("{n} rules", "قاعدة واحدة", "قاعدتين", "قواعد", "قاعدة"),
    ("{n} items", "عنصر واحد", "عنصرين", "عناصر", "عنصر"),
    ("Every {n} years", "كل سنة واحدة", "كل سنتين", "كل {n} سنين", "كل {n} سنة"),
    ("{n} transactions", "معاملة واحدة", "معاملتين", "{n} معاملات", "{n} معاملة"),
    ("{n} days left", "فاضل يوم واحد", "فاضل يومين", "فاضل {n} أيام", "فاضل {n} يوم"),
    ("{n} months", "شهر واحد", "شهرين", "{n} شهور", "{n} شهر"),
    ("{n} payments", "دفعة واحدة", "دفعتين", "{n} دفعات", "{n} دفعة"),
]


@pytest.mark.parametrize("key, one, two, few, many", _NOUNS)
@pytest.mark.parametrize("n", [0, 1, 2, 3, 10, 11])
def test_arabic_agrees_for_every_counted_noun(key, one, two, few, many, n):
    out = translate(key, "ar", n=n)
    want = one if n == 1 else two if n == 2 else few if 3 <= n <= 10 else many
    if "{n}" not in want:
        want = want if n in (1, 2) else f"{n} {want}"
    assert out == want.replace("{n}", str(n))


@pytest.mark.parametrize("n, expected", [(0, "0 بند ميزانية"), (1, "بند واحد ميزانية"),
                                         (2, "بندين ميزانية"), (3, "3 بنود ميزانية"), (11, "11 بند ميزانية")])
def test_budget_line_items_agree(n, expected):
    assert translate("Updated carryover for {n} budget lines.", "ar", n=n) == f"اتحدّث المبلغ المرحّل لـ {expected}."


def test_no_hand_built_plurals_in_the_ui_or_workflows():
    """3BC3: a count goes through counted(); an `'s' if` or a `row(s)` in the UI code is a wrong plural waiting to happen."""
    from pathlib import Path
    pattern = re.compile(r"""'s' if|"s" if|(?<![\w.])[a-z]+\(s\)""")
    root = Path(__file__).resolve().parent.parent / "lightning"
    hits = [f"{path.relative_to(root)}:{n}" for folder in ("ui", "workflows") for path in (root / folder).rglob("*")
            if path.suffix in (".py", ".html") for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if pattern.search(line)]
    assert not hits, hits


@pytest.mark.parametrize("english, arabic", [
    ("Replaced “x” on 1 row.", "اتغيرت “x” في صف واحد."),
    ("Replaced “x” on 3 rows.", "اتغيرت “x” في 3 صفوف."),
    ("Across 1 account", "في حساب واحد"),
    ("Across 2 accounts", "في حسابين"),
    ("2 transactions", "معاملتين"),
    ("11 transactions", "11 معاملة"),
])
def test_a_count_built_in_english_still_agrees_in_arabic(english, arabic):
    assert translate(english, "ar") == arabic


def test_a_unit_the_person_typed_is_never_pluralised():
    from lightning.ui.web import _units_of
    assert _units_of(3, "gram") == "3 gram" and _units_of(3, "piece") == "3 piece" and _units_of(1, "piece") == "1 piece"


def test_the_browser_agrees_counts_like_the_server():
    """3BC4: lightning-t.js ports _agree_counts; the Node test runs it with a small Arabic table."""
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    result = subprocess.run([node, "--test", str(Path(__file__).parent / "plural-runtime.test.cjs")], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_browser_gets_the_counted_table():
    from lightning.ui.web import _ARABIC_UI_JS
    assert b"window.LIGHTNING_COUNTED=" in _ARABIC_UI_JS and "معاملة واحدة".encode() in _ARABIC_UI_JS
