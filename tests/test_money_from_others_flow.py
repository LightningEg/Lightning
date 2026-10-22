from decimal import Decimal

import pytest

from lightning.core.errors import ValidationError


def test_custody_category_links_cash_transaction_and_excludes_it_from_owned_totals(c):
    bank = c.account_flows.open_account("CIB", "BANK", "2026-09-01", "1000")
    category = c.categories.get_by_code("EXP.SYSTEM.CUSTODY")
    dad_id = c.counterparties.create("Dad")
    dad = c.counterparties.get(dad_id)["name"]

    receipt = c.transactions.record_in_account(bank.id, "2026-09-10", "500", category.id)
    c.money_from_others.sync_transaction(receipt.id, receipt.date, dad, bank.id, Decimal("500"))
    assert c.reporting.account_balance(bank.id) == Decimal("1500")
    assert c.reporting.owned_account_value(bank.id, "2026-09-30") == Decimal("1000")
    assert c.reporting.money_from_others_total("2026-09-30") == Decimal("500")
    assert c.reporting.cash_flow("2026-09-01", "2026-09-30").inflows == 0

    returned = c.transactions.record_in_account(bank.id, "2026-09-12", "-125", category.id)
    c.money_from_others.sync_transaction(returned.id, returned.date, dad, bank.id, Decimal("-125"))
    assert c.reporting.money_from_others_total("2026-09-30") == Decimal("375")
    with pytest.raises(ValidationError, match="more than the money currently held"):
        with c.db.transaction():
            excess = c.transactions.record_in_account(bank.id, "2026-09-13", "-500", category.id)
            c.money_from_others.sync_transaction(excess.id, excess.date, dad, bank.id, Decimal("-500"))


def test_investment_units_can_be_attributed_to_another_person(c, setup):
    accounts, _ = setup
    stock = c.assets.create_investment("CIB Shares", "STOCK", "COMI")
    before = c.reporting.net_worth("2026-09-30").total
    c.transactions.record_transfer("2026-09-09", accounts["cib"].id, accounts["thndr"].id, "2000")
    buy = c.investments.buy_total("2026-09-10", accounts["thndr"].id, stock.id, "20", "2000")
    c.money_from_others.sync_investment(buy.id, buy.date, "Dad", accounts["thndr"].id, stock.id,
                                        Decimal("10"))
    assert c.reporting.money_from_others_total("2026-09-30") == Decimal("1000")
    assert c.reporting.net_worth("2026-09-30").total == before - Decimal("1000")
    with pytest.raises(ValidationError, match="less than zero"):
        with c.db.transaction():
            sale = c.investments.sell_total("2026-09-11", accounts["thndr"].id, stock.id, "11", "1100",
                                            accounts["cib"].id)
            c.money_from_others.sync_investment(sale.id, sale.date, "Dad", accounts["thndr"].id, stock.id,
                                                Decimal("-11"))


def test_csv_import_can_tag_held_for_others_with_whom(c):
    bank = c.account_flows.open_account("CIB", "BANK", "2026-09-01", "1000")
    category = c.categories.get_by_code("EXP.SYSTEM.CUSTODY")
    c.counterparties.create("Dad")
    batch_id, repeated = c.bank_imports.stage(
        bank.id, "statement.csv",
        b"Date,Amount,Counterparty,Category,Notes\n2026-09-10,300,Dad,,Family money\n",
    )
    assert not repeated
    _, rows = c.bank_imports.preview(batch_id)
    assert rows[0]["_whom"] == "Dad"
    result = c.bank_imports.confirm(batch_id, {
        rows[0]["_import_row_id"]: {"date": "2026-09-10", "amount": "300", "counterparty": "Dad",
                                   "category_id": category.id}
    })
    assert result["posted"] == 1
    assert c.reporting.account_balance(bank.id) == Decimal("1300")
    assert c.reporting.owned_account_value(bank.id, "2026-09-30") == Decimal("1000")


