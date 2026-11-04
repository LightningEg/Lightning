"""Investments: brokers, trades, dividends, fees, interest, moves, the investment list, typed prices and targets.

Not covered: prices fetched online or filled from price files (home automation, not a user action) and the inline
account entry, which also writes money-from-others rows in a second call. `reevaluations.process_due` is the
"catch up" a person starts; a catch-up that changes more than one effect can carry is refused whole. A trade edit
carries the whole form (`investments.update`).
"""
from .spec import AMOUNT, DATE, FLAG, LONG, RATE, TEXT, Command, items, optional, ref

TABLES = ("investment_custody_events", "investment_dividend_assets", "investment_targets", "investment_liquidation_factors",
          "price_history", "reevaluation_periods", "reevaluation_entries", "reevaluation_account_posts",
          "reevaluation_suppressed_accounts")

TXN = ("transactions", "txn_id")
ASSET = ("financial_assets", "asset_id")
# Cash trades: the paying account and the owner (someone else's money) are optional.
TRADE = dict(date=DATE, account_id=ref("accounts"), asset_id=ref("financial_assets"), quantity=RATE)
EXTRA = dict(cash_account_id=optional(ref("accounts")), notes=LONG, owner_id=optional(ref("counterparties")))
FEES = optional(AMOUNT)  # Left blank on the forms; the service reads a blank as nothing.
TOTAL = dict(total=AMOUNT, fees=FEES, fees_included=FLAG)
# The edit form posts every field as text; the service reads the ones its kind needs.
EDIT = dict(txn_id=ref("transactions"), date=TEXT, account_id=ref("accounts"), asset_id=ref("financial_assets"),
            quantity=TEXT, price=TEXT, fees=TEXT, total_fees=TEXT, fees_included=FLAG, total=TEXT,
            cash_account_id=optional(ref("accounts")), amount=TEXT, total_cost=TEXT, notes=LONG,
            owner_id=optional(ref("counterparties")))



def _none_is_zero(*names):
    return lambda values: values | {name: values[name] or "0" for name in names}


COMMANDS = {
    "investments.buy": Command("investments.buy", TRADE | dict(price=RATE, fees=FEES) | EXTRA, creates="transactions",
                               adapt=_none_is_zero("fees")),
    "investments.buy_total": Command("investments.buy_total", TRADE | TOTAL | EXTRA, creates="transactions",
                                     adapt=_none_is_zero("fees")),
    "investments.sell": Command("investments.sell", TRADE | dict(price=RATE, fees=FEES) | EXTRA, creates="transactions",
                                adapt=_none_is_zero("fees")),
    "investments.sell_total": Command("investments.sell_total", TRADE | TOTAL | EXTRA, creates="transactions",
                                      adapt=_none_is_zero("fees")),
    "investments.buy_converting": Command("investments.buy_converting", TRADE | dict(
        total=AMOUNT, paid=AMOUNT, from_account_id=optional(ref("accounts")), notes=LONG, fees=FEES, fees_included=FLAG,
        owner_id=optional(ref("counterparties"))), creates="transactions", adapt=_none_is_zero("fees")),
    "investments.dividend": Command("investments.dividend", dict(
        date=DATE, account_id=ref("accounts"), asset_id=ref("financial_assets"), amount=AMOUNT, notes=LONG,
        owner_id=optional(ref("counterparties")), tax=FEES), creates="transactions", adapt=_none_is_zero("tax")),
    "investments.return_of_capital": Command("investments.return_of_capital", dict(
        date=DATE, account_id=ref("accounts"), asset_id=ref("financial_assets"), amount=AMOUNT,
        cash_account_id=optional(ref("accounts")), notes=LONG, owner_id=optional(ref("counterparties"))),
        creates="transactions"),
    "investments.bonus_or_split": Command("investments.bonus_or_split", dict(
        date=DATE, account_id=ref("accounts"), asset_id=ref("financial_assets"), units_after=RATE, notes=LONG,
        owner_id=optional(ref("counterparties"))), creates="transactions"),
    "investments.add_holding": Command("investments.add_holding", dict(
        account_id=ref("accounts"), asset_id=ref("financial_assets"), quantity=RATE, total_cost=AMOUNT,
        date=optional(DATE), notes=LONG, owner_id=optional(ref("counterparties"))), creates="transactions"),
    "investments.update": Command("investments.update", EDIT, target=TXN),
    "investments.broker_fee": Command("investments.broker_fee", dict(
        date=DATE, account_id=ref("accounts"), amount=AMOUNT, notes=LONG), creates="transactions"),
    "investments.broker_interest": Command("investments.broker_interest", dict(
        date=DATE, account_id=ref("accounts"), amount=AMOUNT, notes=LONG), creates="transactions"),
    "investments.move_units": Command("investments.move_units", dict(
        date=DATE, from_account_id=ref("accounts"), to_account_id=ref("accounts"), asset_id=ref("financial_assets"),
        quantity=RATE, notes=LONG), creates="transactions"),
    "investments.add_pocket": Command("accounts.add_pocket", dict(broker_id=ref("accounts"), currency=TEXT),
                                      creates="accounts"),
    # No precondition on a bucket or class: the last typed target or factor wins.
    "investments.set_target": Command("investments.set_target_weight", dict(
        bucket=TEXT, weight=AMOUNT, class_id=ref("asset_classes"))),
    "investments.clear_target": Command("investments.clear_target_weight", dict(bucket=TEXT)),
    "investments.set_factor": Command("investments.set_liquidation_factor", dict(
        asset_class_id=ref("asset_classes"), factor=TEXT)),
    "investments.set_all_factors": Command("investments.set_all_liquidation_factors", dict(factor=TEXT)),
    "assets.create_investment": Command("assets.create_investment", dict(
        name=TEXT, class_code=TEXT, symbol=TEXT, karat=optional(TEXT), isin=TEXT, notes=LONG, mic=TEXT, currency=TEXT),
        creates="financial_assets"),
    "assets.update_investment": Command("assets.update_investment", dict(
        asset_id=ref("financial_assets"), name=TEXT, class_code=optional(TEXT), isin=TEXT, notes=LONG, active=FLAG,
        ticker=optional(TEXT), mic=optional(TEXT)), target=ASSET),
    "assets.link_fund": Command("assets.link_fund", dict(asset_id=ref("financial_assets"), page=TEXT), target=ASSET),
    "assets.set_preferences": Command("assets.set_investment_preferences", dict(
        asset_id=ref("financial_assets"), bucket=TEXT, horizon=optional(TEXT)), target=ASSET),
    "assets.set_price": Command("assets.set_price", dict(asset_id=ref("financial_assets"), date=DATE, price=RATE)),
    "assets.set_prices": Command("assets.set_prices", dict(date=DATE, prices=items(asset=ref("financial_assets"), price=RATE)),
                                 adapt=lambda values: values | dict(prices={line["asset"]: line["price"] for line in values["prices"]})),
    "assets.remove_price": Command("assets.remove_price", dict(asset_id=ref("financial_assets"), date=DATE)),
    # Month-end catch-up on the prices typed so far. It can change many rows; a larger effect is refused whole.
    "reevaluations.record_manual_price": Command("reevaluations.record_manual_price", dict(
        asset_id=ref("financial_assets"), day=DATE, price=RATE)),
    "reevaluations.process_due": Command("reevaluations.process_due", {}),
}
