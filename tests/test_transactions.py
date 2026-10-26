from decimal import Decimal

import pytest

from lightning.core.errors import ValidationError
from lightning.transactions.domain import TxnFilter


def ids(c, **kw):
    return c.transactions.find(TxnFilter(**kw))


class TestRecording:
    def test_foreign_cash_posting_uses_latest_rate_on_or_before_transaction_date(self, c, setup):
        from lightning.database.currencies import CurrencyRegistry
        _, cats = setup
        CurrencyRegistry(c.db).register("USD")
        usd = c.account_flows.open_account("Dollar account", "BANK", "2026-09-01", "0",
                                           institution="Test Bank", currency="USD")
        c.db.execute(
            "INSERT INTO fx_rates(date,base,quote,rate_e6,source,created_at) VALUES(?,?,?,?,?,?)",
            ("2026-09-01", "USD", "EGP", 48000000, "MANUAL", "2026-09-01T00:00:00Z"),
        )
        # This later quote must not leak into a posting dated before it.
        c.db.execute(
            "INSERT INTO fx_rates(date,base,quote,rate_e6,source,created_at) VALUES(?,?,?,?,?,?)",
            ("2026-09-20", "USD", "EGP", 50000000, "MANUAL", "2026-09-20T00:00:00Z"),
        )

        c.transactions.record_inflow("2026-09-05", usd.id, "100", cats["EXP.WORK.SALARY"].id)
        txn = c.transactions.record_outflow("2026-09-10", usd.id, "2",
                                            cats["EXP.PERSONAL.FOOD"].id)

        assert txn.lines[0].fx_rate == Decimal("48")
        assert txn.lines[0].amount_base == Decimal("-96.00")

    def test_foreign_cash_posting_requires_a_historical_rate(self, c, setup):
        from lightning.database.currencies import CurrencyRegistry
        _, cats = setup
        CurrencyRegistry(c.db).register("USD")
        usd = c.account_flows.open_account("Dollar account", "BANK", "2026-09-01", "0",
                                           institution="Test Bank", currency="USD")

        with pytest.raises(ValidationError, match="No USD/EGP exchange rate"):
            c.transactions.record_outflow("2026-09-10", usd.id, "2",
                                          cats["EXP.PERSONAL.FOOD"].id)

    def test_cross_currency_transfers_remain_rejected(self, c, setup):
        from lightning.database.currencies import CurrencyRegistry
        accounts, _ = setup
        CurrencyRegistry(c.db).register("USD")
        usd = c.account_flows.open_account("Dollar account", "BANK", "2026-09-01", "0",
                                           institution="Test Bank", currency="USD")

        with pytest.raises(ValidationError, match="same currency"):
            c.transactions.record_transfer("2026-09-10", accounts["cib"].id, usd.id, "5")

    def test_outflow(self, setup, c):
        accounts, cats = setup
        t = c.transactions.record_outflow("2026-09-25", accounts["cib"].id, "450", cats["EXP.PERSONAL.FOOD"].id,
                                          "Weekly groceries", "Carrefour")
        assert t.ref == "OUT-2026-09-25-001"
        assert len(t.lines) == 1 and t.lines[0].quantity == Decimal("-450") and t.lines[0].effect == "OUTFLOW"
        assert c.reporting.account_balance(accounts["cib"].id) == Decimal("49550")

    def test_refs_count_per_day_and_type(self, setup, c):
        accounts, cats = setup
        food = cats["EXP.PERSONAL.FOOD"].id
        r1 = c.transactions.record_outflow("2026-09-25", accounts["cib"].id, "1", food).ref
        r2 = c.transactions.record_outflow("2026-09-25", accounts["cib"].id, "1", food).ref
        r3 = c.transactions.record_outflow("2026-09-26", accounts["cib"].id, "1", food).ref
        r4 = c.transactions.record_inflow("2026-09-25", accounts["cib"].id, "1", cats["EXP.WORK.SALARY"].id).ref
        assert (r1, r2, r3, r4) == ("OUT-2026-09-25-001", "OUT-2026-09-25-002", "OUT-2026-09-26-001",
                                    "IN-2026-09-25-001")

    def test_transfer_is_one_document_two_lines(self, setup, c):
        accounts, cats = setup
        t = c.transactions.record_transfer("2026-09-10", accounts["cib"].id, accounts["thndr"].id, "10,000")
        assert t.ref.startswith("TRF-") and len(t.lines) == 2
        assert sum(ln.amount_base for ln in t.lines) == 0
        assert c.reporting.account_balance(accounts["cib"].id) == Decimal("40000")
        assert c.reporting.account_balance(accounts["thndr"].id) == Decimal("10000")
        summary = c.transactions.summarize(t)
        assert summary.account_label == "CIB Current" and summary.to_account_label == "THNDR"

    def test_atm_withdrawal_is_not_spending(self, setup, c):
        accounts, cats = setup
        c.transactions.record_transfer("2026-09-20", accounts["cib"].id, accounts["wallet"].id, "3000")
        c.transactions.record_outflow("2026-09-21", accounts["wallet"].id, "800", cats["EXP.PERSONAL.FOOD"].id)
        flow = c.reporting.cash_flow("2026-09-01", "2026-09-30")
        assert flow.outflows == Decimal("800")  # the withdrawal itself is not spending

    @pytest.mark.parametrize("amount", ["0", "-5", "12.345", "abc", ""])
    def test_bad_amounts(self, setup, c, amount):
        accounts, cats = setup
        with pytest.raises(ValidationError):
            c.transactions.record_outflow("2026-09-10", accounts["cib"].id, amount, cats["EXP.PERSONAL.FOOD"].id)

    def test_category_describes_activity_not_money_direction(self, setup, c):
        accounts, cats = setup
        c.transactions.record_inflow("2026-09-10", accounts["cib"].id, "5", cats["EXP.PERSONAL.FOOD"].id)
        with pytest.raises(ValidationError, match="more specific"):
            c.transactions.record_outflow("2026-09-10", accounts["cib"].id, "5", c.categories.get_by_code("EXP").id)

    def test_transfer_rules(self, setup, c):
        accounts, _ = setup
        with pytest.raises(ValidationError, match="two different"):
            c.transactions.record_transfer("2026-09-10", accounts["cib"].id, accounts["cib"].id, "5")

    def test_future_dates_are_blocked(self, setup, c):
        accounts, cats = setup
        with pytest.raises(ValidationError, match="future"):
            c.transactions.record_outflow("2027-01-01", accounts["cib"].id, "5", cats["EXP.PERSONAL.FOOD"].id)

    def test_historical_transactions_are_not_limited_by_account_start_date(self, setup, c):
        accounts, cats = setup
        txn = c.transactions.record_outflow("2026-08-31", accounts["cib"].id, "5",
                                             cats["EXP.PERSONAL.FOOD"].id)
        assert txn.date == "2026-08-31"


