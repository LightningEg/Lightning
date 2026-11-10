"""IV-12AA4: a comparison with nothing says so. Mohab's year has no 2025, so the year card read "+315,749 against 0
before" in rose; and in a quarter's first month This quarter was This month again."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app


def _cards(c, monkeypatch, day):
    from lightning.ui.routes import analysis as routes
    from starlette.responses import HTMLResponse
    monkeypatch.setenv("LIGHTNING_TODAY", day)
    seen = {}

    def capture(request, template, **values):
        seen.update(values)
        return HTMLResponse("ok")
    monkeypatch.setattr(routes, "render", capture)
    with TestClient(create_app(c)) as client:
        assert client.get("/reports").status_code == 200
    return {card["label"]: card for card in seen["cards"]}


def test_one_year_of_data_has_no_change_chip_on_the_year_card(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-21")
    load_mohab_2026(c)
    cards = _cards(c, monkeypatch, "2026-10-21")
    year = cards["This year against last year"]["compare"]
    assert year["text"] == "No 2025 to compare with." and not year["figure"] and year["tone"] == "plain"
    assert "This quarter against last quarter" not in cards          # October is the quarter's first month
    month = cards["This month against last month"]["compare"]
    assert month["figure"] and "against" in month["text"]            # September has data: a real comparison
    assert "This quarter against last quarter" in _cards(c, monkeypatch, "2026-11-09")


def test_the_arabic_card_says_it_in_arabic():
    from lightning.ui.i18n import translate
    assert translate("No 2025 to compare with.", "ar") == "مفيش 2025 نقارن بيه."
