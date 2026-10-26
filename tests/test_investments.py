"""Investments: buy, sell, dividends, holdings, prices, and the net-worth equation with revaluation."""

import random
import re
from decimal import Decimal

import pytest

from lightning.core.errors import ConflictError, ValidationError
from lightning.core.money import ZERO
from lightning.transactions.domain import TxnFilter
from lightning.investments.report import build_investment_report
from fastapi.testclient import TestClient
from lightning.ui.web import create_app

D = Decimal


@pytest.fixture
def inv(c, setup):
    accounts, cats = setup
    comi = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI")
    gold_fund = c.assets.create_investment("AZ Gold Fund", "FUND.GOLD", "AZ Gold")
    c.transactions.record_transfer("2026-09-02", accounts["cib"].id, accounts["thndr"].id, "30000")
    return c, accounts, cats, comi, gold_fund


def pos(c, account_id, asset_id, as_of="2026-12-31"):
    return next(p for p in c.investments.portfolio(as_of, account_id).positions if p.asset_id == asset_id)


class TestAssets:
    def test_codes_and_defaults(self, c):
        comi = c.assets.create_investment("Commercial International Bank", "STOCK", "comi")
        assert comi.code == "STK:COMI" and comi.unit == "share" and comi.quantity_decimals == 0
        fund = c.assets.create_investment("AZ Gold Fund", "FUND.GOLD", "AZ Gold")
        assert fund.code == "FND:AZ-GOLD" and fund.exposure.value == "GOLD"
        gold = c.assets.create_investment("Gold 21K", "GOLD", karat="21")
        assert gold.code == "GLD:21K" and gold.purity == D("0.875") and gold.unit == "gram"
        with pytest.raises(ConflictError):
            c.assets.create_investment("CIB again", "STOCK", "COMI")
        with pytest.raises(ValidationError):
            c.assets.create_investment("X", "CASH", "X")

    def test_prices(self, c):
        comi = c.assets.create_investment("CIB", "STOCK", "COMI")
        c.assets.set_price(comi.id, "2026-09-10", "95.5")
        c.assets.set_price(comi.id, "2026-09-10", "96")  # same day replaces
        assert [p.price for p in c.assets.price_history(comi.id)] == [D("96")]
        with pytest.raises(ValidationError):
            c.assets.set_price(comi.id, "2027-01-01", "1")  # future
        with pytest.raises(ValidationError):
            c.assets.set_price(comi.id, "2026-09-10", "0")


