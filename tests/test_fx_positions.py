"""Foreign money you hold (lightning/reporting/fx_positions.py): average cost per currency, unrealized and realized
FX gain, spread paid, and the rule that ties them to the ledger's own revaluation journals."""
from decimal import Decimal as D

import pytest

from lightning.database.currencies import CurrencyRegistry
from lightning.reporting.fx_positions import FxPositions, Position, month_ends

CENT = D("0.01")


@pytest.fixture
def dollars(c, setup):
    accounts, cats = setup
    CurrencyRegistry(c.db).register("USD")
    c.fx.save("USD", "2026-09-01", "48")
    accounts["usd"] = c.account_flows.open_account("Dollar savings", "BANK", "2026-09-01", "0", currency="USD",
                                                   opening_balance_date="2026-09-01")
    accounts["usd2"] = c.account_flows.open_account("Dollar wallet", "CASH", "2026-09-01", "0", currency="USD",
                                                    opening_balance_date="2026-09-01")
    return accounts, cats


def story(c, accounts, cats):
    """750 dollars bought at 48 and 49, 100 spent at 50, the rate now 51."""
    c.transactions.record_conversion("2026-09-05", accounts["cib"].id, accounts["usd"].id, "24000", "500")
    c.transactions.record_conversion("2026-09-10", accounts["cib"].id, accounts["usd"].id, "12250", "250")
    c.fx.save("USD", "2026-09-15", "50")
    c.transactions.record_outflow("2026-09-20", accounts["usd"].id, "100", cats["EXP.PERSONAL.FOOD"].id)
    c.fx.save("USD", "2026-09-30", "51")


def test_average_cost_unrealized_and_realized(c, dollars):
    accounts, cats = dollars
    story(c, accounts, cats)
    p = c.reporting.fx_positions.position("USD", "2026-09-01", "2026-09-30")
    assert (p.units, p.cost) == (D("650"), D("31416.67"))           # 36,250 less 100/750 of it
    assert p.average_rate == D("48.333338") and p.rate.rate == D("51")
    assert p.value == D("33150.00") and p.unrealized == D("1733.33")
    assert (p.realized, p.realized_total) == (D("166.67"), D("166.67"))  # 100 fetched 5,000 and cost 4,833.33


def test_realized_belongs_to_the_period_asked(c, dollars):
    accounts, cats = dollars
    story(c, accounts, cats)
    later = c.reporting.fx_positions.position("USD", "2026-09-21", "2026-09-30")
    assert (later.realized, later.realized_total) == (D("0"), D("166.67"))
    earlier = c.reporting.fx_positions.position("USD", "2026-09-01", "2026-09-19")
    assert (earlier.units, earlier.realized_total, earlier.cost) == (D("750"), D("0"), D("36250.00"))
    assert earlier.unrealized == D("1250.00")                         # 750 dollars at 50 against 36,250


def test_money_in_adds_units_at_the_days_rate_and_transfers_move_no_cost(c, dollars):
    accounts, cats = dollars
    story(c, accounts, cats)
    salary = c.categories.get_by_code("EXP.WORK.SALARY")
    c.fx.save("USD", "2026-09-25", "50.5")
    c.transactions.record_inflow("2026-09-25", accounts["usd"].id, "200", salary.id)
    before = c.reporting.fx_positions.position("USD", "2026-09-01", "2026-09-30")
    assert (before.units, before.cost) == (D("850"), D("31416.67") + D("10100.00"))
    c.transactions.record_transfer("2026-09-26", accounts["usd"].id, accounts["usd2"].id, "300")
    after = c.reporting.fx_positions.position("USD", "2026-09-01", "2026-09-30")
    assert (after.units, after.cost, after.realized_total) == (before.units, before.cost, before.realized_total)
    assert sorted((a.label, a.owned) for a in after.accounts) == [("Dollar savings", D("550")), ("Dollar wallet", D("300"))]


def test_spending_everything_resets_the_pool(c, dollars):
    accounts, cats = dollars
    c.transactions.record_conversion("2026-09-05", accounts["cib"].id, accounts["usd"].id, "4800", "100")
    c.transactions.record_conversion("2026-09-20", accounts["usd"].id, accounts["cib"].id, "100", "5000")
    p = c.reporting.fx_positions.position("USD", "2026-09-01", "2026-09-30")
    assert (p.units, p.cost, p.average_rate, p.value, p.unrealized) == (D("0"), D("0"), None, D("0"), D("0"))
    assert p.realized == D("200.00")                                  # 5,000 fetched for dollars that cost 4,800


