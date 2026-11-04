"""Investments travel as command proposals with exact row effects."""
from decimal import Decimal
from uuid import uuid4

import pytest

from test_journal_finance import devices, groups  # noqa: F401
from lightning.sync.journal.codec import origin_id, unpack


def status(home, wire):
    return home.home.status(origin_id(unpack(wire)["body"]["origin"]))


def same(hd, pc):
    assert hd.store.fingerprint() == pc.store.fingerprint() == pc.adapter.fingerprint(full=True)


def uid(device, table, local_id):
    return device.adapter.uid(table, local_id)


def record(wire):
    return unpack(wire)["body"]["record"]


def account(device, name):
    return next(item for item in device.c.accounts.list() if item.name == name)


def settle(hd, pc, *wires):
    pc.sync_with(hd.home)
    for wire in wires:
        assert status(hd, wire)["status"] == "accepted", status(hd, wire)
    same(hd, pc)


def setup(hd, pc, broker="Broker"):
    """A broker with cash and one stock, opened by the replica and confirmed."""
    opened = pc.command("accounts.open", currency=None, opening_balance_date=None, owner_id=None, name=broker, account_type="BROKERAGE", opening_date="2026-01-01",
                        opening_balance="5000.00", institution="HC", last4=None, notes="")
    stock = pc.command("assets.create_investment", name="Alpha Corp", class_code="STOCK", symbol="ALPH", karat=None,
                       isin="", notes="", mic="", currency="")
    settle(hd, pc, opened, stock)
    return record(opened), record(stock)


def buy(pc, broker, stock, **changes):
    values = dict(date="2026-09-01", account_id=broker, asset_id=stock, quantity="100", total="1000.00", fees="0.00",
                  fees_included=True, cash_account_id=None, notes="", owner_id=None)
    return pc.command("investments.buy_total", **(values | changes))


def held(device, name="Broker"):
    return next(p for p in device.c.investments.portfolio("2026-09-30").positions if p.account_label == name)


def cash(device, name="Broker"):
    return device.c.reporting.account_balance(account(device, name).id)


def test_buy_price_and_sell_replay_exactly_with_reevaluation(devices):
    hd, pc = devices
    broker, stock = setup(hd, pc)
    assert cash(pc) == 5000 and pc.c.assets.get_asset_by_code("STK:ALPH").name == "Alpha Corp"
    first = buy(pc, broker, stock)
    second = pc.command("investments.buy", date="2026-09-02", account_id=broker, asset_id=stock, quantity="50", price="12.50",
                        fees="5.00", cash_account_id=None, notes="top up", owner_id=None)
    assert not pc.c.investments.portfolio("2026-09-30").positions  # Pending until the home confirms.
    settle(hd, pc, first, second)
    assert held(pc).quantity == held(hd).quantity == 150
    assert cash(pc) == cash(hd) == 5000 - 1000 - 630
    typed = pc.command("assets.set_prices", date="2026-09-15", prices=[dict(asset=stock, price="11.50")])
    sold = pc.command("investments.sell_total", date="2026-09-20", account_id=broker, asset_id=stock, quantity="40",
                      total="480.00", fees="0.00", fees_included=True, cash_account_id=None, notes="", owner_id=None)
    settle(hd, pc, typed, sold)
    assert [(p.date, p.price) for p in pc.c.assets.price_history(pc.c.assets.get_asset_by_code("STK:ALPH").id)] == [
        ("2026-09-15", Decimal("11.5"))]
    assert held(pc).quantity == held(hd).quantity == 110 and cash(pc) == cash(hd) == 3370 + 480
    assert hd.c.db.scalar("SELECT COUNT(*) FROM reevaluation_periods") == pc.c.db.scalar("SELECT COUNT(*) FROM reevaluation_periods") > 0
    price = pc.command("assets.set_price", asset_id=stock, date="2026-09-16", price="12.25")
    settle(hd, pc, price)
    gone = hd.command("assets.remove_price", asset_id=stock, date="2026-09-15")
    assert status(hd, gone)["status"] == "accepted"
    pc.sync_with(hd.home)
    assert [p.date for p in pc.c.assets.price_history(pc.c.assets.get_asset_by_code("STK:ALPH").id)] == ["2026-09-16"]
    same(hd, pc)