def test_import_uses_transfer_note_suggestion_and_posts_custody_rows_chronologically(c, setup):
    accounts, _ = setup
    source, target = accounts["cib"], accounts["thndr"]
    category = c.categories.get_by_code("EXP.SYSTEM.CUSTODY")
    c.counterparties.create("Dad")
    # Banks commonly export newest first. Dad's receipt must post before the
    # later transfer, even though the transfer appears first in the CSV.
    batch_id, _ = c.bank_imports.stage(
        source.id, "reverse-order.csv",
        b"Date,Counterparty,Category,Notes,Amount\n"
        b"2026-09-15,Dad,Personal > Money Held for Others,Transfer to thundr,-10000\n"
        b"2026-09-10,Dad,Personal > Money Held for Others,Received from Dad,9900\n",
    )
    _, rows = c.bank_imports.preview(batch_id)
    transfer_row = next(row for row in rows if row["Amount"] == "-10000")
    assert transfer_row["_transfer_target_suggestion"] == target.name
    decisions = {}
    for row in rows:
        if row is transfer_row:
            decisions[row["_import_row_id"]] = {
                "counterparty": target.name, "category_id": category.id, "whom": "Dad"
            }
        else:
            decisions[row["_import_row_id"]] = {
                "counterparty": "Dad", "category_id": category.id, "whom": "Dad"
            }
    result = c.bank_imports.confirm(batch_id, decisions)
    assert result["posted"] == 2
    assert c.money_from_others.cash_balance("Dad", source.id, "2026-09-30") == 0
    # Only the held amount follows Dad to THNDR; the EGP 100 difference is
    # still part of the account transfer, but belongs to the account owner.
    assert c.money_from_others.cash_balance("Dad", target.id, "2026-09-30") == Decimal("9900")


def test_import_posts_valid_rows_and_keeps_only_failed_rows_in_review(c):
    bank = c.account_flows.open_account("CIB", "BANK", "2026-09-01", "1000")
    custody = c.categories.get_by_code("EXP.SYSTEM.CUSTODY")
    c.counterparties.create("Dad")
    batch_id, _ = c.bank_imports.stage(
        bank.id, "partial.csv",
        b"Date,Amount,Counterparty,Category,Notes\n"
        b"2026-09-10,-20,Shop,,Groceries\n"
        b"2026-09-11,-500,Dad,Personal > Money Held for Others,Return\n",
    )
    _, rows = c.bank_imports.preview(batch_id)
    failed = next(row for row in rows if row["Counterparty"] == "Dad")
    result = c.bank_imports.confirm(batch_id, {
        row["_import_row_id"]: {"category_id": custody.id, "whom": "Dad"}
        if row is failed else {}
        for row in rows
    })
    assert result["posted"] == 0
    assert "more than the money currently held" in result["errors"][failed["_import_row_id"]]
    assert c.db.scalar("SELECT status FROM bank_import_batches WHERE id=?", (batch_id,)) == "REVIEW"
    statuses = c.db.all("SELECT status FROM bank_import_rows WHERE batch_id=? ORDER BY row_number", (batch_id,))
    assert [row["status"] for row in statuses] == ["REVIEW", "REVIEW"]
    assert c.reporting.account_balance(bank.id) == Decimal("1000")

    retried = c.bank_imports.confirm(batch_id, {
        row["_import_row_id"]: {"skip": True} if row is failed else {}
        for row in rows
    })
    assert retried["posted"] == 1 and retried["skipped"] == 1 and not retried["errors"]
    assert c.db.scalar("SELECT status FROM bank_import_batches WHERE id=?", (batch_id,)) == "POSTED"