def test_no_rate_means_no_value_not_a_wrong_one(c, dollars):
    accounts, _ = dollars
    c.transactions.record_conversion("2026-09-05", accounts["cib"].id, accounts["usd"].id, "4800", "100")
    c.db.execute("DELETE FROM fx_rates WHERE source<>'TRADE'")
    p = c.reporting.fx_positions.position("USD", "2026-09-01", "2026-09-30")
    assert p.rate.source == "TRADE"                                    # the conversion's own rate still stands
    c.db.execute("DELETE FROM fx_rates")
    p = c.reporting.fx_positions.position("USD", "2026-09-01", "2026-09-30")
    assert (p.rate, p.value, p.unrealized) == (None, None, None) and p.cost == D("4800.00")


def test_spread_paid_counts_conversions_with_a_market_rate(c, dollars):
    accounts, _ = dollars
    c.db.execute("INSERT INTO fx_rates(date,base,quote,rate_e6,source,created_at) VALUES('2026-09-05','USD','EGP',"
                 "47800000,'MARKET','2026-09-05')")
    c.transactions.record_conversion("2026-09-05", accounts["cib"].id, accounts["usd"].id, "4800", "100")
    c.transactions.record_conversion("2026-09-09", accounts["cib"].id, accounts["usd"].id, "4900", "100")  # rate is 4 days old
    p = c.reporting.fx_positions.position("USD", "2026-09-01", "2026-09-30")
    assert p.spread == D("20.00") + D("120.00") and p.conversions == 2 and p.conversions_unpriced == 0
    only_later = c.reporting.fx_positions.position("USD", "2026-09-08", "2026-09-30")
    assert only_later.spread == D("120.00") and only_later.conversions == 1


def test_series_has_value_and_cost_for_each_month_end(c, dollars):
    accounts, cats = dollars
    story(c, accounts, cats)
    p = c.reporting.fx_positions.position("USD", "2026-09-01", "2026-09-30")
    assert [pt.day for pt in p.series] == ["2026-09-30"]
    assert (p.series[0].value, p.series[0].cost) == (D("33150.00"), D("31416.67"))
    assert month_ends("2026-07-15", "2026-09-30") == ["2026-07-31", "2026-08-31", "2026-09-30"]
    assert month_ends("2026-09-02", "2026-09-17") == ["2026-09-17"]
    assert len(month_ends("2020-01-01", "2026-09-30")) == 24


def test_the_currencies_tab_shows_the_figures_with_their_names(c, dollars):
    from fastapi.testclient import TestClient

    from lightning.ui.web import create_app
    accounts, cats = dollars
    story(c, accounts, cats)
    client = TestClient(create_app(c), follow_redirects=False)
    assert "Unavailable" in client.get("/accounts/currencies").text    # the screens' today is later: the 09-30 rate is too old
    c.fx.save("USD", "2026-12-29", "51")
    page = client.get("/accounts/currencies")
    assert page.status_code == 200
    for text in ("Unrealized FX gain", "Realized FX gain", "Average rate", "Spread paid", "48.33", "33,150", "1,733",
                 "<bdi dir=\"ltr\">1 USD = 51.00 EGP</bdi>", "Dollar savings", "Value against cost"):
        assert text in page.text, text
    assert "+1,733" in page.text and "Unavailable" not in page.text
    month = client.get("/accounts/currencies", params={"period": "month", "month": "2026-09"})
    assert month.status_code == 200 and "+167" in month.text                    # realized in September
    c.settings.set("locale", "ar")
    arabic = client.get("/accounts/currencies").text
    assert "ربح فروق العملة غير المحقق" in arabic and "متوسط السعر" in arabic and "Unrealized FX gain" not in arabic.split("<script")[0]
    # The rate line is one left-to-right run inside the right-to-left page, so it never reads backwards (3A); the
    # browser turns its digits Arabic-Indic. Two decimals, not six or four.
    assert '<bdi dir="ltr">1 USD = 51.00 EGP</bdi>' in arabic and '<bdi dir="ltr">48.33</bdi>' in arabic
    assert "51.000000" not in page.text and "48.3333" not in page.text
    c.settings.set("locale", "en")
    assert client.get("/accounts/currencies", params={"period": "custom", "date_from": "x"}).status_code == 200


def test_a_rate_shows_two_decimals_and_four_when_it_is_under_one():
    from lightning.ui.web import _rate
    assert (_rate(D("51.600000")), _rate(D("48.3333333")), _rate(D("1234.5"))) == ("51.60", "48.33", "1,234.50")
    assert (_rate("0.341234"), _rate(D("0.5"))) == ("0.3412", "0.5000")  # 1 JPY = 0.3412 EGP must not become 0.34
    assert _rate("n/a") == "n/a"


def test_the_phone_shows_the_same_figures_as_rows(c, dollars):
    from fastapi.testclient import TestClient

    from lightning.ui.web import create_app
    accounts, cats = dollars
    story(c, accounts, cats)
    c.fx.save("USD", "2026-12-29", "51")
    app = create_app(c)

    async def phone(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)

    page = TestClient(phone, follow_redirects=False).get("/accounts/currencies")
    assert page.status_code == 200 and 'class="phone-appbar"' in page.text
    for text in ("Unrealized FX gain", "Average rate", "Spread paid", "33,150", "+1,733", "Dollar savings"):
        assert text in page.text, text