def test_dividend_with_tax_fee_interest_and_edit(devices):
    hd, pc = devices
    broker, stock = setup(hd, pc)
    bought = buy(pc, broker, stock)
    dividend = pc.command("investments.dividend", date="2026-09-10", account_id=broker, asset_id=stock, amount="100.00",
                          notes="Q3", owner_id=None, tax="10.00")
    fee = pc.command("investments.broker_fee", date="2026-09-11", account_id=broker, amount="25.00", notes="custody")
    interest = pc.command("investments.broker_interest", date="2026-09-12", account_id=broker, amount="7.50", notes="")
    settle(hd, pc, bought, dividend, fee, interest)
    assert cash(pc) == cash(hd) == 4000 + 90 - 25 + Decimal("7.50")
    assert pc.c.db.scalar("SELECT COUNT(*) FROM investment_dividend_assets") == 1
    # Edit the purchase through the whole form, with the home's own precondition on that transaction.
    bought_id = pc.adapter.local("transactions", record(bought))
    edit = pc.command("investments.update", txn_id=record(bought), date="2026-09-01", account_id=broker, asset_id=stock,
                      quantity="100", price="", fees="0", total_fees="0", fees_included=True, total="1100.00",
                      cash_account_id=None, amount="", total_cost="", notes="bigger", owner_id=None)
    settle(hd, pc, edit)
    assert cash(pc) == cash(hd) == 3900 + 90 - 25 + Decimal("7.50") and pc.c.transactions.get(bought_id).notes == "bigger"


def test_return_of_capital_travels_with_its_zero_unit_cost_line(devices):
    """NF-5A4: the cash line and the zero-unit cost line settle together, and the cost follows on both devices."""
    hd, pc = devices
    broker, stock = setup(hd, pc)
    bought = buy(pc, broker, stock)
    returned = pc.command("investments.return_of_capital", date="2026-09-10", account_id=broker, asset_id=stock,
                          amount="300.00", cash_account_id=None, notes="Interim", owner_id=None)
    settle(hd, pc, bought, returned)
    assert cash(pc) == cash(hd) == 4000 + 300
    assert held(pc).cost_basis == held(hd).cost_basis == 700 and held(hd).quantity == 100
    assert hd.c.db.scalar("SELECT COUNT(*) FROM ledger_entries WHERE quantity_e6=0 AND effect='INTERNAL'") == 1
    edit = pc.command("investments.update", txn_id=record(returned), date="2026-09-10", account_id=broker, asset_id=stock,
                      quantity="", price="", fees="", total_fees="", fees_included=True, total="", cash_account_id=None,
                      amount="1200.00", total_cost="", notes="Interim", owner_id=None)
    settle(hd, pc, edit)
    assert held(pc).cost_basis == held(hd).cost_basis == 0 and held(hd).realized == 200


def test_move_shares_between_brokers(devices):
    hd, pc = devices
    broker, stock = setup(hd, pc)
    other = pc.command("accounts.open", currency=None, opening_balance_date=None, owner_id=None, name="Second", account_type="BROKERAGE", opening_date="2026-01-01",
                       opening_balance="0", institution="", last4=None, notes="")
    bought = buy(pc, broker, stock)
    settle(hd, pc, other, bought)
    move = pc.command("investments.move_units", date="2026-09-05", from_account_id=broker, to_account_id=record(other),
                      asset_id=stock, quantity="60", notes="")
    settle(hd, pc, move)
    assert held(pc, "Second").quantity == held(hd, "Second").quantity == 60 and held(pc).quantity == 40
    assert held(pc, "Second").cost_basis == Decimal("600.00")


def test_pocket_currency_and_a_foreign_listing_converted_in(devices):
    hd, pc = devices
    broker, _ = setup(hd, pc)
    register = pc.command("currencies.register", code="USD", name=None)
    rate = pc.command("currencies.save_rate", currency="USD", day="2026-09-01", rate="48.5")
    pocket = pc.command("investments.add_pocket", broker_id=broker, currency="USD")
    nvda = pc.command("assets.create_investment", name="Dollar Fund", class_code="FUND.EQUITY", symbol="DLRF", karat=None,
                      isin="", notes="", mic="", currency="USD")
    settle(hd, pc, register, rate, pocket, nvda)
    assert [a.name for a in pc.c.accounts.list() if a.parent_id] == ["Broker · USD"] == [
        a.name for a in hd.c.accounts.list() if a.parent_id]
    converted = pc.command("investments.buy_converting", date="2026-09-02", account_id=broker, asset_id=record(nvda),
                           quantity="10", total="100.00", paid="4850.00", from_account_id=None, notes="", fees="0.00",
                           fees_included=True, owner_id=None)
    settle(hd, pc, converted)
    assert cash(pc) == cash(hd) == 150 and cash(pc, "Broker · USD") == 0
    assert held(pc, "Broker · USD").quantity == held(hd, "Broker · USD").quantity == 10



