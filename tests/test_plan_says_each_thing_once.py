"""IV-12Z2: Cash planning says each thing once. A late bill is a Needs you row only (not again in "The next 30
days"), "Can I afford this?" is its own card rather than a card inside the Lead, and Zakat day sits in the forecast."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app


def test_a_late_bill_is_listed_once_and_the_lead_holds_no_card(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-20")
    load_mohab_2026(c)
    page = TestClient(create_app(c)).get("/plan").text
    late = set(re.findall(r"([\w'& ]+) is late", page))
    assert late, "the sample has late bills on this day"
    nxt = page.split('id="plan-next"', 1)[1].split("</section>", 1)[0]
    assert "20 Oct – 19 Nov" in nxt  # the list starts at today
    # A late planned bill is not listed again (a later instalment of it may be); a gam'eya instalment is not a Needs you
    # row, so a late one stays in the list.
    late_rows = re.findall(r'plan-payment-row is-late"><span><b>([^<]+)</b>', nxt)
    assert not set(late_rows) & {name.strip() for name in late}
    lead = page.split('class="card lead-card', 1)[1].split("</section>", 1)[0]
    assert 'class="card' not in lead and 'id="afford-h"' not in lead
    assert 'class="card wide-card afford-card"' in page
