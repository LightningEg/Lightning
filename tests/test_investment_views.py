"""Investments: the five holdings views, the By currency breakdown, the USD lens and the exchange-rate share of the gain
(design 2026-10-15 section 9). Every view regroups the same rows, so each one adds up to Holdings value."""
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from lightning.core.ledger import Effect, PostingLine
from lightning.core.refs import DocType
from lightning.database.currencies import CurrencyRegistry
from lightning.investments import views
from lightning.ui.routes import investments as routes
from lightning.ui.web import create_app

from tests.test_currency_honesty import _dollar_etf

PERIOD = "period=custom&date_from=2026-09-01&date_to=2026-12-31"


def _foreign(c, accounts, code, mic, rate, name):
    """A broker in `code` holding 10 units of one stock listed on `mic`, bought at 100 and now worth 120."""
    CurrencyRegistry(c.db).register(code)
    c.fx.save(code, "2026-09-01", str(rate))
    broker = c.account_flows.open_account(f"{code} broker", "BROKERAGE", "2026-09-01", "0", currency=code,
                                          opening_balance_date="2026-09-01")
    c.transactions.record_conversion("2026-09-02", accounts["cib"].id, broker.id, str(rate * 1100), "1100")
    asset = c.assets.create_investment(name, "STOCK", name[:4].upper(), mic=mic)
    cash = c.assets.cash_asset(code)
    c.transactions.post(DocType.BUY, "2026-09-03", [
        PostingLine.cash(broker.id, cash.id, D("-1000"), Effect.INTERNAL, fx_rate=D(rate)),
        PostingLine.units(broker.id, asset.id, D("10"), D("1000"), Effect.INTERNAL, D(rate), fx_rate=D(rate))])
    c.assets.set_price(asset.id, "2026-12-30", "120")
    c.fx.save(code, "2026-12-30", str(rate + 1))
    return broker, asset


@pytest.fixture
def book(c, setup):
    """Pounds at two brokers (one stock in both), a gold fund, a dollar ETF and a riyal stock."""
    accounts, cats = setup
    c.transactions.record_inflow("2026-09-01", accounts["cib"].id, "100000",
                                 cats["EXP.WORK.SALARY"].id, description="Funding for view fixtures")
    second = c.account_flows.open_account("Second broker", "BROKERAGE", "2026-09-01", "0", institution="Second")
    c.transactions.record_transfer("2026-09-02", accounts["cib"].id, accounts["thndr"].id, "30000")
    c.transactions.record_transfer("2026-09-02", accounts["cib"].id, second.id, "20000")
    comi = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI", mic="XCAI")
    gold = c.assets.create_investment("AZ Gold Fund", "FUND.GOLD", "AZ Gold")
    c.investments.buy("2026-09-10", accounts["thndr"].id, comi.id, "100", "95")
    c.investments.buy("2026-09-11", second.id, comi.id, "50", "96")
    c.investments.buy("2026-09-12", accounts["thndr"].id, gold.id, "10", "100")
    c.assets.set_price(comi.id, "2026-12-30", "110")
    c.assets.set_price(gold.id, "2026-12-30", "120")
    dollar_broker, etf = _dollar_etf(c, accounts)
    c.fx.save("USD", "2026-12-30", "53")
    c.assets.set_price(etf.id, "2026-12-30", "62")
    riyal_broker, _ = _foreign(c, accounts, "SAR", "XSAU", 13, "Al Rajhi Bank")
    return SimpleNamespace(accounts=accounts, second=second, comi=comi, gold=gold, etf=etf,
                           dollar_broker=dollar_broker, riyal_broker=riyal_broker)


def _page(c, monkeypatch, query=""):
    seen = {}
    real = getattr(routes.render, "_real", routes.render)

    def spy(request, name, **context):
        seen.update(context)
        return real(request, name, **context)

    spy._real = real
    monkeypatch.setattr(routes, "render", spy)
    response = TestClient(create_app(c)).get(f"/investments?{PERIOD}&{query}")
    assert response.status_code == 200
    seen["html"] = response.text
    return seen