def test_a_separate_dollar_brokerage_joins_the_broker_as_its_pocket(devices):
    hd, pc = devices
    broker, _ = setup(hd, pc)
    register = pc.command("currencies.register", code="USD", name=None)
    dollars = pc.command("accounts.open", currency="USD", opening_balance_date=None, owner_id=None, name="Dollar brokerage",
                         account_type="BROKERAGE", opening_date="2026-01-01", opening_balance="0", institution="",
                         last4=None, notes="")
    settle(hd, pc, register, dollars)
    joined = pc.command("investments.make_pocket", account_id=record(dollars), broker_id=broker)
    settle(hd, pc, joined)
    assert [a.name for a in pc.c.accounts.list() if a.parent_id] == ["Broker · USD"] == [
        a.name for a in hd.c.accounts.list() if a.parent_id]

def test_targets_factors_and_the_investment_list(devices):
    hd, pc = devices
    broker, stock = setup(hd, pc)
    stocks = pc.c.assets.get_class_by_code("STOCK")
    cls = uid(pc, "asset_classes", stocks.id)
    target = pc.command("investments.set_target", bucket="Stocks", weight="60", class_id=cls)
    factor = pc.command("investments.set_factor", asset_class_id=cls, factor="90")
    renamed = pc.command("assets.update_investment", asset_id=stock, name="Alpha Corporation", class_code=None, isin="",
                         notes="core", active=True, ticker=None, mic=None)
    plan = pc.command("assets.set_preferences", asset_id=stock, bucket="Stocks", horizon="LONG")
    settle(hd, pc, target, factor, renamed, plan)
    assert pc.c.investments.target_weights() == hd.c.investments.target_weights() == {"Stocks": Decimal("60")}
    assert hd.c.investments.own_liquidation_factors() == {stocks.id: Decimal("90")}
    assert pc.c.assets.get_asset_by_code("STK:ALPH").notes == "core"
    retarget = pc.command("investments.set_target", bucket="Stocks", weight="45.5", class_id=cls)
    cleared = hd.command("investments.set_factor", asset_class_id=cls, factor="")
    settle(hd, pc, retarget, cleared)
    assert hd.c.investments.target_weights() == {"Stocks": Decimal("45.5")} and not pc.c.investments.own_liquidation_factors()
    drop = pc.command("investments.clear_target", bucket="Stocks")
    settle(hd, pc, drop)
    assert not hd.c.investments.target_weights()


def test_concurrent_edit_of_one_investment_waits_for_review(devices):
    hd, pc = devices
    broker, stock = setup(hd, pc)
    values = dict(asset_id=stock, class_code=None, isin="", active=True, ticker=None, mic=None)
    first = hd.command("assets.update_investment", name="Alpha Home", notes="", **values)
    late = pc.command("assets.update_investment", name="Alpha Phone", notes="on the phone", **values)  # Saw "Alpha Corp".
    pc.sync_with(hd.home)
    assert status(hd, first)["status"] == "accepted"
    assert status(hd, late) == dict(status="review", reason="conflict")
    assert [entry["state"] for entry in pc.pending_commands()] == ["Needs review"]
    state = hd.home.review_state(origin_id(unpack(late)["body"]["origin"]))
    hd.home.review(command_id=str(uuid4()), proposal_id=state["proposal_id"], token=state["token"], choice="apply")
    pc.sync_with(hd.home)
    assert pc.c.assets.get_asset_by_code("STK:ALPH").name == "Alpha Phone" and not pc.pending_commands()
    same(hd, pc)


def test_service_refusals_are_rejected_without_writing_and_uncovered_actions_are_refused(devices):
    hd, pc = devices
    broker, stock = setup(hd, pc)
    bought = buy(pc, broker, stock)
    settle(hd, pc, bought)
    oversold = pc.command("investments.sell_total", date="2026-09-20", account_id=broker, asset_id=stock, quantity="500",
                          total="5000.00", fees="0.00", fees_included=True, cash_account_id=None, notes="", owner_id=None)
    wrong = pc.command("investments.dividend", date="2026-08-01", account_id=broker, asset_id=stock, amount="10.00",
                       notes="", owner_id=None, tax="0")  # Nothing was held yet.
    pc.sync_with(hd.home)
    assert status(hd, oversold) == dict(status="rejected", reason="financial-validation")
    assert status(hd, wrong) == dict(status="rejected", reason="financial-validation")
    assert held(hd).quantity == 100 and cash(hd) == 4000
    same(hd, pc)
    with pytest.raises(Exception, match="not covered"):
        pc.command("investments.not_a_thing", date="2026-09-20")


