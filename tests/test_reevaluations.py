from decimal import Decimal

import pytest

from lightning.core.errors import ValidationError
from lightning.core.ledger import PostingLine
from lightning.core.refs import DocType
from lightning.database.currencies import CurrencyRegistry
from lightning.transactions.domain import TxnSource


def _certificate(c, accounts, name, principal):
    return c.deposits.purchase(
        accounts["cd"].id, name=name, start_date="2026-09-01", lockup_end_date="2026-09-01",
        maturity_date="2027-09-01", principal=principal, annual_rate="12.5", interest_method="SIMPLE",
        payout_frequency="MONTHLY", compounding_frequency="MONTHLY",
        destination_account_id=accounts["cib"].id, funding_account_id=accounts["cib"].id,
    )[0]


def test_monthly_returns_create_one_account_journal_linked_from_each_asset(c):
    account = c.account_flows.open_account("THNDR", "BROKERAGE", "2026-09-01", "10000")
    first = c.assets.create_investment("First fund", "FUND.EQUITY", "F1")
    second = c.assets.create_investment("Second fund", "FUND.EQUITY", "F2")
    c.investments.add_holding(account.id, first.id, "10", "1000", "2026-09-01")
    c.investments.add_holding(account.id, second.id, "20", "1000", "2026-09-02")
    c.assets.set_price(first.id, "2026-09-30", "110")
    c.assets.set_price(second.id, "2026-09-30", "55")

    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")
    detail = c.db.all("SELECT * FROM reevaluation_entries ORDER BY asset_id")
    assert len(detail) == 2
    assert {row["journal_transaction_id"] for row in detail} == {detail[0]["journal_transaction_id"]}
    journal = c.transactions.get(detail[0]["journal_transaction_id"])
    assert journal.type.value == "VAL" and journal.source.value == "SYSTEM"
    assert journal.lines[0].effect.value == "REVALUATION"
    assert journal.lines[0].amount_base == Decimal("200")
    assert len(journal.lines) == 1
    assert c.reporting.account_balance(account.id) == Decimal("10000")
    assert c.db.scalar("SELECT status FROM reevaluation_periods WHERE date='2026-09-30'") == "POSTED"
    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")  # idempotent on reopen
    assert c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='VAL'") == 1


def test_foreign_cash_month_end_records_fx_return_without_changing_native_balance(c):
    CurrencyRegistry(c.db).register("USD")
    c.fx.save("USD", "2026-09-01", "50")
    account = c.account_flows.open_account(
        "Dollar savings", "BANK", "2026-09-01", "100", currency="USD",
        opening_balance_date="2026-09-01")
    c.fx.save("USD", "2026-09-30", "55")

    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")
    detail = c.db.one("SELECT value_base_e6,return_base_e6,price_source,journal_transaction_id "
                      "FROM reevaluation_entries")
    assert detail["value_base_e6"] == 5_500_000_000
    assert detail["return_base_e6"] == 500_000_000
    assert detail["price_source"] == "FX"
    assert c.reporting.account_balance(account.id, "2026-09-30") == Decimal("100")
    opening = next(row for row in c.reporting.register(account.id, "2026-09-01", "2026-09-30")
                   if row.type == "OPN")
    assert (opening.amount_base, opening.amount, opening.currency) == (
        Decimal("5000"), Decimal("100"), "USD")
    journal = c.transactions.get(detail["journal_transaction_id"])
    assert journal.lines[0].quantity == 0
    assert journal.lines[0].amount_base == Decimal("500")
    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")
    assert c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='VAL'") == 1


def test_foreign_cash_checkpoint_exposes_missing_rate(c):
    CurrencyRegistry(c.db).register("USD")
    c.fx.save("USD", "2026-09-01", "50")
    c.account_flows.open_account("Dollar savings", "BANK", "2026-09-01", "100",
                                 currency="USD", opening_balance_date="2026-09-01")
    c.db.execute("DELETE FROM fx_rates")

    assert not c.reevaluations.process_date("2026-09-30", "MONTH_END")
    assert c.reevaluations.pending_fx() == [{"date": "2026-09-30", "currency": "USD"}]
    c.fx.save("USD", "2026-09-30", "55")
    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")


def test_deleted_reevaluation_stays_deleted_when_checkpoint_is_rebuilt(c):
    account = c.account_flows.open_account("THNDR", "BROKERAGE", "2026-09-01", "1000")
    asset = c.assets.create_investment("Fund", "FUND.EQUITY", "FUND")
    c.investments.add_holding(account.id, asset.id, "1", "100", "2026-09-01")
    c.assets.set_price(asset.id, "2026-09-30", "120")
    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")
    journal_id = c.db.scalar("SELECT transaction_id FROM reevaluation_account_posts")
    assert c.transactions.delete_many([journal_id]) == 1
    assert c.transactions.get(journal_id).is_void
    c.assets.set_price(asset.id, "2026-09-30", "130")
    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")
    assert c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='VAL' AND status='POSTED'") == 0
    c.transactions.restore(journal_id)
    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")
    assert c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='VAL' AND status='POSTED'") == 1


