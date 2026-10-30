"""One page header: a single .topbar CSS block, and the account header has one Secondary and one ⋯ (batch 004, T10)."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from lightning.ui.web import create_app

STATIC = Path(__file__).resolve().parents[1] / "lightning" / "ui" / "static"


def test_topbar_is_defined_in_one_css_block():
    for name in ("style.css", "style.rtl.css"):
        css = (STATIC / name).read_text(encoding="utf-8")
        assert len(re.findall(r"^\.topbar \{", css, flags=re.M)) == 1, name


def test_the_account_header_has_a_tile_a_figure_strip_two_secondaries_and_a_menu(c, setup):
    accounts, _ = setup
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    page = client.get(f"/accounts/{accounts['cib'].id}").text
    head = page[page.index('<div class="topbar">'):page.index('<div class="actions">')]
    start = page.index('<div class="actions">')
    actions = page[start:page.index("</details>", page.index("More actions", start))]
    assert 'class="inst-tile"' in head and "CIB Current" in head
    assert "Bank account · CIB · EGP" in head
    assert 'class="page-figures"' in head and "Balance" in head
    assert len(re.findall(r'<summary class="btn">', actions)) == 1 and "Money actions" in actions  # the Secondary menu
    assert re.search(r'<a class="btn" href="/accounts/\d+/import">Import statement</a>', actions)  # never buried in ⋯ (owner, 2026-10-30)
    assert len(re.findall(r'class="action-menu"', actions)) == 1
    assert "Import statement" not in actions.split('class="action-menu"')[1]
    for item in ("Adjust balance", "Edit account"):
        assert item in actions.split('class="action-menu"')[1]
    for item in ("Convert currency", "Change ownership", "Bought in instalments"):
        assert item in actions.split('class="action-menu"')[0]