def trade_form(device, **changes):
    values = dict(date="2026-09-01", account_id=account(device, "Broker").id,
                  asset_id=device.c.assets.get_asset_by_code("STK:ALPH").id, quantity="100", price="", fees="", total="1000",
                  cash_account_id="", amount="", total_cost="", notes="", owner_id="", dividend_basis="total")
    return values | changes


def test_the_buy_form_posts_on_the_home_and_on_the_replica(devices):
    from test_journal_screens import Screen
    hd, pc = devices
    setup(hd, pc)
    home, replica = Screen(hd), Screen(pc)
    response = home.post("/investments/new?kind=buy", data=trade_form(hd))  # Fees left blank, as the form does.
    assert response.status_code == 303 and "Saved%20BUY" in response.headers["location"], response.headers["location"]
    assert held(hd).quantity == 100 and cash(hd) == 4000
    response = replica.post("/investments/new?kind=buy", data=trade_form(pc, date="2026-09-02", quantity="10", total="120"))
    assert response.status_code == 303 and "msg=Saved+on+this+device" in response.headers["location"]
    assert not pc.c.investments.portfolio("2026-09-30").positions  # The replica's copy waits for the home.
    pc.sync_with(hd.home)
    assert held(pc).quantity == held(hd).quantity == 110 and cash(pc) == cash(hd) == 3880
    same(hd, pc)
    refused = replica.post("/investments/new?kind=sell", data=trade_form(pc, quantity="900", total="9000"))
    assert refused.status_code == 400 and not pc.store.pending()  # Refused at once, in the service's words.


def test_dividend_price_target_and_pocket_forms_on_both_devices(devices):
    from test_journal_screens import Screen
    hd, pc = devices
    setup(hd, pc)
    home, replica = Screen(hd), Screen(pc)
    home.post("/investments/new?kind=buy", data=trade_form(hd))
    pc.sync_with(hd.home)
    # A dividend per share with tax withheld, entered on the replica.
    dividend = trade_form(pc, kind="dividend", date="2026-09-10", amount="1.50", dividend_basis="per_share")
    response = replica.post("/investments/new?kind=dividend", data=dividend)
    assert "msg=Saved+on+this+device" in response.headers["location"]
    # Prices typed on the prices page: the home saves at once, the replica waits.
    stock_hd, stock_pc = (d.c.assets.get_asset_by_code("STK:ALPH").id for d in (hd, pc))
    response = home.post("/investments/prices", data={"date": "2026-09-15", f"p_{stock_hd}": "11.50"})
    assert response.status_code == 303 and "Saved%201%20price" in response.headers["location"], response.headers["location"]
    response = replica.post("/investments/prices", data={"date": "2026-09-16", f"p_{stock_pc}": "12"})
    assert "msg=Saved+on+this+device" in response.headers["location"]
    target = replica.post("/investments/targets", data={"bucket": "Stocks", "target_weight": "40"})
    assert "msg=Saved+on+this+device" in target.headers["location"]
    pocket = replica.post(f"/accounts/{account(pc, 'Broker').id}/pockets", data={"currency": "USD"})
    assert "msg=Saved+on+this+device" in pocket.headers["location"]
    pc.sync_with(hd.home)
    assert cash(pc) == cash(hd) == 4000 + Decimal("150.00")  # 1.50 x 100 shares
    assert [p.date for p in hd.c.assets.price_history(stock_hd)] == [p.date for p in pc.c.assets.price_history(stock_pc)] == [
        "2026-09-16", "2026-09-15"]
    assert hd.c.investments.target_weights() == {"Stocks": Decimal("40")}
    same(hd, pc)


def open_account(pc, name, kind, **changes):
    values = dict(name=name, account_type=kind, opening_date="2026-01-01", opening_balance="0", institution="NBE",
                  last4=None, notes="", currency=None, opening_balance_date=None, owner_id=None)
    return pc.command("accounts.open", **(values | changes))