class TestEditingAndVoiding:
    def test_edit_keeps_ref_and_logs_history(self, setup, c):
        accounts, cats = setup
        t = c.transactions.record_outflow("2026-09-25", accounts["cib"].id, "450", cats["EXP.PERSONAL.FOOD"].id)
        edited = c.transactions.update_money(t.id, "2026-09-27", accounts["wallet"].id, "540",
                                             cats["EXP.PERSONAL.FOOD"].id, "Groceries")
        assert edited.ref == t.ref and edited.date == "2026-09-27"
        assert c.reporting.account_balance(accounts["cib"].id) == Decimal("50000")
        assert c.reporting.account_balance(accounts["wallet"].id) == Decimal("660")
        assert c.transactions.history(t.id)[0]["action"] == "edit"

    def test_edit_transfer(self, setup, c):
        accounts, _ = setup
        t = c.transactions.record_transfer("2026-09-10", accounts["cib"].id, accounts["wallet"].id, "100")
        c.transactions.update_transfer(t.id, "2026-09-10", accounts["cib"].id, accounts["thndr"].id, "300")
        assert c.reporting.account_balance(accounts["wallet"].id) == Decimal("1200")
        assert c.reporting.account_balance(accounts["thndr"].id) == Decimal("300")

    def test_register_edit_preserves_transaction_description(self, setup, c):
        accounts, cats = setup
        bank, wallet = accounts["cib"], accounts["wallet"]
        food = cats["EXP.PERSONAL.FOOD"].id
        outflow = c.transactions.record_outflow("2026-09-25", bank.id, "450", food,
                                                description="Weekly groceries")
        edited = c.transactions.update_in_account(outflow.id, bank.id, "2026-09-25", "-500", food,
                                                  counterparty="Carrefour")
        assert edited.description == "Weekly groceries"

        transfer = c.transactions.record_transfer("2026-09-25", bank.id, wallet.id, "100",
                                                  description="Move savings")
        edited_transfer = c.transactions.update_in_account(transfer.id, bank.id, "2026-09-25", "-200",
                                                            other_account_id=wallet.id)
        assert edited_transfer.description == "Move savings"

        # Changing the register row's kind replaces its transaction, but keeps its description too.
        changed_kind = c.transactions.update_in_account(outflow.id, bank.id, "2026-09-25", "-25",
                                                         other_account_id=wallet.id)
        assert changed_kind.type.value == "TRF"
        assert changed_kind.description == "Weekly groceries"

    def test_void_and_restore(self, setup, c):
        accounts, cats = setup
        t = c.transactions.record_outflow("2026-09-25", accounts["cib"].id, "450", cats["EXP.PERSONAL.FOOD"].id)
        c.transactions.void(t.id)
        assert c.reporting.account_balance(accounts["cib"].id) == Decimal("50000")
        assert ids(c, search="450")[1] == 0 and ids(c, search="450", include_void=True)[1] == 1
        with pytest.raises(ValidationError, match="Restore"):
            c.transactions.update_money(t.id, "2026-09-25", accounts["cib"].id, "1", cats["EXP.PERSONAL.FOOD"].id)
        c.transactions.restore(t.id)
        assert c.reporting.account_balance(accounts["cib"].id) == Decimal("49550")

    def test_restore_allows_transaction_before_account_opening_date(self, setup, c):
        accounts, cats = setup
        account = accounts["cib"]
        txn = c.transactions.record_outflow("2026-08-31", account.id, "25", cats["EXP.PERSONAL.FOOD"].id)
        c.transactions.void(txn.id)
        c.transactions.restore(txn.id)
        assert not c.transactions.get(txn.id).is_void

    def test_opening_balance_not_edited_as_a_transaction(self, setup, c):
        accounts, cats = setup
        opening_id = c.transactions.repo.opening_txn_id(accounts["cib"].id)
        with pytest.raises(ValidationError, match="account's edit page"):
            c.transactions.update_money(opening_id, "2026-09-01", accounts["cib"].id, "1", cats["EXP.WORK.SALARY"].id)