class TestTrades:
    def test_brokerage_breakdown_groups_level_two_classes_by_weight_and_ownership(self, inv):
        c, accounts, _, stock, gold_fund = inv
        account_id = accounts["thndr"].id
        buy_stock = c.investments.buy_total("2026-09-10", account_id, stock.id, "10", "1000")
        c.money_from_others.sync_investment(buy_stock.id, buy_stock.date, "Dad", account_id, stock.id, D("4"))
        c.investments.buy_total("2026-09-11", account_id, gold_fund.id, "20", "2000")
        c.assets.set_price(stock.id, "2026-09-30", "110")
        c.assets.set_price(gold_fund.id, "2026-09-30", "120")
        c.money_from_others.record("2026-09-12", "Dad", account_id, D("500"))

        rows = c.reporting.account_asset_class_breakdown(account_id, "2026-09-30")
        by_name = {row["name"]: row for row in rows}

        assert [row["name"] for row in rows] == ["Brokerage Cash", "Gold Fund", "Stocks"]
        assert by_name["Brokerage Cash"]["total"] == D("27000")
        assert by_name["Brokerage Cash"]["held"] == D("500")
        assert by_name["Stocks"]["total"] == D("1100")
        assert by_name["Stocks"]["held"] == D("440")
        assert by_name["Gold Fund"]["total"] == D("2400")
        assert sum((row["total"] for row in rows), D("0")) == c.reporting.account_value(account_id, "2026-09-30")
        assert sum((row["held"] for row in rows), D("0")) == D("940")
        assert sum((row["weight_total"] for row in rows), D("0")) == D("100")
        assert sum((row["weight_yours"] for row in rows), D("0")) == D("100")
        assert sum((row["weight_held"] for row in rows), D("0")) == D("100")

    def test_fees_can_be_added_outside_the_entered_trade_total(self, inv):
        c, accounts, _, comi, _ = inv
        account = accounts["thndr"].id
        c.investments.buy_total("2026-09-10", account, comi.id, "10", "1000", fees="25",
                                fees_included=False)
        assert pos(c, account, comi.id).cost_basis == D("1025")
        c.investments.sell_total("2026-09-20", account, comi.id, "2", "300", fees="10",
                                 fees_included=False)
        assert c.reporting.account_balance(account) == D("30000") - D("1025") + D("290")

    def test_portfolio_and_holding_show_xirr_from_dated_cashflows(self, inv):
        c, accounts, _, comi, _ = inv
        account = accounts["thndr"].id
        c.investments.buy_total("2026-09-10", account, comi.id, "10", "1000")
        c.assets.set_price(comi.id, "2026-09-25", "110")
        portfolio = c.investments.portfolio("2026-09-25", account)
        holding = next(row for row in portfolio.positions if row.asset_id == comi.id)
        assert portfolio.xirr is not None and portfolio.xirr > 0
        assert holding.xirr == portfolio.xirr

    def test_buy_is_a_conversion_at_cost(self, inv):
        c, accounts, _, comi, _ = inv
        thndr = accounts["thndr"].id
        t = c.investments.buy("2026-09-10", thndr, comi.id, "100", "95", fees="50")
        assert t.ref == "BUY-2026-09-10-001"
        assert c.reporting.account_balance(thndr) == D("30000") - D("9550")  # cash only
        p = pos(c, thndr, comi.id)
        assert (p.quantity, p.cost_basis, p.average_cost) == (D("100"), D("9550"), D("95.5"))
        assert p.price == D("95") and p.price_source == "TRADE" and p.value == D("9500")
        assert p.unrealized == D("-50")  # the fee
        assert c.reporting.account_value(thndr, "2026-12-31") == D("20450") + D("9500")

    def test_sell_realizes_gain_on_average_cost(self, inv):
        c, accounts, _, comi, _ = inv
        thndr = accounts["thndr"].id
        c.investments.buy("2026-09-10", thndr, comi.id, "100", "95", fees="50")
        c.investments.buy("2026-09-15", thndr, comi.id, "100", "105")  # avg now (9550+10500)/200 = 100.25
        c.investments.sell("2026-09-20", thndr, comi.id, "50", "110", fees="25")
        p = pos(c, thndr, comi.id)
        assert p.quantity == D("150")
        assert p.cost_basis == D("15037.50")  # 150 × 100.25
        assert p.realized == D("5500") - D("25") - D("5012.50")  # proceeds − cost removed
        assert p.price == D("110") and p.value == D("16500")

    def test_cannot_sell_what_you_do_not_hold(self, inv):
        c, accounts, _, comi, _ = inv
        thndr = accounts["thndr"].id
        c.investments.buy("2026-09-10", thndr, comi.id, "10", "95")
        with pytest.raises(ValidationError, match="less than zero"):
            c.investments.sell("2026-09-12", thndr, comi.id, "11", "100")
        with pytest.raises(ValidationError, match="less than zero"):
            c.investments.sell("2026-09-09", thndr, comi.id, "5", "100")  # before the buy
        sale = c.investments.sell("2026-09-12", thndr, comi.id, "10", "100")
        buy_id = c.transactions.find(TxnFilter(search="BUY-"))[0][0].id
        with pytest.raises(ValidationError, match="less than zero"):
            c.transactions.void(buy_id)  # the later sale would have nothing to sell
        c.transactions.void(sale.id)
        c.transactions.void(buy_id)
        assert c.investments.holding(thndr, comi.id) == ZERO

    def test_gold_bought_with_wallet_cash(self, c, setup):
        accounts, _ = setup
        home = c.account_flows.open_account("Gold at home", "PHYSICAL_ASSET", "2026-09-01")
        gold = c.assets.create_investment("Gold 21K", "GOLD", karat="21")
        with pytest.raises(ValidationError, match="comes from"):
            c.investments.buy("2026-09-10", home.id, gold.id, "10", "4000")
        c.investments.buy("2026-09-10", home.id, gold.id, "10.5", "4000", fees="1500",
                          cash_account_id=accounts["cib"].id)
        assert c.reporting.account_balance(accounts["cib"].id) == D("50000") - D("43500")
        p = pos(c, home.id, gold.id)
        assert p.quantity == D("10.5") and p.cost_basis == D("43500") and p.value == D("42000")
        with pytest.raises(ValidationError, match="decimal"):
            c.investments.buy("2026-09-10", home.id, gold.id, "1.2345", "4000", cash_account_id=accounts["cib"].id)

    def test_only_investment_accounts_hold_investments(self, inv):
        c, accounts, _, comi, _ = inv
        with pytest.raises(ValidationError, match="brokerage"):
            c.investments.buy("2026-09-10", accounts["cib"].id, comi.id, "1", "95")

    def test_dividends_are_investment_income_per_holding(self, inv):
        c, accounts, _, comi, _ = inv
        thndr = accounts["thndr"].id
        c.investments.buy("2026-09-10", thndr, comi.id, "100", "95")
        d = c.investments.dividend("2026-09-28", thndr, comi.id, "250")
        assert d.type == "DIV" and d.counterparty == comi.name
        flow = c.reporting.cash_flow("2026-09-01", "2026-09-30")
        assert flow.investment_inflows == D("250") and flow.household_inflows == ZERO
        p = pos(c, thndr, comi.id)
        assert p.dividends == D("250") and p.total_return == D("250")

    def test_traceable_report_counts_boundary_money_and_sale_gain_once(self, inv):
        from lightning.investments.report import build_investment_report
        c, accounts, _, comi, _ = inv
        bank = c.account_flows.open_account("Report Bank", "BANK", "2025-01-01", "5000")
        broker = c.account_flows.open_account("Report Brokerage", "BROKERAGE", "2025-01-01")
        c.transactions.record_transfer("2025-10-01", bank.id, broker.id, "100")
        c.investments.buy("2025-12-01", broker.id, comi.id, "10", "10")
        c.assets.set_price(comi.id, "2025-12-31", "12")
        c.transactions.record_transfer("2026-01-02", bank.id, broker.id, "1000")
        c.investments.sell("2026-01-10", broker.id, comi.id, "4", "12")
        c.investments.dividend("2026-01-12", broker.id, comi.id, "3")
        c.transactions.record_transfer("2026-01-15", broker.id, bank.id, "3")
        report = build_investment_report(c.db, c.accounts, c.assets, c.reporting,
                                         "2026-01-01", "2026-01-31")
        assert report["new_money"] == D("1000")  # deposit counted once; purchase stays inside
        assert report["withdrawn"] == D("3")
        assert report["realized"] == D("8")  # 48 net proceeds − 40 average cost
        assert report["dividends"] == D("3")
        assert report["unrealized"] == D("12")

    def test_traceable_report_excludes_tagged_custody_and_values_unpriced_holdings_at_cost(self, inv):
        from lightning.investments.report import build_investment_report
        c, accounts, _, stock, _ = inv
        buy = c.investments.add_holding(accounts["thndr"].id, stock.id, "10", "950", "2026-09-10")
        c.money_from_others.sync_investment(buy.id, buy.date, "Dad", accounts["thndr"].id, stock.id, D("4"))
        report = build_investment_report(c.db, c.accounts, c.assets, c.reporting,
                                         "2026-01-01", "2026-09-28")
        owned = next(row for row in report["holdings"] if row["asset"] == stock.name)
        assert owned["units"] == D("6")
        assert owned["cost"] == D("570")
        # No price yet: counted at what was paid (no gain), flagged, and the result stays available.
        # The 5,000 left as cash in the legacy CD account is a deposit, and deposits are holdings.
        assert report["value"] == D("5570") and report["unrealized"] == ZERO
        assert [item["asset"] for item in report["at_cost"]] == [stock.name] and not report["missing"]

    def test_traceable_report_counts_direct_physical_purchase_as_new_money(self, inv):
        from lightning.investments.report import build_investment_report
        c, accounts, _, _, _ = inv
        home = c.account_flows.open_account("Report Gold", "PHYSICAL_ASSET", "2026-09-01")
        gold = c.assets.create_investment("Report Gold 24K", "GOLD", karat="24")
        c.investments.buy("2026-09-10", home.id, gold.id, "1", "4000",
                          cash_account_id=accounts["cib"].id)
        report = build_investment_report(c.db, c.accounts, c.assets, c.reporting,
                                         "2026-09-10", "2026-09-30")
        assert report["new_money"] == D("4000")
        assert report["withdrawn"] == ZERO

    def test_existing_holding_valued_at_cost_until_priced(self, inv):
        c, accounts, _, comi, fund = inv
        thndr = accounts["thndr"].id
        c.investments.add_holding(thndr, fund.id, "1000.5", "12,000")
        p = pos(c, thndr, fund.id)
        assert p.price_source == "COST" and p.value == D("12000") and p.unrealized == ZERO
        with pytest.raises(ConflictError):
            c.investments.add_holding(thndr, fund.id, "1", "1")
        c.assets.set_price(fund.id, "2026-09-30", "13")
        p = pos(c, thndr, fund.id)
        assert p.price_source == "MANUAL" and p.value == D("13006.50") and p.unrealized == D("1006.50")
        # the cash opening balance is untouched
        assert c.transactions.opening_balance(thndr) == ZERO
        assert c.account_flows.opening_of(accounts["thndr"]) == ZERO

    def test_manual_price_wins_on_the_same_day(self, inv):
        c, accounts, _, comi, _ = inv
        thndr = accounts["thndr"].id
        c.investments.buy("2026-09-10", thndr, comi.id, "10", "95")
        c.assets.set_price(comi.id, "2026-09-10", "96")
        assert pos(c, thndr, comi.id).price == D("96")
        c.investments.buy("2026-09-11", thndr, comi.id, "10", "97")  # newer trade price wins
        assert pos(c, thndr, comi.id).price == D("97")

    def test_edit_keeps_ref_and_values_round_trip(self, inv):
        c, accounts, _, comi, _ = inv
        thndr = accounts["thndr"].id
        t = c.investments.buy("2026-09-10", thndr, comi.id, "100", "95", fees="50")
        values = c.investments.values_of(t.id)
        assert (values["quantity"], values["price"], values["fees"]) == (D("100"), D("95"), D("50"))
        edited = c.investments.update(t.id, date="2026-09-11", account_id=thndr, asset_id=comi.id, quantity="80",
                                      price="96", fees="10")
        assert edited.ref == t.ref and edited.date == "2026-09-11"
        assert pos(c, thndr, comi.id).cost_basis == D("7690")

    def test_register_shows_cash_only(self, inv):
        c, accounts, _, comi, _ = inv
        thndr = accounts["thndr"].id
        c.investments.buy("2026-09-10", thndr, comi.id, "100", "95", fees="50")
        rows = c.reporting.register(thndr, "1900-01-01", "9999-12-31")
        buy = next(r for r in rows if r.type == "BUY")
        assert buy.payment == D("9550") and "Buy 100 × STK:COMI @ 95" in buy.category_label
        assert all(r.balance is None or r.balance >= 0 for r in rows)


