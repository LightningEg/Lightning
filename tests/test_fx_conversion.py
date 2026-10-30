"""Conversion (CNV): your own pounds become dollars. The dollars carry what they really cost, the two sides net to
zero in the profile currency, a fee is an expense, the executed rate is saved as a TRADE rate, and the cent
rounding of very large amounts never breaks the ledger."""
import random
import re
from decimal import Decimal as D

import pytest

from lightning.core.errors import ValidationError
from lightning.database.currencies import CurrencyRegistry
from lightning.fx import rate_for
from lightning.transactions.conversion import exact_lines

CENT, SIX = D("0.01"), D("0.000001")


@pytest.fixture
def wallets(c, setup):
    accounts, cats = setup
    CurrencyRegistry(c.db).register("USD")
    CurrencyRegistry(c.db).register("EUR")
    c.fx.save("USD", "2026-09-01", "48.20")
    c.fx.save("EUR", "2026-09-01", "54")
    accounts["usd"] = c.account_flows.open_account("Dollar savings", "BANK", "2026-09-01", "0", currency="USD",
                                                   opening_balance_date="2026-09-01")
    accounts["eur"] = c.account_flows.open_account("Euro savings", "BANK", "2026-09-01", "0", currency="EUR",
                                                   opening_balance_date="2026-09-01")
    return accounts, cats


def side(txn, accounts, key):
    return [ln for ln in txn.lines if ln.account_id == accounts[key].id]


def test_buying_dollars_carries_the_pound_cost_and_nets_to_zero(c, wallets):
    accounts, _ = wallets
    txn = c.transactions.record_conversion("2026-09-10", accounts["cib"].id, accounts["usd"].id, "40000", "824")
    assert txn.ref.startswith("CNV") and txn.type.value == "CNV"
    assert sum(ln.amount_base for ln in side(txn, accounts, "cib")) == D("-40000.00")
    inn = side(txn, accounts, "usd")
    assert sum(ln.amount_base for ln in inn) == D("40000.00")           # the dollars carry the pounds paid
    assert sum(ln.amount_base for ln in txn.lines) == 0
    assert inn[0].fx_rate == D("48.543689")                              # the executed rate, 6 places
    assert c.reporting.account_balance(accounts["cib"].id, "2026-09-10") == D("10000")
    assert c.reporting.account_balance(accounts["usd"].id, "2026-09-10") == D("824")
    summary = c.transactions.summarize(txn)
    assert (summary.amount, summary.currency, summary.to_amount, summary.to_currency, summary.rate) == (
        D("40000"), "EGP", D("824"), "USD", D("48.543689"))


def test_the_executed_rate_is_saved_as_a_trade_rate_and_follows_edit_and_void(c, wallets):
    accounts, _ = wallets
    txn = c.transactions.record_conversion("2026-09-10", accounts["cib"].id, accounts["usd"].id, "40000", "824")
    rate = rate_for(c.db, "USD", "EGP", "2026-09-10")
    assert (rate.source, rate.rate, rate.date) == ("TRADE", D("48.543689"), "2026-09-10")
    c.fx.save("USD", "2026-09-10", "48.40")                              # a typed rate still wins that day
    assert rate_for(c.db, "USD", "EGP", "2026-09-10").source == "MANUAL"
    c.transactions.update_conversion(txn.id, "2026-09-12", accounts["cib"].id, accounts["usd"].id, "40000", "800")
    assert not c.db.scalar("SELECT 1 FROM fx_rates WHERE source='TRADE' AND date='2026-09-10'")
    assert c.db.scalar("SELECT rate_e6 FROM fx_rates WHERE source='TRADE' AND date='2026-09-12'") == 50_000_000
    c.transactions.void(txn.id)
    assert c.db.scalar("SELECT COUNT(*) FROM fx_rates WHERE source='TRADE'") == 0
    assert c.reporting.account_balance(accounts["usd"].id, "2026-09-12") == 0
    c.transactions.restore(txn.id)
    assert c.db.scalar("SELECT COUNT(*) FROM fx_rates WHERE source='TRADE'") == 1
    assert c.reporting.account_balance(accounts["usd"].id, "2026-09-12") == D("800")


