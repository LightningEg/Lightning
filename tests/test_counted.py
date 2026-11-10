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