@pytest.mark.parametrize("view", views.VIEWS)
def test_every_view_adds_up_to_holdings_value(c, book, monkeypatch, view):
    ctx = _page(c, monkeypatch, f"view={view}")
    groups = ctx["holding_groups"]
    assert ctx["view"] == view
    assert sum(g["value"] for g in groups) == ctx["holdings_total"] > 0
    assert sum(g["cost"] for g in groups) == sum(g["cost"] for g in _page(c, monkeypatch)["holding_groups"])
    assert abs(sum(g["weight"] for g in groups) - 100) < D("0.01")
    for g in groups:
        assert g["value"] == sum(r["value"] for r in g["rows"])


def test_an_unknown_view_is_by_class(c, book, monkeypatch):
    assert _page(c, monkeypatch, "view=nonsense")["view"] == "class"


def test_currency_view_lists_each_currency_separately(c, book, monkeypatch):
    names = {g["name"] for g in _page(c, monkeypatch, "view=currency")["holding_groups"]}
    assert {"EGP", "USD", "SAR"} <= names


def test_security_view_merges_one_asset_held_in_two_accounts(c, book, monkeypatch):
    groups = {g["name"]: g for g in _page(c, monkeypatch, "view=security")["holding_groups"]}
    comi = groups["COMI"]
    assert len(comi["rows"]) == 2 and {r["h"].account_label for r in comi["rows"]} == {"THNDR", "Second broker"}
    assert comi["value"] == D("150") * D("110")


def test_account_view_is_one_group_per_account_and_a_pocket_rolls_into_its_broker(c, book, monkeypatch):
    names = {g["name"] for g in _page(c, monkeypatch, "view=account")["holding_groups"]}
    assert {"THNDR", "Second broker", "US broker", "SAR broker"} <= names
    # a pocket (accounts.parent_id) is grouped under its broker
    pocket = SimpleNamespace(id=2, name="USD pocket", parent_id=1)
    broker = SimpleNamespace(id=1, name="IBKR", parent_id=None)
    row = {"h": SimpleNamespace(asset_id=7, account_id=2, asset_name="X", account_label="USD pocket"),
           "value": D(10), "cost": D(8), "gain": D(2)}
    group = views.regroup("account", [{"name": "Stock", "rows": [row]}], D(10), accounts={1: broker, 2: pocket},
                          assets={7: SimpleNamespace(currency="USD", mic=None)}, base="EGP")
    assert [g["name"] for g in group] == ["IBKR"]


def test_market_view_names_the_venue_or_the_kind_and_caps_at_four_and_other(c, book, monkeypatch):
    names = [g["name"] for g in _page(c, monkeypatch, "view=market")["holding_groups"]]
    assert {"EGX", "Funds", "Saudi Exchange"} <= set(names)
    rows = [{"h": SimpleNamespace(asset_id=i, account_id=1, asset_name=f"S{i}", account_label="A"),
             "value": D(10 + i), "cost": D(10), "gain": D(1)} for i in range(7)]
    mics = ["XCAI", "XNAS", "XNYS", "XLON", "XETR", "XPAR", "XSAU"]
    groups = views.regroup("market", [{"name": "Stock", "rows": rows}], D(100), accounts={},
                           assets={i: SimpleNamespace(currency="EGP", mic=mics[i]) for i in range(7)}, base="EGP")
    # NYSE, Nasdaq... : five or more names show four, then Other
    assert len(groups) == 5 and groups[-1]["name"] == "Other"
    assert sum(g["value"] for g in groups) == sum(r["value"] for r in rows)


def test_by_currency_card_counts_cash_and_shows_what_is_not_in_pounds(c, book, monkeypatch):
    ctx = _page(c, monkeypatch)
    card = ctx["currency_card"]
    labels = [r["label"] for r in card["rows"]]
    assert "EGP" in labels and "USD" in labels and "SAR" in labels
    holdings = ctx["holdings_total"]
    cash = ctx["investment_report"]["investment_cash"]
    assert card["total"] == holdings + cash
    egp = next(r for r in card["rows"] if r["label"] == "EGP")
    assert card["abroad"] == card["total"] - egp["value"] > 0
    assert "By currency" in ctx["html"] and "Not in EGP" in ctx["html"]