class TestSearch:
    @pytest.fixture
    def data(self, setup, c):
        accounts, cats = setup
        c.transactions.record_outflow("2026-09-25", accounts["cib"].id, "450", cats["EXP.PERSONAL.FOOD"].id,
                                      "Weekly groceries", "Carrefour Maadi")
        c.transactions.record_outflow("2026-10-02", accounts["wallet"].id, "35", cats["EXP.PERSONAL.FOOD"].id,
                                      "فول و طعمية", "")
        c.transactions.record_transfer("2026-09-26", accounts["cib"].id, accounts["thndr"].id, "10,000", "Invest")
        return accounts, cats

    @pytest.mark.parametrize("query,expected", [
        ("carrefour", 1), ("carre", 1), ("CARREFOUR maadi", 1), ("450", 1), ("OUT-2026-09-25-001", 1),
        ("2026-09", 5), ("10000", 1), ("10,000", 1), ("THNDR", 1), ("طعمية", 1), ("EXP.PERSONAL.FOOD", 2),
        ("nothing-matches-this", 0), ('"quoted', 0),
    ])
    def test_queries(self, data, c, query, expected):
        assert ids(c, search=query)[1] == expected

    def test_filters(self, data, c):
        accounts, cats = data
        assert ids(c, search="CIB-CUR-EGP")[1] == 3  # searched through the account links, not the ref
        assert ids(c, account_id=accounts["wallet"].id)[1] == 2  # opening + outflow
        assert ids(c, date_from="2026-10-01", date_to="2026-10-31")[1] == 1
        assert ids(c, category_ids=[cats["EXP.PERSONAL.FOOD"].id])[1] == 2

    def test_special_characters_are_literal(self, data, c):
        accounts, cats = data
        c.transactions.record_outflow("2026-10-05", accounts["cib"].id, "5", cats["EXP.PERSONAL.FOOD"].id,
                                      "50% off_sale")
        assert ids(c, search="50%")[1] == 1 and ids(c, search="%")[1] == 1 and ids(c, search="_")[1] == 1

    def test_search_by_category_name_and_notes(self, data, c):
        assert ids(c, search="groceries")[1] == 2  # "Food & Groceries" category name
        assert ids(c, search="personal food")[1] == 2


