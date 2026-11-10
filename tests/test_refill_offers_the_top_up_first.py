"""IV-12AA2: Refill offers the modest amount first and says what Home will show. Mohab's year offered "Refill
117,786 · Safe to spend is 897" as the filled button; owner, 2026-11-10: the plan's monthly top-up first, the full
safe amount under "Move more", and six months is the aim on Reserves and on Limits alike."""
from __future__ import annotations

import re
from decimal import Decimal as D

from fastapi.testclient import TestClient

from lightning.core.dates import today
from lightning.planning.health import EMERGENCY_FUND_MONTHS
from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app


def test_the_filled_button_is_the_top_up_and_below_safe_to_spend(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-21")
    load_mohab_2026(c)
    safe_now = c.forecaster.forecast(today()).safe_to_spend
    with TestClient(create_app(c)) as client:
        page = client.get("/plan/reserves").text
        limits = client.get("/settings?section=financial-health").text
    prompt = page.split('class="refill-prompt"', 1)[1]
    filled = D(re.search(r'btn primary small">Refill ([\d,]+)', prompt).group(1).replace(",", ""))
    more = prompt.split('id="refill-more"', 1)[1]
    bigger = D(re.search(r'btn small">Refill ([\d,]+)</button>', more).group(1).replace(",", ""))
    assert 0 < filled < safe_now < bigger                     # the gap is larger than Safe to spend
    assert "Safe to spend after:" in prompt
    assert EMERGENCY_FUND_MONTHS == 6 and "The aim is six" in page
    assert "At least 6 months" in limits