def test_internal_transfer_moves_custody_cash_without_double_counting(c, setup):
    accounts, _ = setup
    source, target = accounts["cib"], accounts["thndr"]
    dad_id = c.counterparties.create("Dad")
    dad = c.counterparties.get(dad_id)["name"]
    category = c.categories.get_by_code("EXP.SYSTEM.CUSTODY")
    receipt = c.transactions.record_in_account(source.id, "2026-09-10", "1000", category.id,
                                               owner_id=dad_id)

    transfer = c.transactions.record_transfer("2026-09-11", source.id, target.id, "1000", owner_id=dad_id)
    assert c.money_from_others.cash_balance(dad, source.id, "2026-09-30") == 0
    assert c.money_from_others.cash_balance(dad, target.id, "2026-09-30") == Decimal("1000")
    assert c.reporting.money_from_others_total("2026-09-30") == Decimal("1000")

    asset = c.assets.create_investment("CIB Shares", "STOCK", "COMI")
    purchase = c.investments.buy_total("2026-09-12", target.id, asset.id, "10", "1000", owner_id=dad_id)
    assert c.reporting.money_from_others_total("2026-09-30") == Decimal("1000")


def test_someone_else_cannot_buy_investments_without_cash_in_the_funding_account(c, setup):
    accounts, _ = setup
    brokerage = accounts["thndr"]
    c.transactions.record_transfer("2026-09-05", accounts["cib"].id, brokerage.id, "5000")
    stock = c.assets.create_investment("Test stock", "STOCK", "TEST")
    c.money_from_others.record("2026-09-09", "Dad", brokerage.id, Decimal("500"))

    dad_id = c.counterparties.resolve("Dad")["id"]
    with pytest.raises(ValidationError, match="selected owner"):
        with c.db.transaction():
            trade = c.investments.buy_total("2026-09-10", brokerage.id, stock.id, "10", "1000", owner_id=dad_id)
            c.money_from_others.sync_investment(trade.id, trade.date, "Dad", brokerage.id, stock.id, Decimal("10"))
            c.money_from_others.sync_transaction(trade.id, trade.date, "Dad", brokerage.id, Decimal("-1000"))
    assert c.investments.holding(brokerage.id, stock.id) == 0
    assert c.money_from_others.cash_balance("Dad", brokerage.id, "2026-09-30") == Decimal("500")

    c.money_from_others.record("2026-09-09", "Dad", brokerage.id, Decimal("500"))
    with c.db.transaction():
        trade = c.investments.buy_total("2026-09-10", brokerage.id, stock.id, "10", "1000", owner_id=dad_id)
        c.money_from_others.sync_investment(trade.id, trade.date, "Dad", brokerage.id, stock.id, Decimal("10"))
        c.money_from_others.sync_transaction(trade.id, trade.date, "Dad", brokerage.id, Decimal("-1000"))
    assert c.investments.holding(brokerage.id, stock.id) == Decimal("10")
    assert c.money_from_others.cash_balance("Dad", brokerage.id, "2026-09-30") == 0


def test_marking_part_of_a_dollar_line_for_someone_keeps_whole_cents_and_undo_works(c):
    """2G: the split used to store base amounts with six decimals, and every later undo was refused."""
    from decimal import Decimal as D
    from lightning.core.ledger import PostingLine, validate_posting
    from lightning.undo import user_action
    c.currencies.register("USD")
    c.fx.save("USD", "2026-01-01", "50.123457")
    usd = c.account_flows.open_account("Dollar savings", "BANK", "2026-01-01", "0", currency="USD")
    txn = c.transactions.record_inflow("2026-01-02", usd.id, "100.01", c.categories.get_by_code("EXP.WORK.SALARY").id)
    c.counterparties.create("Dad", kind="PERSON")
    with c.db.transaction():
        c.money_from_others.sync_transaction(txn.id, "2026-01-02", "Dad", usd.id, D("33.33"))
    lines = c.transactions.get(txn.id).lines
    usd_lines = [line for line in lines if line.account_id == usd.id]
    assert sorted(line.quantity for line in usd_lines) == [D("33.33"), D("66.68")]
    # 100.01 at 50.123457 posted 5,012.85; each part is now its own amount x rate, as two entries would be
    assert abs(sum(line.amount_base for line in usd_lines) - D("5012.85")) <= D("0.01")
    assert all(line.amount_base == line.amount_base.quantize(D("0.01")) for line in lines)
    validate_posting([PostingLine(account_id=l.account_id, asset_id=l.asset_id, quantity=l.quantity, effect=l.effect,
                                  unit_price=l.unit_price, fx_rate=l.fx_rate, category_id=l.category_id, memo=l.memo,
                                  amount=l.amount, amount_base=l.amount_base, is_cash=True, owner_id=l.owner_id)
                      for l in lines])
    with user_action("Edit note"):
        c.transactions.update_metadata(txn.id, "2026-01-02", "", "second note")
    c.undo.replay()
    assert c.transactions.get(txn.id).notes != "second note"