class TestRegister:
    def test_signed_amount_and_transfers(self, setup, c):
        accounts, cats = setup
        w = accounts["wallet"].id
        out = c.transactions.record_in_account(w, "2026-09-10", "-50", cats["EXP.PERSONAL.FOOD"].id, counterparty="Kiosk")
        assert out.type == "OUT" and out.counterparty == "Kiosk" and out.lines[0].quantity == Decimal("-50")
        inn = c.transactions.record_in_account(w, "2026-09-10", "20", cats["EXP.WORK.SALARY"].id)
        assert inn.type == "IN"
        t1 = c.transactions.record_in_account(w, "2026-09-11", "-100", other_account_id=accounts["cib"].id)
        t2 = c.transactions.record_in_account(w, "2026-09-11", "300", other_account_id=accounts["cib"].id)
        assert c.transactions.summarize(t1).to_account_label == "CIB Current"
        assert c.transactions.summarize(t2).account_label == "CIB Current"
        assert c.reporting.account_balance(w) == Decimal("1200") - 50 + 20 - 100 + 300

    @pytest.mark.parametrize("amount,category,msg", [
        ("0", "EXP.PERSONAL.FOOD", "Enter an amount"),
        ("-50", None, "Choose a category"),
    ])
    def test_register_rules(self, setup, c, amount, category, msg):
        accounts, cats = setup
        cid = cats[category].id if category else None
        with pytest.raises(ValidationError, match=msg):
            c.transactions.record_in_account(accounts["wallet"].id, "2026-09-10", amount, cid)

    def test_typed_category_and_account_lookup(self, setup, c):
        accounts, _ = setup
        find = c.categories.find_by_text
        assert find("Personal › Food & Groceries").code == "EXP.PERSONAL.FOOD"
        assert find("food & groceries").code == "EXP.PERSONAL.FOOD"
        assert find("EXP.WORK.SOFTWARE").code == "EXP.WORK.SOFTWARE"
        assert find("groceries").code == "EXP.PERSONAL.FOOD"  # unique partial match
        with pytest.raises(ValidationError, match="Which one"):
            find("Transportation")  # Personal and Work both have one
        with pytest.raises(ValidationError, match="no category"):
            find("Spaceships")
        assert c.accounts.find_by_text("wallet").id == accounts["wallet"].id
        assert c.accounts.find_by_text("CIB-CUR-EGP · CIB Current").id == accounts["cib"].id
        assert c.accounts.find_by_text("Carrefour") is None


def test_search_finds_a_row_by_the_whole_figure_the_pages_show(c, setup):
    from lightning.transactions.domain import TxnFilter
    accounts, cats = setup
    c.transactions.record_outflow("2026-10-02", accounts["cib"].id, "3250.75", cats["EXP.PERSONAL.FOOD"].id, counterparty="Carrefour")
    found = lambda text: c.transactions.find(TxnFilter(search=text))[1]
    assert found("3250.75") == found("3251") == found("3,251") == 1  # the exact figure and the one the pages round to
    assert found("3252") == 0  # a different whole figure finds nothing