def test_deleting_earlier_reevaluation_recalculates_later_return(c):
    account = c.account_flows.open_account("THNDR", "BROKERAGE", "2026-09-01", "1000")
    asset = c.assets.create_investment("Fund", "FUND.EQUITY", "FUND")
    c.investments.add_holding(account.id, asset.id, "1", "100", "2026-09-01")
    c.assets.set_price(asset.id, "2026-09-30", "120")
    c.assets.set_price(asset.id, "2026-10-31", "140")
    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")
    assert c.reevaluations.process_date("2026-10-31", "MONTH_END")
    old_id = c.db.scalar("SELECT ap.transaction_id FROM reevaluation_account_posts ap "
                         "JOIN reevaluation_periods p ON p.id=ap.period_id WHERE p.date='2026-09-30'")
    c.transactions.delete_many([old_id])
    assert c.reevaluations.process_date("2026-10-31", "MONTH_END")
    later = c.db.scalar("SELECT e.return_base_e6 FROM reevaluation_entries e "
                        "JOIN reevaluation_periods p ON p.id=e.period_id WHERE p.date='2026-10-31'")
    assert later == 40_000_000


def test_sale_forces_same_day_revaluation_at_trade_price(c):
    account = c.account_flows.open_account("THNDR", "BROKERAGE", "2026-09-01", "10000")
    asset = c.assets.create_investment("COMI", "STOCK", "COMI")
    c.investments.add_holding(account.id, asset.id, "10", "1000", "2026-09-01")
    c.assets.set_price(asset.id, "2026-09-30", "120")
    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")

    c.investments.sell("2026-10-05", account.id, asset.id, "5", "130")
    sale_period = c.db.one("SELECT id,status FROM reevaluation_periods WHERE date='2026-10-05' AND reason='SALE'")
    assert sale_period["status"] == "POSTED"
    detail = c.db.one("SELECT * FROM reevaluation_entries WHERE period_id=?", (sale_period["id"],))
    assert detail["price_source"] == "TRADE"
    assert Decimal(detail["return_base_e6"]) / 1_000_000 == Decimal("100")
    assert detail["journal_transaction_id"] is not None
    linked = c.db.scalar("SELECT transaction_id FROM reevaluation_account_posts WHERE period_id=?",
                         (sale_period["id"],))
    assert linked == detail["journal_transaction_id"]


def test_pending_month_end_price_is_explicit_and_completes_after_manual_entry(c):
    account = c.account_flows.open_account("THNDR", "BROKERAGE", "2026-09-01", "10000")
    asset = c.assets.create_investment("Fund no feed", "FUND.EQUITY", "NOFEED")
    c.investments.add_holding(account.id, asset.id, "10", "1000", "2026-09-01")
    assert not c.reevaluations.process_date("2026-09-30", "MONTH_END")
    assert c.reevaluations.pending_prices()[0]["asset_id"] == asset.id

    c.reevaluations.record_manual_price(asset.id, "2026-09-30", Decimal("120"))
    assert c.db.scalar("SELECT status FROM reevaluation_periods WHERE date='2026-09-30'") == "POSTED"
    assert c.reevaluations.pending_prices() == []


def test_cd_month_end_prices_post_per_certificate_without_cash_or_unit_changes(c, setup):
    accounts, _ = setup
    first = _certificate(c, accounts, "CIB first certificate", "10000")
    second = _certificate(c, accounts, "CIB second certificate", "20000")
    c.assets.set_price(first.terms.asset_id, "2026-09-30", "11000")
    c.assets.set_price(second.terms.asset_id, "2026-09-30", "18000")
    cash_before = c.reporting.account_balance(accounts["cd"].id, "2026-09-30")

    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")
    details = c.db.all("SELECT asset_id,units_e6,return_base_e6,journal_transaction_id "
                       "FROM reevaluation_entries ORDER BY asset_id")
    assert [(row["asset_id"], row["units_e6"], row["return_base_e6"]) for row in details] == [
        (first.terms.asset_id, 1_000_000, 1_000_000_000),
        (second.terms.asset_id, 1_000_000, -2_000_000_000),
    ]
    assert len({row["journal_transaction_id"] for row in details}) == 1
    journal = c.transactions.get(details[0]["journal_transaction_id"])
    assert journal.type == DocType.VAL and journal.source == TxnSource.SYSTEM
    assert [(line.asset_id, line.quantity, line.amount_base,
             c.assets.get_asset(line.asset_id).is_cash) for line in journal.lines] == [
        (first.terms.asset_id, Decimal(0), Decimal("1000.00"), False),
        (second.terms.asset_id, Decimal(0), Decimal("-2000.00"), False),
    ]
    assert c.reporting.account_balance(accounts["cd"].id, "2026-09-30") == cash_before
    for asset_id in (first.terms.asset_id, second.terms.asset_id):
        units = c.db.scalar("SELECT SUM(le.quantity_e6) FROM ledger_entries le JOIN transactions t "
                            "ON t.id=le.transaction_id WHERE le.account_id=? AND le.asset_id=? "
                            "AND t.status='POSTED' AND le.date<='2026-09-30'",
                            (accounts["cd"].id, asset_id))
        assert units == 1_000_000