def test_certificate_purchase_terms_and_redemption(devices):
    hd, pc = devices
    portfolio = open_account(pc, "CDs", "DEPOSIT")
    settle(hd, pc, portfolio)
    bank = uid(pc, "accounts", account(pc, "Bank").id)
    terms = dict(lockup_end_date="2026-07-15", maturity_date="2027-01-15", annual_rate="20", interest_method="SIMPLE",
                 payout_frequency="MONTHLY", compounding_frequency="MONTHLY", destination_account_id=bank, term_years="")
    purchase = pc.command("deposits.purchase", account_id=record(portfolio), name="NBE one", start_date="2026-01-15",
                          principal="500.00", funding_account_id=bank, **terms)
    settle(hd, pc, purchase)
    cert = pc.c.deposits.list_certificates(account(pc, "CDs").id)[0]
    assert cert.terms.name == "NBE one" and cert.terms.principal == 500 and cert.units == 1
    assert pc.c.reporting.account_balance(account(pc, "Bank").id) == hd.c.reporting.account_balance(account(hd, "Bank").id) == 500
    home_cert = hd.c.deposits.list_certificates(account(hd, "CDs").id)[0]
    assert home_cert.terms.name == "NBE one"
    certificate = uid(pc, "cd_certificates", cert.terms.id)
    edit = pc.command("deposits.update_certificate", certificate_id=certificate, name="NBE three", **(terms | dict(annual_rate="21")))
    settle(hd, pc, edit)
    home_cert = hd.c.deposits.list_certificates(account(hd, "CDs").id)[0]
    assert home_cert.terms.annual_rate == 21 and hd.c.assets.get_asset(home_cert.terms.asset_id).name == "NBE three"
    redeem = pc.command("deposits.redeem", certificate_id=certificate, date_value="2026-10-01", proceeds="600.00",
                        destination_account_id=bank)
    settle(hd, pc, redeem)
    assert pc.c.reporting.account_balance(account(pc, "Bank").id) == 1100
    assert pc.c.deposits.list_certificates(account(pc, "CDs").id)[0].redeemed
    assert pc.c.db.scalar("SELECT COUNT(*) FROM cd_redemptions") == hd.c.db.scalar("SELECT COUNT(*) FROM cd_redemptions") == 1


def test_gameya_terms_instalments_and_payout(devices):
    hd, pc = devices
    circle = open_account(pc, "Circle", "GAMEYA", institution="")
    settle(hd, pc, circle)
    bank = uid(pc, "accounts", account(pc, "Bank").id)
    terms = pc.command("gameya.save_terms", account_id=record(circle), organiser="Om Ali", members="5", installment="100.00",
                       first_date="2026-06-01", my_turn="3", payout="", annual_rate="0", funding_account_id=bank,
                       payout_account_id=bank)
    first = pc.command("gameya.record_instalment", account_id=record(circle), date_value="2026-06-01", amount="100",
                       funding_account_id=bank)
    settle(hd, pc, terms, first)
    assert pc.c.gameya.get(account(pc, "Circle").id).members == 5 and pc.c.gameya.progress(account(pc, "Circle").id).paid == 1
    past = pc.command("gameya.record_past_instalments", account_id=record(circle), expected_paid=1, as_of=None)
    settle(hd, pc, past)
    assert pc.c.gameya.progress(account(pc, "Circle").id).paid == hd.c.gameya.progress(account(hd, "Circle").id).paid == 5
    payout = pc.command("gameya.record_payout", account_id=record(circle), date_value="2026-08-01", amount="500",
                        payout_account_id=bank)
    settle(hd, pc, payout)
    assert pc.c.reporting.account_balance(account(pc, "Bank").id) == 1000 - 500 + 500
    stale = pc.command("gameya.record_past_instalments", account_id=record(circle), expected_paid=1, as_of=None)
    pc.sync_with(hd.home)
    assert status(hd, stale) == dict(status="rejected", reason="financial-validation")  # The circle changed since.