class TestNetWorth:
    def test_revaluation_explains_price_changes(self, inv):
        c, accounts, _, comi, _ = inv
        thndr = accounts["thndr"].id
        c.investments.buy("2026-09-10", thndr, comi.id, "100", "95", fees="50")
        c.assets.set_price(comi.id, "2026-09-30", "100")
        sep = c.reporting.bridge_for_month("2026-09")
        assert sep.revaluation == D("450")  # +500 price move, −50 fee
        assert sep.difference == ZERO
        c.assets.set_price(comi.id, "2026-10-31", "90")
        oct_ = c.reporting.bridge_for_month("2026-10")
        assert oct_.revaluation == D("-1000") and oct_.inflows == ZERO and oct_.difference == ZERO
        groups = {g.code: g.value for g in c.reporting.net_worth("2026-10-31").by_class}
        assert groups["STOCK"] == D("9000")

    def test_randomized_portfolio_always_reconciles(self, c):
        rng = random.Random(3)
        f = c.account_flows
        thndr = f.open_account("THNDR", "BROKERAGE", "2026-01-01", "200000", institution="THNDR")
        home = f.open_account("Gold at home", "PHYSICAL_ASSET", "2026-01-01")
        bank = f.open_account("Bank", "BANK", "2026-01-01", "500000")
        assets = [c.assets.create_investment(f"Stock {i}", "STOCK", f"S{i}") for i in range(3)]
        assets.append(c.assets.create_investment("Fund", "FUND.EQUITY", "F1"))
        gold = c.assets.create_investment("Gold 24K", "GOLD", karat="24")
        c.investments.add_holding(thndr.id, assets[0].id, "50", "4000", "2026-01-01")
        for _ in range(250):
            day = f"2026-{rng.randint(1, 6):02d}-{rng.randint(1, 28):02d}"
            roll = rng.random()
            asset = rng.choice(assets)
            price = D(rng.randint(500, 20000)) / 100
            try:
                if roll < 0.35:
                    c.investments.buy(day, thndr.id, asset.id, str(rng.randint(1, 40)), price, fees=str(rng.randint(0, 30)))
                elif roll < 0.55:
                    held = c.investments.holding(thndr.id, asset.id, day)
                    if held:
                        c.investments.sell(day, thndr.id, asset.id, str(rng.randint(1, int(held))), price,
                                           fees=str(rng.randint(0, 5)))
                elif roll < 0.7:
                    c.assets.set_price(asset.id, day, price)
                elif roll < 0.8:
                    c.investments.buy(day, home.id, gold.id, f"{rng.randint(1, 20)}.{rng.randint(0, 999):03d}",
                                      D(rng.randint(300000, 500000)) / 100, fees="100", cash_account_id=bank.id)
                elif roll < 0.9:
                    c.investments.dividend(day, thndr.id, asset.id, str(rng.randint(1, 500)))
                else:
                    c.assets.set_price(gold.id, day, D(rng.randint(300000, 500000)) / 100)
            except ValidationError:
                continue  # e.g. a sale dated before the units were bought
        for month in ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]:
            b = c.reporting.bridge_for_month(month)
            assert b.difference == ZERO, month
        # net worth = cash + every holding at its price
        nw = c.reporting.net_worth("2026-06-30")
        portfolio = c.investments.portfolio("2026-06-30")
        cash = sum((c.reporting.account_balance(a.id, "2026-06-30") for a in (thndr, home, bank)), ZERO)
        assert nw.total == cash + portfolio.value
        assert not nw.unvalued