def test_cd_portfolio_rejects_manual_value_journals(c, setup):
    accounts, _ = setup
    certificate = _certificate(c, accounts, "CIB certificate", "10000")
    line = PostingLine.revaluation(accounts["cd"].id, certificate.terms.asset_id,
                                   Decimal("1"), is_cash=False)
    with pytest.raises(ValidationError, match="Only CD certificates can be traded"):
        c.transactions.post(DocType.VAL, "2026-09-30", [line], source=TxnSource.MANUAL)


def test_month_end_checkpoint_keeps_returns_by_owner_without_changing_cash(c):
    account = c.account_flows.open_account("THNDR", "BROKERAGE", "2026-09-01", "0")
    dad = c.counterparties.create("Dad")
    salary = c.categories.get_by_code("EXP.WORK.SALARY")
    asset = c.assets.create_investment("Owned share", "STOCK", "OWNED")
    c.transactions.record_inflow("2026-09-10", account.id, "1000", salary.id)
    c.transactions.record_inflow("2026-09-10", account.id, "1000", salary.id, owner_id=dad)
    c.investments.buy("2026-09-11", account.id, asset.id, "1", "10")
    c.investments.buy("2026-09-11", account.id, asset.id, "1", "10", owner_id=dad)
    c.assets.set_price(asset.id, "2026-09-30", "20")
    cash_before = c.reporting.account_balance(account.id, "2026-09-30")

    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")
    rows = c.db.all("SELECT owner_id,return_base_e6,journal_transaction_id "
                    "FROM reevaluation_entries ORDER BY owner_id")
    assert [(row["owner_id"], row["return_base_e6"]) for row in rows] == [(None, 10_000_000), (dad, 10_000_000)]
    journal = c.transactions.get(rows[0]["journal_transaction_id"])
    assert {line.owner_id for line in journal.lines} == {None, dad}
    assert c.reporting.account_balance(account.id, "2026-09-30") == cash_before


def test_physical_item_edit_rebuilds_existing_checkpoints(c):
    account = c.account_flows.open_account("Gold at home", "PHYSICAL_ASSET", "2026-09-01", "0")
    reference = c.assets.get_asset_by_code("GLD:18K")
    c.assets.set_price(reference.id, "2026-09-30", "1000")
    item = c.physical_items.create(account.id, "Ring", "Ring", "4", 18, reference.id)
    c.investments.add_holding(account.id, item, "1", "3000", "2026-09-01")
    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")
    old_journal_id = c.db.scalar("SELECT transaction_id FROM reevaluation_account_posts")
    c.physical_items.update(item, "Ring", "Ring", "5", 18, reference.id)

    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")
    row = c.db.one("SELECT units_e6,value_base_e6,return_base_e6 FROM reevaluation_entries")
    assert row["value_base_e6"] == 5_000_000_000
    assert row["return_base_e6"] == 2_000_000_000
    assert c.transactions.get(old_journal_id).is_void


def test_rebuilt_checkpoint_reuses_unchanged_revaluation_journals(c):
    """BT-2E part 8: new inputs that leave a checkpoint's lines as they were do not void and repost them."""
    account = c.account_flows.open_account("THNDR", "BROKERAGE", "2026-09-01", "10000")
    fund = c.assets.create_investment("First fund", "FUND.EQUITY", "F1")
    c.investments.add_holding(account.id, fund.id, "10", "1000", "2026-09-01")
    c.assets.set_price(fund.id, "2026-09-30", "110")
    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")
    before = c.db.one("SELECT id,status FROM transactions WHERE type='VAL'")
    hash_before = c.db.scalar("SELECT source_hash FROM reevaluation_periods WHERE date='2026-09-30'")

    c.assets.set_price(fund.id, "2026-09-15", "105")  # a new input before the month end: the hash changes, the lines do not
    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")

    assert c.db.scalar("SELECT source_hash FROM reevaluation_periods WHERE date='2026-09-30'") != hash_before
    rows = c.db.all("SELECT id,status FROM transactions WHERE type='VAL'")
    assert [(r["id"], r["status"]) for r in rows] == [(before["id"], "POSTED")]  # not voided, not reposted
    assert c.db.scalar("SELECT transaction_id FROM reevaluation_account_posts") == before["id"]
    assert c.db.scalar("SELECT COUNT(*) FROM audit_log WHERE entity_id=? AND action='void'", (before["id"],)) == 0

    c.assets.set_price(fund.id, "2026-09-30", "120")  # a changed price still rebuilds the journal
    assert c.reevaluations.process_date("2026-09-30", "MONTH_END")
    assert c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='VAL' AND status='VOID'") == 1
    assert c.db.scalar("SELECT amount_base_e6 FROM reevaluation_account_posts") == 200_000_000