def test_a_fee_is_an_expense_in_fees_and_charges_not_part_of_the_rate(c, wallets):
    accounts, _ = wallets
    txn = c.transactions.record_conversion("2026-09-10", accounts["cib"].id, accounts["usd"].id, "40000", "824",
                                           fee="25")
    fee = [ln for ln in txn.lines if ln.effect.value == "OUTFLOW"]
    assert len(fee) == 1 and fee[0].quantity == D("-25") and fee[0].account_id == accounts["cib"].id
    assert c.categories.get(fee[0].category_id).code == "EXP.PERSONAL.FEES"
    assert c.reporting.account_balance(accounts["cib"].id, "2026-09-10") == D("9975")
    internal = [ln for ln in txn.lines if ln.effect.value == "INTERNAL"]
    assert sum(ln.amount_base for ln in internal) == 0
    assert [ln for ln in internal if ln.quantity > 0][0].fx_rate == D("48.543689")   # the fee left the rate alone
    described = c.transactions.conversion_of(txn)
    assert (described.fee, described.sent, described.received) == (D("25"), D("40000"), D("824"))


def test_selling_dollars_for_pounds_leaves_at_the_price_it_fetched(c, wallets):
    accounts, _ = wallets
    c.transactions.record_conversion("2026-09-10", accounts["cib"].id, accounts["usd"].id, "40000", "824")
    txn = c.transactions.record_conversion("2026-09-20", accounts["usd"].id, accounts["cib"].id, "500", "24300")
    out = side(txn, accounts, "usd")
    assert sum(ln.amount_base for ln in out) == D("-24300.00") and sum(ln.quantity for ln in out) == D("-500")
    assert sum(ln.amount_base for ln in txn.lines) == 0
    assert rate_for(c.db, "USD", "EGP", "2026-09-20").rate == D("48.6")
    assert c.reporting.account_balance(accounts["usd"].id, "2026-09-20") == D("324")


def test_dollars_into_euros_use_the_days_rate_on_the_sending_side(c, wallets):
    accounts, _ = wallets
    c.transactions.record_conversion("2026-09-10", accounts["cib"].id, accounts["usd"].id, "40000", "824")
    txn = c.transactions.record_conversion("2026-09-15", accounts["usd"].id, accounts["eur"].id, "100", "89.10")
    assert sum(ln.amount_base for ln in side(txn, accounts, "usd")) == -sum(
        ln.amount_base for ln in side(txn, accounts, "eur"))
    assert sum(ln.amount_base for ln in side(txn, accounts, "eur")) > 0
    assert sum(ln.amount_base for ln in txn.lines) == 0
    assert rate_for(c.db, "EUR", "USD", "2026-09-15") is not None   # a euro now has a rate in dollars too


def test_a_conversion_needs_two_currencies_and_usable_accounts(c, wallets):
    accounts, _ = wallets
    with pytest.raises(ValidationError, match="same currency"):
        c.transactions.record_conversion("2026-09-10", accounts["cib"].id, accounts["wallet"].id, "10", "10")
    with pytest.raises(ValidationError, match="different"):
        c.transactions.record_conversion("2026-09-10", accounts["usd"].id, accounts["usd"].id, "10", "10")
    with pytest.raises(ValidationError):
        c.transactions.record_conversion("2026-09-10", accounts["cib"].id, accounts["usd"].id, "0", "10")
    with pytest.raises(ValidationError, match="negative"):
        c.transactions.record_conversion("2026-09-10", accounts["cib"].id, accounts["usd"].id, "100", "2", fee="-1")
    with pytest.raises(ValidationError, match="Convert"):  # a transfer still refuses two currencies, and says where to go
        c.transactions.record_transfer("2026-09-10", accounts["cib"].id, accounts["usd"].id, "5")


def test_a_missing_reference_rate_never_blocks_buying_dollars(c, setup):
    accounts, _ = setup
    CurrencyRegistry(c.db).register("USD")
    c.fx.save("USD", "2026-01-01", "40")
    usd = c.account_flows.open_account("Dollars", "BANK", "2026-01-01", "0", currency="USD",
                                       opening_balance_date="2026-01-01")
    txn = c.transactions.record_conversion("2026-09-10", accounts["cib"].id, usd.id, "4850", "100")  # rate 8 months old
    assert rate_for(c.db, "USD", "EGP", "2026-09-10").rate == D("48.5")
    assert c.transactions.conversion_spread(txn) is None   # nothing to compare with