class TestInvestmentPages:
    def test_holdings_table_shows_every_figure_in_its_own_column(self, c, setup):
        # Owner, 2026-10-06: more columns (units, average cost, price, share, return, XIRR), and no lines
        # or fold-outs under the names.
        from fastapi.testclient import TestClient
        from lightning.ui.web import create_app

        accounts, _ = setup
        asset = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI")
        c.investments.add_holding(accounts["thndr"].id, asset.id, "10", "950", "2025-09-10")
        c.assets.set_price(asset.id, "2026-09-30", "100")

        page = TestClient(create_app(c)).get("/investments?period=month&month=2026-09").text
        table = page.split('id="holdings-table"', 1)[1].split("</table>", 1)[0]
        headers = re.findall(r"<th\b", table.split("<thead>", 1)[1].split("</thead>", 1)[0])
        rows = re.findall(r"<tr\b[^>]*>.*?</tr>", table, re.S)

        assert [re.sub(r"<[^>]+>", "", h) for h in re.findall(r"<th\b[^>]*>(.*?)</th>", table.split("</thead>", 1)[0])] == [
            "Investment", "Cost", "Value", "Total gain", "Total return"]  # five columns (3.33, A11)
        assert len(headers) == 5 and rows
        assert all(len(re.findall(r"<(?:th|td)\b", row)) == 5 for row in rows)
        assert "Holding details" not in table and 'class="small muted"' not in table
        row = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", rows[-1]))
        assert "Commercial International Bank" in table and "950 1,000" in row and "+5.3%" in row
        assert "<small" not in table and "<form" not in table and "data-horizon-edit" not in table
        assert 'data-holdings-group' in page and 'holdings-views' not in page
        picker = page.split('data-holdings-group', 1)[1].split('</select>', 1)[0]
        assert picker.count('<option') == 5
        assert 'data-submit-on-change' in page and 'action="/investments" method="get"' in page
        assert 'name="period" value="month"' in page and 'name="month" value="2026-09"' in page
        assert 'window.location.assign(event.target.value)' not in page
        assert all(label in picker for label in ('By class', 'By account', 'By currency', 'By market', 'By security'))

    def test_full_investing_flow(self, c, setup):
        from fastapi.testclient import TestClient
        from lightning.ui.web import create_app
        accounts, _ = setup
        client = TestClient(create_app(c))
        thndr = accounts["thndr"]
        c.transactions.record_transfer("2026-09-02", accounts["cib"].id, thndr.id, "20000")
        assert "No holdings yet" in client.get("/investments").text
        r = client.post("/investments/assets/new?then=buy", data={"name": "Commercial International Bank",
                        "class_code": "STOCK", "symbol": "COMI"})
        assert "Added Commercial International Bank." in r.text and "STK:COMI" not in r.text.split("Added")[1][:60] and "Buy" in r.text
        comi = c.assets.get_asset_by_code("STK:COMI")
        r = client.post("/investments/new?kind=buy", data={"date": "2026-09-10", "account_id": thndr.id,
                        "asset_id": comi.id, "quantity": "100", "price": "95", "fees": "50"})
        assert "Saved BUY-2026-09-10-001" in r.text  # lands on the THNDR register
        assert "Holdings" in r.text and "Commercial International Bank" in r.text and "\u22129,550" in r.text
        r = client.post("/investments/prices", data={"date": "2026-09-30", f"p_{comi.id}": "100"})
        assert "Saved 1 price input; reevaluation catch-up completed." in r.text
        assert c.investments.portfolio("2026-09-30").unrealized == D("450")
        assert "+450" in client.get("/investments?period=month&month=2026-09").text
        r = client.post("/investments/new?kind=sell", data={"date": "2026-09-30", "account_id": thndr.id,
                        "asset_id": comi.id, "quantity": "500", "price": "100"})
        assert r.status_code == 400 and "less than zero" in r.text
        buy = c.transactions.get_by_ref("BUY-2026-09-10-001")
        page = client.get(f"/investments/{buy.id}/edit")
        assert page.status_code == 200 and 'value="95' in page.text
        r = client.post(f"/investments/{buy.id}/edit", data={"date": "2026-09-10", "account_id": thndr.id,
                        "asset_id": comi.id, "quantity": "100", "price": "94", "fees": "50"})
        assert "Saved BUY-2026-09-10-001" in r.text
        r = client.post("/investments/new?kind=dividend", data={"date": "2026-09-28", "account_id": thndr.id,
                        "asset_id": comi.id, "amount": "120"})
        assert "Saved DIV-2026-09-28-001" in r.text

    @pytest.mark.parametrize("path", ["/investments", "/investments/new?kind=buy", "/investments/new?kind=sell",
                                      "/investments/new?kind=dividend", "/investments/new?kind=holding",
                                      "/investments/assets/new", "/investments/prices"])
    def test_pages_render(self, c, setup, path):
        from fastapi.testclient import TestClient
        from lightning.ui.web import create_app
        assert TestClient(create_app(c)).get(path).status_code == 200