def test_by_currency_shows_four_then_other():
    card = views.by_currency({"EGP": D(100), "USD": D(90), "SAR": D(80), "AED": D(70), "QAR": D(60), "KWD": D(50)},
                             {"USD": D(10)}, "EGP")
    assert [r["label"] for r in card["rows"]] == ["EGP", "USD", "SAR", "AED", "Other"]
    assert card["rows"][-1]["value"] == D(110) and sum(r["value"] for r in card["rows"]) == card["total"]


def test_the_usd_lens_divides_by_the_dated_rate(c, book, monkeypatch):
    plain = _page(c, monkeypatch)
    lens = _page(c, monkeypatch, "lens=usd")
    rate = c.reporting.valuer.fx("USD", "2026-12-31").rate
    assert lens["lens"]["usd"] and lens["lens"]["rate"] == rate and lens["lens"]["code"] == "USD"
    assert sum(g["value"] for g in lens["holding_groups"]) == plain["holdings_total"] / rate
    assert lens["hero_value"] == plain["value_spark"]["latest"] / rate
    assert lens["hero_result"] == plain["investment_report"]["result"] / rate
    assert "at 1 USD = 53.00 EGP" in lens["html"]
    # nothing stored changes: the plain page is still in pounds
    assert plain["lens"]["code"] == "EGP" and not plain["lens"]["usd"]
    # the toggle keeps the view and the period
    assert "view=account" in _page(c, monkeypatch, "lens=usd&view=account")["lens"]["egp_link"]


def test_the_usd_lens_is_hidden_without_a_dollar_rate(c, setup, monkeypatch):
    accounts, _ = setup
    comi = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI", mic="XCAI")
    c.transactions.record_transfer("2026-09-02", accounts["cib"].id, accounts["thndr"].id, "30000")
    c.investments.buy("2026-09-10", accounts["thndr"].id, comi.id, "100", "95")
    c.assets.set_price(comi.id, "2026-12-30", "110")
    ctx = _page(c, monkeypatch, "lens=usd")
    assert not ctx["lens"]["available"] and not ctx["lens"]["usd"] and ctx["lens"]["code"] == "EGP"
    assert ">USD</a>" not in ctx["html"]


def test_the_exchange_rate_share_of_the_gain_is_the_sum_of_fx_parts(c, book, monkeypatch):
    ctx = _page(c, monkeypatch)
    parts = [r["fx_part"] for r in ctx["investment_report"]["holdings"] if r.get("fx_part") is not None]
    assert parts and ctx["fx_gain"] == sum(parts) != 0
    assert "came from exchange rates" in ctx["html"]


def test_no_exchange_rate_line_for_a_pound_only_portfolio(c, setup, monkeypatch):
    accounts, _ = setup
    comi = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI", mic="XCAI")
    c.transactions.record_transfer("2026-09-02", accounts["cib"].id, accounts["thndr"].id, "30000")
    c.investments.buy("2026-09-10", accounts["thndr"].id, comi.id, "100", "95")
    c.assets.set_price(comi.id, "2026-12-30", "110")
    ctx = _page(c, monkeypatch)
    assert ctx["fx_gain"] == 0 and "came from exchange rates" not in ctx["html"]


@pytest.mark.parametrize("view", views.VIEWS)
def test_each_view_and_the_lens_render_on_pc_and_phone(c, book, view):
    client = TestClient(create_app(c))
    for query in (f"view={view}", f"view={view}&lens=usd"):
        assert client.get(f"/investments?{PERIOD}&{query}").status_code == 200
        assert client.get(f"/investments?{PERIOD}&{query}", headers={"user-agent": "Mozilla/5.0 (iPhone)"}).status_code == 200


def test_the_usd_lens_keeps_every_percentage(c, setup):
    """Gain and what it is a return on are both divided, so returns read the same in either lens."""
    from decimal import Decimal
    from lightning.investments.views import in_lens
    groups = [{"name": "Stocks", "value": Decimal(120), "cost": Decimal(100), "gain": Decimal(20),
               "invested": Decimal(100), "rows": [{"cost": Decimal(100), "value": Decimal(120), "gain": Decimal(20),
                                                   "invested": Decimal(100)}]}]
    out = in_lens(groups, Decimal(50))
    assert out[0]["gain"] / out[0]["invested"] == Decimal("0.2")
    assert out[0]["rows"][0]["gain"] / out[0]["rows"][0]["invested"] == Decimal("0.2")
