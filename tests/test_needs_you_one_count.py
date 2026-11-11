"""IV-12AA3: Needs you has one count. The Overview said 17 in its heading, "Bills and payments · 7" on its one row
and "Show all 4" under it; now the heading and Show all are both the rows shown when all are open."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from lightning.samples import SAMPLE_TODAY, load_mohab_2026
from lightning.ui.web import create_app


def test_the_heading_counts_the_rows_after_show_all(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", SAMPLE_TODAY.isoformat())
    load_mohab_2026(c)
    with TestClient(create_app(c)) as client:
        page = client.get("/").text
    section = page.split('<section class="needs"', 1)[1].split("</section>", 1)[0]
    heading = int(re.search(r'id="needs-heading">[^<]*<span>· (\d+)</span>', section).group(1))
    rows = section.count('class="needs-row"')
    assert rows > 1 and heading == rows
    more = re.search(r"Show all (\d+)", section)
    assert more and int(more.group(1)) == heading