def test_physical_item_valuation_and_trade_details(devices):
    hd, pc = devices
    gold = pc.command("assets.create_investment", name="Gold 21K", class_code="GOLD", symbol="", karat="21", isin="", notes="",
                      mic="", currency="")
    vault = open_account(pc, "Vault", "PHYSICAL_ASSET", institution="")
    settle(hd, pc, gold, vault)
    item = pc.command("physical.create", account_id=record(vault), name="Ring", kind="Jewelry", grams_per_piece="5.5", karat=21,
                      reference_asset_id=record(gold), details="engraved", worn=False)
    settle(hd, pc, item)
    holding = pc.command("investments.add_holding", account_id=record(vault), asset_id=record(item), quantity="1",
                         total_cost="9000.00", date="2026-03-01", notes="", owner_id=None)
    settle(hd, pc, holding)
    details = pc.command("physical.record_trade_details", transaction_id=record(holding), asset_id=record(item), action="OPN",
                         workmanship_cost=None, notes="gift")
    value = pc.command("physical.record_valuation", asset_id=record(item), day="2026-09-01", total_value="12000.00", notes="jeweller")
    renamed = pc.command("physical.update", asset_id=record(item), name="Gold ring", kind="Jewelry", grams_per_piece="5.5",
                         karat=21, reference_asset_id=record(gold), details="engraved", worn=True)
    settle(hd, pc, details, value, renamed)
    row = pc.c.physical_items.for_account(account(pc, "Vault").id)[0]
    assert row["name"] == "Gold ring" and row["worn"] == 1 and pc.c.physical_items.valuations(row["asset_id"])[0]["notes"] == "jeweller"
    assert pc.c.physical_items.trade_details_for_account(account(pc, "Vault").id)[0]["notes"] == "gift"


def test_deposit_and_gameya_forms_on_both_devices(devices):
    from test_journal_screens import Screen
    hd, pc = devices
    portfolio, circle = open_account(pc, "CDs", "DEPOSIT"), open_account(pc, "Circle", "GAMEYA", institution="")
    settle(hd, pc, portfolio, circle)
    home, replica = Screen(hd), Screen(pc)

    def cd(device, **changes):
        bank = account(device, "Bank").id
        return dict(name="NBE one", start_date="2026-01-15", lockup_end_date="2026-07-15", maturity_date="2027-01-15",
                    term_years="", principal="500", annual_rate="20", interest_method="SIMPLE", compounding_frequency="MONTHLY",
                    payout_frequency="MONTHLY", destination_account_id=bank, funding_account_id=bank) | changes

    response = home.post(f"/deposits/{account(hd, 'CDs').id}/purchase", data=cd(hd))
    assert response.status_code == 303 and "Bought%20NBE%20one" in response.headers["location"], response.headers["location"]
    response = replica.post(f"/deposits/{account(pc, 'CDs').id}/purchase", data=cd(pc, name="NBE two", principal="100"))
    assert "msg=Saved+on+this+device" in response.headers["location"]
    bank = account(pc, "Bank").id
    terms = dict(organiser="Om Ali", members="5", installment="100", first_date="2026-06-01", my_turn="3", interest="none",
                 payout="", annual_rate="", funding_account_id=bank, payout_account_id=bank)
    response = replica.post(f"/gameya/{account(pc, 'Circle').id}/terms", data=terms)
    assert "msg=Saved+on+this+device" in response.headers["location"]
    pc.sync_with(hd.home)
    paid = dict(date="2026-06-01", amount="100", account_id=account(hd, "Bank").id)
    response = home.post(f"/gameya/{account(hd, 'Circle').id}/instalment", data=paid)
    assert response.status_code == 303 and "Recorded%20instalment" in response.headers["location"], response.headers["location"]
    pc.sync_with(hd.home)
    assert {c.terms.name for c in pc.c.deposits.list_certificates(account(pc, "CDs").id)} == {"NBE one", "NBE two"}
    assert cash(pc, "Bank") == cash(hd, "Bank") == 1000 - 500 - 100 - 100
    same(hd, pc)


def test_cost_method_of_a_broker_follows_to_the_other_device(devices):
    hd, pc = devices
    broker, _ = setup(hd, pc)
    settle(hd, pc, pc.command("accounts.set_cost_method", account_id=broker, method="fifo"))
    assert account(hd, "Broker").cost_method == account(pc, "Broker").cost_method == "fifo"


def test_bonus_or_split_travels_and_changes_the_units_on_both_devices(devices):
    hd, pc = devices
    broker, stock = setup(hd, pc)
    settle(hd, pc, buy(pc, broker, stock))
    settle(hd, pc, pc.command("investments.bonus_or_split", date="2026-09-02", account_id=broker, asset_id=stock,
                              units_after="125", notes="", owner_id=None))
    quantity = lambda d: next(p.quantity for p in d.c.investments.portfolio("2026-09-30").positions)
    assert quantity(hd) == quantity(pc) == Decimal("125")