def test_a_voided_sale_for_someone_no_longer_counts_against_their_next_sale(c):
    """2G: the custody check summed a voided sale, so Dad's real 10 units looked like 0."""
    from decimal import Decimal as D
    flows = c.account_flows
    broker = flows.open_account("THNDR", "BROKERAGE", "2026-01-01", "0", institution="THNDR")
    bank = flows.open_account("CIB", "BANK", "2026-01-01", "100000", institution="CIB")
    dad = c.counterparties.create("Dad")
    asset = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI")
    c.transactions.record_transfer("2026-02-01", bank.id, broker.id, "5000")
    c.transactions.change_cash_ownership("2026-02-01", broker.id, "5000", None, dad)

    def trade(record, day, units, total, signed):
        with c.db.transaction():
            txn = record(day, broker.id, asset.id, units, total, owner_id=dad)
            held = next(line.account_id for line in txn.lines if line.asset_id == asset.id)
            c.money_from_others.sync_investment(txn.id, txn.date, "Dad", held, asset.id, D(signed))
        return txn

    trade(c.investments.buy_total, "2026-02-02", "10", "1000", "10")
    sale = trade(c.investments.sell_total, "2026-02-03", "10", "1000", "-10")
    c.transactions.void(sale.id, "mistake")
    assert c.investments.holding_for_owner(broker.id, asset.id, "2026-02-05", dad) == 10
    trade(c.investments.sell_total, "2026-02-05", "5", "500", "-5")
    assert c.investments.holding_for_owner(broker.id, asset.id, "2026-02-06", dad) == 5


def test_a_split_line_keeps_whole_cents_its_sign_and_its_own_rate():
    from lightning.core.ledger import split_line_e6
    e6 = 1_000_000
    part, part_base, rest, rest_base = split_line_e6(-100_010_000, 50_123_457, 33_330_000, 100_010_000)
    assert (part, rest) == (-33_330_000, -66_680_000)
    assert (part_base, rest_base) == (-1_670_610_000, -3_342_230_000)
    assert split_line_e6(1_000 * e6, e6, 1, 3)[0] == 333_330_000  # 1,000 x 1/3 rounds to 333.33
    assert split_line_e6(1_000 * e6, e6, 1, 3)[2] == 666_670_000


def test_a_part_tag_is_a_validated_audited_posting(c, monkeypatch):
    """2G3: marking part of a line for someone goes through TransactionService, not a direct ledger write."""
    import lightning.transactions.service as service
    bank = c.account_flows.open_account("CIB", "BANK", "2026-01-01", "0")
    txn = c.transactions.record_inflow("2026-01-02", bank.id, "1000", c.categories.get_by_code("EXP.WORK.SALARY").id)
    c.counterparties.create("Dad", kind="PERSON")
    checked = []
    real = service.validate_posting
    monkeypatch.setattr(service, "validate_posting", lambda lines: checked.append(len(lines)) or real(lines))
    c.money_from_others.sync_transaction(txn.id, "2026-01-02", "Dad", bank.id, Decimal("400"))
    assert checked == [len(c.transactions.get(txn.id).lines)]
    assert sorted(line.quantity for line in c.transactions.get(txn.id).lines if line.account_id == bank.id) == [
        Decimal("400"), Decimal("600")]
    assert c.money_from_others.cash_balance("Dad", bank.id, "2026-01-31") == Decimal("400")
    assert c.db.scalar("SELECT COUNT(*) FROM audit_log WHERE entity='transaction' AND entity_id=? "
                       "AND summary LIKE 'Changed owner%'", (txn.id,)) == 1
    # What is left as yours is checked too: you spent 500 of the 600, so 200 more cannot become Dad's.
    c.transactions.record_outflow("2026-01-03", bank.id, "500", c.categories.get_by_code("EXP.PERSONAL.HOUSING").id)
    before = [(line.quantity, line.owner_id) for line in c.transactions.get(txn.id).lines]
    with pytest.raises(ValidationError, match="user's balance"):
        with c.db.transaction():
            c.money_from_others.sync_transaction(txn.id, "2026-01-02", "Dad", bank.id, Decimal("200"))
    assert [(line.quantity, line.owner_id) for line in c.transactions.get(txn.id).lines] == before


