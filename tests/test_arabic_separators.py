"""3U (Audit 1, section 5): in Arabic a middle dot beside a number reads as the Arabic zero (Late 17 days read as 170),
decimals and percent signs are one kind, and the undo button speaks Arabic."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from lightning.ui.i18n import arabic_dots, localize_html
from test_arabic_no_english import EXTRA_PAGES, PC_PAGES, PHONE_EXTRA, PHONE_PAGES, _client, sample  # noqa: F401

SCRIPT = Path(__file__).parents[1] / "lightning/ui/static/arabic-numbers.js"
ARABIC_DIGIT = "٠-٩"
BIDI = "⁦-⁩‪-‮‎‏"
DOT_BESIDE_DIGIT = re.compile(rf"[0-9{ARABIC_DIGIT}%][{BIDI}\s]*·|·[{BIDI}\s]*[0-9{ARABIC_DIGIT}]")


class _Visible(HTMLParser):
    """Every text node and the attributes a person reads, as the browser would see them."""

    def __init__(self):
        super().__init__()
        self.skip, self.found = [], []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "textarea"):
            self.skip.append(tag)
        self.found += [v for n, v in attrs if n in ("title", "aria-label", "placeholder", "data-tip") and v]

    def handle_endtag(self, tag):
        if self.skip and self.skip[-1] == tag:
            self.skip.pop()

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.found.append(data)


def _pages(client, phone):
    paths = list(PHONE_PAGES + PHONE_EXTRA) if phone else list(PC_PAGES + EXTRA_PAGES)
    for path in paths:
        response = client.get(path)
        if response.status_code == 200:
            yield path, response.text


def _visible(page):
    parser = _Visible()
    parser.feed(page)
    return parser.found


def test_a_dot_beside_a_number_becomes_the_arabic_comma():
    assert arabic_dots("متأخر · 17 يوم") == "متأخر، 17 يوم"
    assert arabic_dots("٢٠٢٦-١٠-٠٣ · فاتورة") == "٢٠٢٦-١٠-٠٣، فاتورة"
    assert arabic_dots("5 · 1") == "5، 1"
    assert arabic_dots("فاتورة · اشتراك") == "فاتورة · اشتراك"  # between two words it cannot be read as a zero


def test_the_dot_is_replaced_across_a_tag_but_never_inside_a_field_a_person_edits():
    page = ('<p><time>2026-10-03</time> · <b>Bill</b></p><input value="Rent · 2026">'
            '<textarea>note · 5</textarea><script>var a = "1 · 2"</script>')
    result = localize_html(page)
    assert "</time>، <b>" in result
    assert 'value="Rent · 2026"' in result and "note · 5" in result and '"1 · 2"' in result


@pytest.mark.parametrize("phone", [False, True], ids=["pc", "phone"])
def test_no_arabic_page_has_a_dot_beside_a_number(sample, phone):  # noqa: F811
    c, _ = sample
    client = _client(c, phone)
    bad = {}
    for path, page in _pages(client, phone):
        found = sorted({text.strip()[:80] for text in _visible(page) if DOT_BESIDE_DIGIT.search(text)})
        if found:
            bad[path] = found[:4]
    assert not bad, bad


def test_the_figures_shown_use_one_decimal_mark_and_one_percent_sign(sample):  # noqa: F811
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable for the browser display helper test")
    c, _ = sample
    texts = {}
    for phone in (False, True):
        for path, page in _pages(_client(c, phone), phone):
            for text in _visible(page):
                texts.setdefault(text, path)
    items = list(texts)
    shown = json.loads(subprocess.run(
        [node, "-e", "const {localizeNumericText:f}=require(process.argv[1]);"
                     "process.stdout.write(JSON.stringify(JSON.parse(require('fs').readFileSync(0,'utf8')).map(f)));",
         str(SCRIPT)], input=json.dumps(items), capture_output=True, text=True, check=True).stdout)
    latin_mark = re.compile(rf"[{ARABIC_DIGIT}][.,][{ARABIC_DIGIT}]")
    bad = [(texts[a], s[:90]) for a, s in zip(items, shown)
           if latin_mark.search(s) or "٪" in s or DOT_BESIDE_DIGIT.search(s)]
    assert not bad, bad[:6]


@pytest.mark.parametrize("label", ["Saved changes", "Account changes", "Transaction changes", "Payment plan changes",
                                   "Reserve changes", "Budget changes", "Statement import", "SMS review", "Rule changes",
                                   "Merge duplicate transactions", "Fund the payday plan"])
def test_the_undo_button_is_in_arabic(label):
    from lightning.ui.web import templates
    page = templates.env.get_template("partials/history.html").render(
        action_history={"undo": {"id": 1, "label": label}, "redo": None}, locale="ar", path="/", session_token="")
    titles = re.findall(r'data-history="undo"[^>]*title="([^"]*)"', localize_html(page))
    assert titles and not re.search(r"[A-Za-z]{3}", titles[0].replace("Ctrl+Z", "")), titles


@pytest.mark.parametrize("english", [
    "Plan this transaction", "1 entry", "e.g. 100 shares, 12.5 grams", "Setting", "Where",
    "From 2026-10 on · the total plan stays the same", "System-generated · MONTH_END",
    "Transaction OUT-2026-08-12-001 · 2026-08-12 · 650.00 EGP. Adding this plan does not post or edit a transaction.",
])
def test_the_other_strings_the_audit_found_are_translated(english):
    shown = re.sub(r"<[^>]+>", "", localize_html(f"<p>{english}</p>"))
    assert not re.findall(r"[a-z]{4,}", re.sub(r"OUT-[\d-]+|EGP", "", shown)), shown