def test_inline_investment_workflow(setup, c):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app

    accounts, _ = setup
    thndr = accounts["thndr"]
    c.transactions.record_transfer("2026-09-02", accounts["cib"].id, thndr.id, "5000")
    client = TestClient(create_app(c), follow_redirects=False)
    register = client.get(f"/accounts/{thndr.id}")
    assert register.status_code == 200
    assert "trade-instrument-search" in register.text
    assert "/investment-entry" in register.text

    buy = client.post(f"/accounts/{thndr.id}/investment-entry", data={
        "date": "2026-09-10", "instrument_key": "catalog:AALR",
        "instrument_label": "General Co. for Land Reclamation Development & Reconstruction · AALR",
        "units": "10", "total": "1050", "unit_price": "",
        "price_basis": "total", "cash_account_id": "", "notes": "",
    })
    assert buy.status_code == 303
    asset = c.assets.get_asset_by_code("STK:AALR")
    assert c.investments.holding(thndr.id, asset.id) == D("10")

    oversell = client.post(f"/accounts/{thndr.id}/investment-entry", data={
        "date": "2026-09-11", "instrument_key": f"asset:{asset.id}",
        "trade_action": "sell", "units": "11", "total": "1200", "price_basis": "total",
    })
    assert oversell.status_code == 400
    assert c.investments.holding(thndr.id, asset.id) == D("10")

    sell = client.post(f"/accounts/{thndr.id}/investment-entry", data={
        "date": "2026-09-12", "instrument_key": f"asset:{asset.id}",
        "trade_action": "sell", "units": "4", "total": "520", "price_basis": "total",
    })
    assert sell.status_code == 303
    assert c.investments.holding(thndr.id, asset.id) == D("6")
    assert c.reporting.account_balance(thndr.id, "2026-09-12") == D("4470")

    dividend = client.post(f"/accounts/{thndr.id}/investment-entry", data={
        "date": "2026-09-13", "instrument_key": f"asset:{asset.id}",
        "trade_action": "dividend", "units": "", "total": "50", "price_basis": "total",
    })
    assert dividend.status_code == 303
    assert c.investments.holding(thndr.id, asset.id) == D("6")


