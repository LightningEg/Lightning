"""Register: value updates folded by default, saved views as one menu; Budget hears about a raise."""
from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def _brokerage_with_updates(c):
    account = c.account_flows.open_account("THNDR", "BROKERAGE", "2026-09-01", "10000")
    asset = c.assets.create_investment("First fund", "FUND.EQUITY", "F1")
    c.investments.add_holding(account.id, asset.id, "10", "1000", "2026-09-01")
    c.assets.set_price(asset.id, "2026-09-30", "110")
    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")
    return account


def test_value_updates_are_folded_until_asked_for(c):
    account = _brokerage_with_updates(c)
    client = TestClient(create_app(c))
    folded = client.get(f"/accounts/{account.id}").text
    assert "Investment revaluation" not in folded
    assert "Show value updates (1)" in folded
    shown = client.get(f"/accounts/{account.id}?val=1").text
    assert "Investment revaluation" in shown and "Hide value updates" in shown
    assert c.reporting.register_value_updates(account.id, "0001-01-01", "9999-12-31") == 1


def test_accounts_without_value_updates_show_no_toggle(c, setup):
    accounts, _ = setup
    page = TestClient(create_app(c)).get(f"/accounts/{accounts['cib'].id}").text
    assert "value updates" not in page


def test_saved_views_are_one_menu_with_the_name_field_inside(c, setup):
    accounts, _ = setup
    view_id = c.saved_views.save("All time", {"preset": "all_time"}, accounts["cib"].id)
    page = TestClient(create_app(c)).get(f"/accounts/{accounts['cib'].id}").text
    menu = page.split('class="action-menu views-menu', 1)[1].split("</details>", 1)[0]
    assert "<summary>Views" in menu and f"saved_view={view_id}" in menu
    assert 'name="name"' in menu and "Save view" in menu
    assert page.count('name="name"') == 1 and "Open a saved view" not in page