def test_spread_is_the_bank_cut_against_the_market_rate(c, wallets):
    accounts, _ = wallets
    c.db.execute("INSERT INTO fx_rates(date,base,quote,rate_e6,source,created_at) VALUES('2026-09-10','USD','EGP',"
                 "48200000,'MARKET','2026-09-10')")
    buy = c.transactions.record_conversion("2026-09-10", accounts["cib"].id, accounts["usd"].id, "40000", "824")
    assert c.transactions.conversion_spread(buy) == D("283.20")        # 40,000 - 824 x 48.2
    sell = c.transactions.record_conversion("2026-09-10", accounts["usd"].id, accounts["cib"].id, "100", "4800")
    assert c.transactions.conversion_spread(sell) == D("20.00")        # 100 x 48.2 - 4,800


# ------------------------------------------------------------------ the cent
def test_a_large_amount_that_no_six_place_rate_can_carry_is_split_over_two_lines():
    lines = exact_lines(1, 1, D("123456.78"), D("6000000.01"), "x")
    assert len(lines) == 2                                         # one rate of 6 places cannot give this base
    assert sum(ln.quantity for ln in lines) == D("123456.78")
    assert sum(ln.amount_base for ln in lines) == D("6000000.01")
    assert all(ln.amount_base == (ln.amount * ln.fx_rate).quantize(CENT) for ln in lines)
    assert all(ln.fx_rate == ln.fx_rate.quantize(SIX) and ln.fx_rate > 0 for ln in lines)
    assert len(exact_lines(1, 1, D("824"), D("40000.00"), "x")) == 1


def test_a_large_conversion_posts_and_nets_to_zero(c, wallets):
    accounts, _ = wallets
    big = c.account_flows.open_account("Big", "BANK", "2026-09-01", "3000000", institution="CIB")
    txn = c.transactions.record_conversion("2026-09-10", big.id, accounts["usd"].id, "2999999.99", "61999.99")
    assert sum(ln.amount_base for ln in txn.lines) == 0
    assert sum(ln.amount_base for ln in side(txn, accounts, "usd")) == D("2999999.99")
    assert c.reporting.account_balance(accounts["usd"].id, "2026-09-10") == D("61999.99")
    summary = c.transactions.summarize(txn)
    assert (summary.amount, summary.to_amount) == (D("2999999.99"), D("61999.99"))


def test_random_amounts_always_split_into_valid_lines():
    rnd = random.Random(7)
    for _ in range(400):
        units = D(rnd.randint(1, 5_000_000_00)) / 100
        base = D(rnd.randint(1, 900_000_000_00)) / 100
        for sign in (1, -1):
            lines = exact_lines(1, 1, sign * units, sign * base, "x")
            assert sum(ln.quantity for ln in lines) == sign * units
            assert sum(ln.amount_base for ln in lines) == sign * base
            assert all(ln.amount_base == (ln.amount * ln.fx_rate).quantize(CENT) for ln in lines)
            assert all(ln.fx_rate > 0 and ln.fx_rate == ln.fx_rate.quantize(SIX) for ln in lines)


# ------------------------------------------------------------------ the screens
def test_the_convert_form_saves_and_the_register_and_detail_show_both_amounts(c, wallets):
    from fastapi.testclient import TestClient

    from lightning.ui.web import create_app
    accounts, _ = wallets
    c.db.execute("INSERT INTO fx_rates(date,base,quote,rate_e6,source,created_at) VALUES('2026-09-10','USD','EGP',"
                 "48200000,'MARKET','2026-09-10')")
    client = TestClient(create_app(c), follow_redirects=False)
    cib, usd = accounts["cib"].id, accounts["usd"].id
    page = client.get(f"/accounts/{cib}/convert")
    assert page.status_code == 200 and "You sent" in page.text and "You received" in page.text
    assert "Fee" in page.text and ">Convert<" in page.text
    quote = client.get("/accounts/convert/quote", params={
        "date": "2026-09-10", "from": cib, "to": usd, "sent": "40,000", "received": "824"}).json()
    assert quote["rate"] == "48.543689" and quote["reference"] == "48.200000" and quote["direction"] == "above"
    assert quote["percent"] == "0.7" and quote["cost"] == "283.20"
    assert client.get("/accounts/convert/quote", params={"from": "x"}).json() == {}
    form = {"date": "2026-09-10", "from_account_id": str(cib), "to_account_id": str(usd), "sent": "40000",
            "received": "824", "fee": "25", "notes": "Banque Misr", "return_to": f"/accounts/{cib}"}
    assert client.post(f"/accounts/{cib}/convert", data=form).status_code == 303
    register = client.get(f"/accounts/{cib}").text
    assert "CNV" in register and "40,000" in register and "824" in register and "USD" in register
    txn = c.db.scalar("SELECT id FROM transactions WHERE type='CNV'")
    detail = client.get(f"/transactions/{txn}").text
    assert "1 USD = 48.543689 EGP" in detail and "Spread paid" in detail and "283.20" in detail
    assert f"/transactions/{txn}/convert/edit" in detail
    edit = client.get(f"/transactions/{txn}/convert/edit")
    assert edit.status_code == 200 and 'value="40000' in edit.text and "Edit conversion" in edit.text
    fixed = client.post(f"/transactions/{txn}/convert/edit", data=form | {"received": "800", "fee": ""})
    assert fixed.status_code == 303 and c.reporting.account_balance(usd, "2026-09-10") == D("800")
    bad = client.post(f"/accounts/{cib}/convert", data=form | {"to_account_id": str(accounts["wallet"].id)})
    assert bad.status_code == 400 and "same currency" in bad.text
    assert client.post(f"/transactions/{txn}/delete", data={}).status_code in (200, 303)
    assert c.db.scalar("SELECT COUNT(*) FROM fx_rates WHERE source='TRADE'") == 0