def test_a_fund_can_be_bought_by_amount_and_a_new_name_needs_no_extra_step(c, setup):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, cats = setup
    thndr = accounts["thndr"]
    c.transactions.record_transfer("2026-09-01", accounts["cib"].id, thndr.id, "10000")
    fund = c.assets.create_investment("Money Market Fund", "FUND.MONEY_MARKET", "MMF1")
    c.assets.set_price(fund.id, "2026-09-01", "120")
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    entry = {"price_basis": "total", "fees": "", "fees_included": "1", "trade_action": "buy",
             "instrument_key": f"asset:{fund.id}", "date": "2026-09-02"}
    response = client.post(f"/accounts/{thndr.id}/investment-entry", data={**entry, "total": "3000"})
    assert response.status_code in (200, 303)
    assert c.investments.holding(thndr.id, fund.id, "2026-09-30") == D("25")  # 3,000 ÷ the latest price 120
    saved = client.post(f"/accounts/{accounts['cib'].id}/register", data={
        "date": "2026-09-25", "counterparty": "Zzq Bakery", "category": "Food & Groceries", "amount": "-40"})
    assert saved.status_code == 200 and c.counterparties.resolve("Zzq Bakery") is not None


def test_holding_page_tells_the_journey_of_one_asset(c, setup, monkeypatch):
    from datetime import date
    from fastapi.testclient import TestClient
    from lightning.ui import visuals
    from lightning.ui.web import create_app
    monkeypatch.setenv("LIGHTNING_TODAY", "2027-06-30")
    accounts, _ = setup
    comi = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI")
    thndr = accounts["thndr"].id
    c.transactions.record_transfer("2026-09-02", accounts["cib"].id, thndr, "30000")
    c.investments.buy("2026-09-10", thndr, comi.id, "100", "100")
    for month, price in (("2026-09-30", 100), ("2026-10-31", 110), ("2026-11-30", 99), ("2026-12-31", 88),
                         ("2027-01-31", 95), ("2027-02-28", 121), ("2027-03-31", 118)):
        c.assets.set_price(comi.id, month, str(price))
    j = visuals.holding_journey(c, thndr, comi.id, date(2027, 3, 31))
    assert j["labels"][0] == "2026-09" and j["labels"][-1] == "2027-03"
    assert j["best"][0] == "2027-02" and round(j["best"][1], 1) == Decimal("27.4")
    assert j["worst"][0] == "2026-12" and round(j["worst"][1], 1) == Decimal("-11.1")  # 99 to 88
    assert round(j["max_drawdown"], 1) == -20.0  # 88 against the 110 high
    assert (j["up"], j["down"]) == (3, 3) and j["typical"] is not None
    assert not j["price"]["too_short"] and j["price"]["plan"]["value"] == 100  # average cost line
    assert [t["kind"] for t in j["trades"]] == ["Bought"]
    page = TestClient(create_app(c)).get(f"/investments/holding/{comi.id}?account={thndr}&date=2027-03-31")
    assert page.status_code == 200
    for question in ("Is it making money?", "How bumpy has it been?", "The journey", "Fall from its high"):
        assert question in page.text