def test_the_convert_page_speaks_arabic(c, wallets_for_arabic):
    from fastapi.testclient import TestClient

    from lightning.ui.web import create_app
    accounts = wallets_for_arabic
    c.settings.set("locale", "ar")
    page = TestClient(create_app(c), follow_redirects=False).get(f"/accounts/{accounts['cib'].id}/convert").text
    body = page.split("</head>", 1)[1].split("<script")[0]
    assert "اللي بعتّه" in body and "اللي استلمته" in body and "You sent" not in body and "Convert money" not in body


@pytest.fixture
def wallets_for_arabic(c, dollars):
    return dollars[0]


def test_the_tab_is_empty_without_foreign_money(c, setup):
    from fastapi.testclient import TestClient

    from lightning.ui.web import create_app
    page = TestClient(create_app(c), follow_redirects=False).get("/accounts/currencies")
    assert page.status_code == 200 and "No accounts use another currency yet." in page.text


def test_four_currencies_then_other():
    def pos(code, value):
        p = Position(code)
        p.units, p.cost = D(1), D(value) - D(10)
        return p
    from types import SimpleNamespace
    rate = SimpleNamespace(rate=D(1), as_of=None)
    positions = []
    for code, value in (("USD", 900), ("EUR", 800), ("GBP", 700), ("SAR", 600), ("AED", 500), ("KWD", 400)):
        p = pos(code, value)
        p.rate = rate
        p.units = D(value)
        p.cost = D(value) - D(10)
        positions.append(p)
    head, other = FxPositions.split(positions)
    assert [p.currency for p in head] == ["USD", "EUR", "GBP", "SAR"]
    assert other.currencies == ["AED", "KWD"] and other.value == D("900") and other.unrealized == D("20")
    assert FxPositions.split(positions[:3])[1] is None


# ------------------------------------------------------------------ the rule that ties it to the ledger
def test_unrealized_plus_realized_equals_the_revaluation_journals_plus_the_change_since(c, dollars):
    """For a currency, unrealized + realized since the first holding = the sum of its FX revaluation journals
    up to the last month-end + (the change in the held units' value since then, minus what moved in or out)."""
    accounts, cats = dollars
    c.transactions.record_conversion("2026-09-05", accounts["cib"].id, accounts["usd"].id, "24000", "500")
    c.transactions.record_conversion("2026-09-10", accounts["cib"].id, accounts["usd"].id, "12250", "250")
    c.fx.save("USD", "2026-09-15", "50")
    assert c.reevaluations.process_date("2026-09-15", "MONTH_END")               # a checkpoint in the middle
    c.transactions.record_outflow("2026-09-20", accounts["usd"].id, "100", cats["EXP.PERSONAL.FOOD"].id)
    c.transactions.record_inflow("2026-09-22", accounts["usd2"].id, "40", c.categories.get_by_code("EXP.WORK.SALARY").id)
    c.fx.save("USD", "2026-09-30", "51")

    def cash_lines(upto):
        return c.db.all(
            "SELECT le.date,le.quantity_e6,le.amount_base_e6 FROM ledger_entries le JOIN transactions t "
            "ON t.id=le.transaction_id JOIN financial_assets a ON a.id=le.asset_id WHERE a.code='CASH:USD' "
            "AND le.owner_id IS NULL AND t.status='POSTED' AND t.type<>'VAL' AND le.date<=?", (upto,))

    def held(upto):
        return sum(D(r["quantity_e6"]) for r in cash_lines(upto)) / D(1_000_000)

    def flow(upto):
        return sum(D(r["amount_base_e6"]) for r in cash_lines(upto)) / D(1_000_000)

    journals = sum(D(r["return_base_e6"]) for r in c.db.all(
        "SELECT e.return_base_e6 FROM reevaluation_entries e JOIN financial_assets a ON a.id=e.asset_id "
        "JOIN transactions t ON t.id=e.journal_transaction_id WHERE a.code='CASH:USD' AND e.owner_id IS NULL "
        "AND e.price_source='FX' AND t.status='POSTED'")) / D(1_000_000)
    assert journals == D("1250.00")                                   # 750 dollars: 37,500 now against the 36,250 paid
    value_then, value_now = held("2026-09-15") * D(50), held("2026-09-30") * D(51)
    change_since = (value_now - value_then) - (flow("2026-09-30") - flow("2026-09-15"))
    p = c.reporting.fx_positions.position("USD", "2026-09-01", "2026-09-30")
    assert abs((p.unrealized + p.realized_total) - (journals + change_since)) <= CENT
    assert p.unrealized + p.realized_total == p.value - D(str(flow("2026-09-30")))   # and both equal M - N