def test_conversion_preview_rejects_invalid_amounts_without_crashing(c, wallets):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, _ = wallets
    client = TestClient(create_app(c))
    params = {"date": "2026-09-10", "from": accounts["cib"].id, "to": accounts["usd"].id,
              "sent": "40000", "received": "824"}
    for field in ("sent", "received"):
        for value in ("NaN", "Infinity", "1e100", "0.000000000000000000000000000001"):
            response = client.get("/accounts/convert/quote", params=params | {field: value})
            assert response.status_code == 200 and response.json() == {}
    # Preview uses the same parser as posting, including Arabic digits.
    assert client.get("/accounts/convert/quote", params=params | {"received": "٨٢٤"}).json()["rate"] == "48.543689"


@pytest.mark.parametrize("locale", ["en", "ar"])
def test_a_rate_far_from_the_market_is_asked_once_before_it_is_saved(c, wallets, locale):
    """Audit 11 F5 (5J): 100 EGP sent and 5,000 USD received (the two amounts swapped) saved without a question,
    and its rate then valued every dollar. Now Convert asks once; pressing it again saves the rate as typed."""
    from fastapi.testclient import TestClient

    from lightning.ui.web import create_app
    accounts, _ = wallets
    cib, usd = accounts["cib"].id, accounts["usd"].id
    client = TestClient(create_app(c), follow_redirects=False)
    if locale == "ar":
        client.post("/settings/locale", data={"locale": "ar"})
    count = lambda: c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='CNV' AND status='POSTED'")
    form = {"date": "2026-09-10", "from_account_id": str(cib), "to_account_id": str(usd), "sent": "100",
            "received": "5000", "fee": "", "notes": "", "return_to": f"/accounts/{cib}"}
    asked = client.post(f"/accounts/{cib}/convert", data=form)
    assert asked.status_code == 400 and count() == 0
    if locale == "en":
        assert "below the market rate (48.2000 EGP on 2026-09-01)" in asked.text and "swapped" in asked.text
    else:
        assert "أقل من سعر السوق" in asked.text and "swapped" not in asked.text
    checked = re.search(r'name="rate_checked" value="([^"]+)"', asked.text).group(1)
    changed = client.post(f"/accounts/{cib}/convert", data=form | {"received": "4000", "rate_checked": checked})
    assert changed.status_code == 400 and count() == 0  # another rate is asked about again
    assert client.post(f"/accounts/{cib}/convert", data=form | {"rate_checked": checked}).status_code == 303
    assert count() == 1
    near = form | {"sent": "4820", "received": "100"}  # the market rate: no question
    assert client.post(f"/accounts/{cib}/convert", data=near).status_code == 303 and count() == 2
    txn = c.db.scalar("SELECT id FROM transactions WHERE type='CNV' ORDER BY id DESC LIMIT 1")
    revision = c.transactions.revision(txn)
    edit = client.post(f"/transactions/{txn}/convert/edit", data=near | {"received": "5000", "revision": revision})
    assert edit.status_code == 400 and c.transactions.conversion_of(c.transactions.get(txn)).received == 100
