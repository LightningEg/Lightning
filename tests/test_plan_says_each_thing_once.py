"""IV-12Z2: Cash planning says each thing once. A late bill is a Needs you row only (not again in "The next 30
days"), the Lead is not a card inside a card, and Zakat day sits in the forecast."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app


def test_a_late_bill_is_listed_once_and_the_lead_holds_no_card(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-20")
    load_mohab_2026(c)
    page = TestClient(create_app(c)).get("/plan").text
    from lightning.core.dates import today
    from lightning.planning.bill_state import late_payments
    late = {p.item.name for p in late_payments(c.planning, today())}
    assert late, "the sample has late bills on this day"
    # IV-12AA5: four late bills are one Needs you row that opens Catch up, not a row each.
    assert f"{len(late)} payments are late" in page and 'href="/plan/catch-up"' in page
    # NF-7AR: the next payments are the Upcoming calendar; the 30-day table is gone.
    assert 'id="plan-next"' in page and 'class="pay-cal"' in page and "The next 30 days" not in page
    lead = page.split('class="card lead-card', 1)[1].split("</section>", 1)[0]
    assert 'class="card' not in lead and 'id="afford-h"' not in lead
    assert "afford" not in page