class TestPlanner:
    """New money toward target allocation: spread across gaps, or biggest gaps first."""

    def split(self, values, targets, amount, mode):
        from lightning.investments.report import suggest_contributions
        return suggest_contributions({k: D(v) for k, v in values.items()}, {k: D(v) for k, v in targets.items()},
                                     D(amount), mode)

    def test_when_the_money_covers_every_gap_both_modes_land_on_target(self):
        values, targets = {"Stocks": 500, "Gold": 300, "MMF": 200}, {"Stocks": 50, "Gold": 30, "MMF": 20}
        for mode in ("prorata", "fill_gaps"):
            assert self.split(values, targets, 1000, mode) == {"Stocks": 500, "Gold": 300, "MMF": 200}

    def test_short_money_is_shared_pro_rata_or_given_to_the_biggest_gap(self):
        values, targets = {"Stocks": 7000, "Gold": 1000, "MMF": 2000}, {"Stocks": 50, "Gold": 30, "MMF": 20}
        assert self.split(values, targets, 1000, "prorata") == {"Gold": 920, "MMF": 80}  # 2300 : 200
        assert self.split(values, targets, 1000, "fill_gaps") == {"Gold": 1000}  # Gold is still the furthest behind

    def test_biggest_gaps_first_levels_classes_once_they_meet(self):
        values, targets = {"Stocks": 7500, "Gold": 1000, "MMF": 1500}, {"Stocks": 40, "Gold": 30, "MMF": 30}
        split = self.split(values, targets, 1000, "fill_gaps")
        assert split == {"Gold": 750, "MMF": 250}
        gaps = {b: targets[b] - (values[b] + split[b]) / D(11000) * 100 for b in split}
        assert gaps["Gold"] == gaps["MMF"]  # both end the same number of points below target

    def test_the_split_adds_up_to_the_cent_and_never_goes_negative(self):
        targets = {"A": D("33.33"), "B": D("33.33"), "C": D("33.34")}
        for mode in ("prorata", "fill_gaps"):
            split = self.split({"A": 0, "B": 0, "C": 0}, targets, "100", mode)
            assert sum(split.values()) == 100 and all(x > 0 for x in split.values())
            split = self.split({"A": 1, "B": 2, "C": 0}, targets, "0.01", mode)
            assert sum(split.values()) == D("0.01") and all(x > 0 for x in split.values())

    def test_partial_targets_are_scaled_without_changing_them(self):
        targets = {"Stocks": D("42"), "Gold": D("28")}
        for mode in ("prorata", "fill_gaps"):
            assert self.split({}, targets, 1000, mode) == {"Stocks": 600, "Gold": 400}
        assert targets == {"Stocks": D("42"), "Gold": D("28")}

    def test_invalid_targets_or_amount_produce_no_split(self):
        for targets in ({}, {"Gold": 0}, {"Gold": 101}, {"Gold": -10, "Stocks": 80}):
            assert self.split({"Gold": 100}, targets, 1000, "fill_gaps") == {}
        assert self.split({"Gold": 100}, {"Gold": 100}, 0, "prorata") == {}
        with pytest.raises(ValueError):
            self.split({"Gold": 100}, {"Gold": 100}, 1000, "largest")


# An account-less profile still gets a full report and a way to start.
class NoInvestmentAccounts:
    def list(self, active_only=False):
        return []


def test_empty_investment_report_has_reconciliation_and_template_fields():
    report = build_investment_report(
        None, NoInvestmentAccounts(), None, None, "2026-09-01", "2026-09-30"
    )
    assert report["net_money"] == ZERO
    assert report["unresolved_dividends"] == 0
    assert report["value"] == ZERO
    assert report["investment_cash"] == ZERO


def test_investment_page_renders_without_investment_accounts(c):
    response = TestClient(create_app(c)).get("/investments")
    assert response.status_code == 200
    assert "Add a brokerage account" in response.text


def test_short_period_return_is_plain_in_portfolio_and_holding_screens(inv, monkeypatch):
    c, accounts, _, comi, _ = inv
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-25")
    account = accounts["thndr"].id
    c.investments.buy_total("2026-09-10", account, comi.id, "10", "1000")
    c.assets.set_price(comi.id, "2026-09-25", "110")
    client = TestClient(create_app(c))
    portfolio = client.get("/investments?period=month&month=2026-09")
    holding = client.get(f"/investments/holding/{comi.id}?account={account}&date=2026-09-25")
    assert portfolio.status_code == holding.status_code == 200
    assert "after a year" not in portfolio.text and "After a full year" not in holding.text
    assert "% a year" not in holding.text
    assert "Held 15 days" in holding.text
    assert "Held 15 days" not in portfolio.text.split('id="holdings-table"', 1)[1].split("</table>", 1)[0]
    assert "+10.0" in holding.text
    assert "Not enough dated cash flows" not in holding.text