def _tagged_trade(c, record, broker, asset, day, units, total, signed):
    with c.db.transaction():
        txn = record(day, broker.id, asset.id, units, total)
        held = next(line.account_id for line in txn.lines if line.asset_id == asset.id)
        c.money_from_others.sync_investment(txn.id, txn.date, "Dad", held, asset.id, Decimal(signed))
    return txn


def _broker_with_stock(c):
    flows = c.account_flows
    broker = flows.open_account("THNDR", "BROKERAGE", "2026-01-01", "0", institution="THNDR")
    bank = flows.open_account("CIB", "BANK", "2026-01-01", "100000", institution="CIB")
    dad = c.counterparties.create("Dad")
    asset = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI")
    c.transactions.record_transfer("2026-02-01", bank.id, broker.id, "5000")
    return broker, asset, dad


def test_a_voided_tagged_sale_does_not_block_the_next_one_from_the_ledger_alone(c):
    """2G3: the ledger's owner is the one record; investment_custody_events is no longer written."""
    broker, asset, dad = _broker_with_stock(c)
    _tagged_trade(c, c.investments.buy_total, broker, asset, "2026-02-02", "20", "2000", "10")  # 10 are yours
    sale = _tagged_trade(c, c.investments.sell_total, broker, asset, "2026-02-03", "10", "1000", "-10")
    c.transactions.void(sale.id, "mistake")
    assert c.investments.holding_for_owner(broker.id, asset.id, "2026-02-05", dad) == 10
    _tagged_trade(c, c.investments.sell_total, broker, asset, "2026-02-05", "5", "500", "-5")
    assert c.investments.holding_for_owner(broker.id, asset.id, "2026-02-06", dad) == 5
    with pytest.raises(ValidationError, match="not enough units owned by Dad"):
        _tagged_trade(c, c.investments.sell_total, broker, asset, "2026-02-07", "6", "600", "-6")
    assert c.db.scalar("SELECT COUNT(*) FROM investment_custody_events") == 0


def test_investment_history_lists_an_owned_buy_and_sale_from_the_ledger(c):
    """2G3: the same rows the events table gave, now read from ledger lines with an owner."""
    broker, asset, _ = _broker_with_stock(c)
    buy = _tagged_trade(c, c.investments.buy_total, broker, asset, "2026-02-02", "20", "2000", "10")
    sale = _tagged_trade(c, c.investments.sell_total, broker, asset, "2026-02-03", "4", "400", "-4")
    held = next(line.account_id for line in buy.lines if line.asset_id == asset.id)
    found = c.money_from_others.investment_history()
    keys = {"date", "owner", "account_id", "asset_id", "units_e6", "account_name", "asset_name", "unit", "ref", "units"}
    assert [set(row) for row in found] == [keys, keys]
    assert [(row["date"], row["owner"], row["account_id"], row["asset_id"], row["units"], row["ref"])
            for row in found] == [("2026-02-03", "Dad", held, asset.id, Decimal("-4"), sale.ref),
                                  ("2026-02-02", "Dad", held, asset.id, Decimal("10"), buy.ref)]
    assert (found[0]["account_name"], found[0]["asset_name"]) == (c.accounts.get(held).name, asset.name)
    c.transactions.void(sale.id, "mistake")
    assert [row["ref"] for row in c.money_from_others.investment_history()] == [buy.ref]
