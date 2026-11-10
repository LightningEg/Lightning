"""Search uses screen money notation without changing the amount in its entry link."""
from urllib.parse import parse_qs, urlsplit

import pytest

from lightning.ui.routes.search import entry, fmt_amount


@pytest.mark.parametrize("amount,expected", [
    ("1234", "1,234"), ("1234.00", "1,234"), ("1234.5", "1,234.50"),
    ("-1234.5", "−1,234.50"), ("−1,234.50", "−1,234.50"),
    ("0", "0"), ("-0.00", "0"),
])
def test_search_amounts_use_grouping_cents_and_a_true_minus(amount, expected):
    assert fmt_amount(amount) == expected


def test_search_preview_formats_money_without_rewriting_the_entry_amount(c):
    result = entry(c, "1200.5 lunch")
    assert result["label"] == "Add 1,200.50 out · lunch"
    fields = parse_qs(urlsplit(result["href"]).query)
    assert fields["amount"] == ["1200.5"]
    assert fields["kind"] == ["out"]