def test_planner_warns_about_partial_targets_and_preserves_saved_weights(inv):
    c, _, _, _, _ = inv
    cls = c.assets.get_class_by_code("STOCK")
    c.investments.set_target_weight("Stocks", D("70"), cls.id)
    client = TestClient(create_app(c))
    response = client.get("/investments/planner?amount=1000")
    assert response.status_code == 200
    assert "Suggestions scale them to 100%" in response.text
    assert "Suggested allocation" in response.text
    assert "Target 100" in response.text
    assert c.investments.target_weights() == {"Stocks": D("70")}


def test_phone_sale_breakdown_uses_sale_factors_and_leads_with_parent_total(inv, monkeypatch):
    c, accounts, _, comi, _ = inv
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-25")
    stock = c.assets.get_class_by_code("STOCK")
    c.investments.buy_total("2026-09-10", accounts["thndr"].id, comi.id, "10", "1000")
    c.assets.set_price(comi.id, "2026-09-25", "100")
    c.investments.set_liquidation_factor(stock.id, "50")
    app = create_app(c)

    @app.middleware("http")
    async def phone_frame(request, call_next):
        request.state.phone = True
        return await call_next(request)

    page = TestClient(app).get("/")
    assert page.status_code == 200
    child = re.search(r'<a class="phone-row"[^>]+href="/birdview/class/' + str(stock.id) +
                      r'\?[^\"]+"[^>]*>(.*?)</a>', page.text, re.S)
    assert child is not None
    text = re.sub(r"<[^>]+>", " ", child.group(1))
    assert "500" in text and "1,000" not in text
    assert page.text.index("Holdings after sale") < child.start()


def test_planner_without_any_targets_explains_the_missing_allocation(c):
    response = TestClient(create_app(c)).get("/investments/planner?amount=1000")
    assert response.status_code == 200
    assert "Set target allocation first" in response.text
    assert 'href="/settings?section=targets"' in response.text


def test_short_holding_shows_plain_return_and_positive_worst_month_is_not_rose(inv, monkeypatch):
    from lightning.ui import visuals
    c, accounts, _, asset, _ = inv
    c.investments.buy_total("2026-09-03", accounts["thndr"].id, asset.id, "10", "1000")
    c.assets.set_price(asset.id, "2026-09-30", "110")
    original = visuals.holding_journey

    def journey(*args, **kwargs):
        result = original(*args, **kwargs)
        result.update(best=("2026-09", D("10")), worst=("2026-08", D("5")))
        return result

    monkeypatch.setattr(visuals, "holding_journey", journey)
    page = TestClient(create_app(c)).get(f"/investments/holding/{asset.id}?date=2026-09-30").text
    assert "Held 27 days" in page and "% a year" not in page
    assert 'Worst month</span><b class="pos">+5.0%' in page
    # A single observed month is shown once, rather than as both best and worst.
    monkeypatch.setattr(visuals, "holding_journey", original)
    page = TestClient(create_app(c)).get(f"/investments/holding/{asset.id}?date=2026-09-30").text
    assert "Best month" not in page and "Worst month" not in page


def test_a_one_day_hold_says_day_not_days(inv, monkeypatch):
    c, accounts, _, comi, _ = inv
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-11")
    account = accounts["thndr"].id
    c.investments.buy_total("2026-09-10", account, comi.id, "10", "1000")
    c.assets.set_price(comi.id, "2026-09-11", "110")
    client = TestClient(create_app(c))
    holding = client.get(f"/investments/holding/{comi.id}?account={account}&date=2026-09-11").text
    portfolio = client.get("/investments?period=month&month=2026-09").text
    assert "Held 1 day" in holding
    assert "Held 1 day" not in portfolio.split('id="holdings-table"', 1)[1].split("</table>", 1)[0]
    assert "Held 1 days" not in holding + portfolio


def test_planner_without_targets_splits_by_the_current_mix(inv):
    from lightning.investments.report import suggest_by_current_mix
    assert suggest_by_current_mix({"Stocks": D("750"), "Gold": D("250"), "Cash": ZERO}, D("1000")) == {
        "Stocks": D("750.00"), "Gold": D("250.00")}
    split = suggest_by_current_mix({"A": D("1"), "B": D("1"), "C": D("1")}, D("100"))
    assert sum(split.values()) == D("100") and suggest_by_current_mix({}, D("100")) == {}
    c, accounts, _, comi, gold_fund = inv
    c.investments.buy_total("2026-09-10", accounts["thndr"].id, comi.id, "10", "3000")
    c.investments.buy_total("2026-09-10", accounts["thndr"].id, gold_fund.id, "10", "1000")
    c.assets.set_price(comi.id, "2026-12-31", "300")
    c.assets.set_price(gold_fund.id, "2026-12-31", "100")
    assert c.investments.target_weights() == {}
    page = TestClient(create_app(c)).get("/investments/planner?amount=4000").text
    assert 'value="4000"' in page  # the Overview passes its free cash
    assert "By your current mix" in page and "Set target allocation first" not in page
    assert "3,000" in page and "1,000" in page  # 75% and 25% of 4,000, to the classes it holds
