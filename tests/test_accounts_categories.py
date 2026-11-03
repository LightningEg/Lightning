from decimal import Decimal

import pytest

from lightning.categories.domain import Movement
from lightning.core.errors import ConflictError, NotFoundError, ValidationError
from lightning.transactions.domain import TxnFilter


class TestAccounts:
    def test_codes_are_suggested_and_unique(self, c):
        a = c.account_flows.open_account("CIB Current", "BANK", "2026-09-01", institution="CIB")
        b = c.account_flows.open_account("CIB Payroll", "BANK", "2026-09-01", institution="CIB")
        assert a.code == "CIB-CUR-EGP" and b.code == "CIB-CUR-EGP-2"
        assert a.label == "CIB Current"

    def test_duplicate_manual_code_rejected(self, c):
        c.account_flows.open_account("A", "BANK", "2026-09-01", code="MY-BANK")
        with pytest.raises(ConflictError):
            c.account_flows.open_account("B", "BANK", "2026-09-01", code="my-bank")

    def test_opening_balance_is_a_transaction(self, c):
        a = c.account_flows.open_account("CIB Current", "BANK", "2026-09-01", "50,000")
        assert c.reporting.account_balance(a.id) == Decimal("50000")
        found, total = c.transactions.find(TxnFilter())
        assert total == 1 and found[0].ref == "OPN-2026-09-01-001"

    def test_debt_accounts_are_not_offered(self, c):
        for retired in ("CREDIT_CARD", "LOAN", "PAYABLE"):
            with pytest.raises(ValidationError):
                c.account_flows.open_account("X", retired, "2026-09-01")

    def test_opening_balance_cannot_be_negative(self, c):
        with pytest.raises(ValidationError, match="negative"):
            c.account_flows.open_account("Wallet", "CASH", "2026-09-01", "-5")

    def test_cash_class_follows_where_cash_sits(self, c):
        wallet = c.account_flows.open_account("Wallet", "CASH", "2026-09-01", "100")
        bank = c.account_flows.open_account("Bank", "BANK", "2026-09-01", "200")
        cd = c.account_flows.open_account("CIB CD", "DEPOSIT", "2026-09-01")
        with pytest.raises(ValidationError, match="cannot hold cash"):
            c.account_flows.open_account("NBE CD", "DEPOSIT", "2026-09-01", "300")
        classes = {c.assets.get_class(a.cash_class_id).code for a in (wallet, bank, cd)}
        assert classes == {"CASH.PHYSICAL", "CASH.BANK", "DEPOSIT.CD"}
        assert c.accounts.reporting_group(bank) == "Liquid Cash › Bank Balance"
        assert c.accounts.reporting_group(cd) == "Deposits › CDs / Time Deposits"

    def test_group_follows_type_on_edit(self, c):
        a = c.account_flows.open_account("QNB", "DEPOSIT", "2026-09-01")
        a = c.account_flows.update_account(a.id, "QNB Savings", "BANK", "2026-09-01", "100")
        assert c.assets.get_class(a.cash_class_id).code == "CASH.BANK"

    def test_account_start_date_does_not_limit_existing_transactions(self, setup, c):
        accounts, cats = setup
        c.transactions.record_outflow("2026-09-10", accounts["wallet"].id, "5", cats["EXP.PERSONAL.FOOD"].id)
        c.account_flows.update_account(accounts["wallet"].id, "Wallet", "CASH", "2026-09-11", "1200",
                                       opening_balance_date="2026-09-01")

    def test_editing_opening_balance_and_date(self, c):
        a = c.account_flows.open_account("Bank", "BANK", "2026-09-01", "100")
        c.account_flows.update_account(a.id, "Bank", "BANK", "2026-08-15", "250")
        assert c.reporting.account_balance(a.id) == Decimal("250")
        assert c.reporting.account_balance(a.id, "2026-08-14") == Decimal("0")
        opening = c.transactions.get(c.transactions.repo.opening_txn_id(a.id))
        assert opening.ref == "OPN-2026-09-01-001"  # ref never changes
        assert opening.date == "2026-08-15"
        c.account_flows.update_account(a.id, "Bank", "BANK", "2026-08-15", "")
        assert c.reporting.account_balance(a.id) == Decimal("0")

    def test_generated_codes_keep_whole_words(self, c):
        a = c.account_flows.open_account("Cash at hand", "CASH", "2026-09-01")
        assert a.code == "CASH-AT-HAND-CSH-EGP"

    def test_deactivate_requires_zero_balance(self, setup, c):
        accounts, cats = setup
        with pytest.raises(ConflictError, match="Move the balance"):
            c.account_flows.deactivate(accounts["wallet"].id)
        assert c.account_flows.deactivate(accounts["thndr"].id).active is False
        with pytest.raises(ValidationError, match="inactive"):
            c.transactions.record_transfer("2026-09-10", accounts["cib"].id, accounts["thndr"].id, "10")

    def test_foreign_currency_accounts_require_registration_and_a_dated_opening_rate(self, c):
        from lightning.database.currencies import CurrencyRegistry

        with pytest.raises(ValidationError, match="not registered"):
            c.account_flows.open_account("XYZ", "BANK", "2026-09-01", currency="XYZ")
        CurrencyRegistry(c.db).register("USD")
        with pytest.raises(ValidationError, match="exchange rate"):
            c.account_flows.open_account("USD", "BANK", "2026-09-01", "100", currency="USD")
        c.fx.save("USD", "2026-09-01", "50")
        account = c.account_flows.open_account("USD", "BANK", "2026-09-01", "100", currency="USD")
        assert c.reporting.account_balance(account.id) == Decimal("100")
        assert c.reporting.account_value(account.id, "2026-09-01") == Decimal("5000")

    def test_last4_only(self, c):
        with pytest.raises(ValidationError):
            c.account_flows.open_account("Bank", "BANK", "2026-09-01", last4="4111111111111111")

    def test_account_cannot_start_in_the_future(self, c):
        with pytest.raises(ValidationError, match="future"):
            c.account_flows.open_account("Bank", "BANK", "2027-01-01")

    def test_rename_is_found_by_search_immediately(self, setup, c):
        accounts, cats = setup
        c.transactions.record_outflow("2026-09-10", accounts["cib"].id, "10", cats["EXP.PERSONAL.FOOD"].id)
        c.account_flows.update_account(accounts["cib"].id, "Main Bank", "BANK", "2026-09-01", "50000",
                                       institution="CIB", code="CIB-MAIN-EGP")
        assert c.transactions.find(TxnFilter(search="CIB-MAIN-EGP"))[1] == 2  # opening + outflow
        assert c.transactions.find(TxnFilter(search="CIB-CUR-EGP"))[1] == 0


class TestCategories:
    def test_child_inherits_direction_and_scope(self, c):
        work = c.categories.get_by_code("EXP.WORK")
        cat = c.categories.create(work.id, "Coworking Space")
        assert cat.code == "EXP.WORK.COWORKING_SPACE"
        assert cat.movement.value == "OUTFLOW" and cat.scope.value == "WORK" and cat.default_reimbursable

    def test_full_code_accepted(self, c):
        personal = c.categories.get_by_code("EXP.PERSONAL")
        assert c.categories.create(personal.id, "Pets", "EXP.PERSONAL.PETS").code == "EXP.PERSONAL.PETS"

    def test_arabic_name_needs_a_code(self, c):
        personal = c.categories.get_by_code("EXP.PERSONAL")
        with pytest.raises(ValidationError):
            c.categories.create(personal.id, "مواصلات")
        assert c.categories.create(personal.id, "مواصلات", "MICROBUS").name == "مواصلات"

    def test_categories_go_to_l3_and_stop_there(self, c):
        food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
        groceries = c.categories.create(food.id, "Groceries")
        assert groceries.code == "EXP.PERSONAL.FOOD.GROCERIES" and groceries.depth == 3
        with pytest.raises(ValidationError, match="stop at L3"):
            c.categories.create(groceries.id, "Vegetables")
        assert groceries.id in {category.id for category in c.categories.pickable()}
        assert c.categories.find_by_text("Groceries").id == groceries.id
        table = dict((l1.name, rows) for l1, rows in c.categories.table())
        assert list(table) == ["Personal", "Work", "Investment", "System Categories"]
        personal = [(row["category"].name, row["level"], row["has_children"]) for row in table["Personal"]]
        assert ("Food & Groceries", 2, True) in personal and ("Groceries", 3, False) in personal
        assert personal.index(("Groceries", 3, False)) == personal.index(("Food & Groceries", 2, True)) + 1
        # Ledger exceptions live together in System Categories, and keep working there.
        system = [row["category"].code for row in table["System Categories"]]
        assert {"EXP.SYSTEM.CUSTODY", "EXP.SYSTEM.LOANS", "EXP.SYSTEM.TRANSFERS",
                "EXP.SYSTEM.CAPITAL", "EXP.SYSTEM.ADJUSTMENT"} <= set(system)

    def test_direction_soft_groups_income_and_expense(self, c):
        table = dict((l1.name, rows) for l1, rows in c.categories.table())
        signs = [row["category"].sign for row in table["Work"] if row["level"] == 2]
        assert signs == sorted(signs, key="+−±".index)  # + income first, then − expense, then ± both
        meals = c.categories.get_by_code("EXP.WORK.MEALS")
        c.categories.set_direction(meals.id, "BOTH")
        assert c.categories.get(meals.id).sign == "±"
        c.categories.set_direction(meals.id, "IN")
        meals = c.categories.get(meals.id)
        assert meals.sign == "+" and meals.income_class is not None and meals.scope is None
        c.categories.set_direction(meals.id, "OUT")
        meals = c.categories.get(meals.id)
        assert meals.sign == "−" and meals.income_class is None and meals.scope.value == "WORK"
        with pytest.raises(ValidationError):
            c.categories.set_direction(c.categories.get_by_code("EXP.SYSTEM.CUSTODY").id, "OUT")

    def test_archived_categories_leave_the_table(self, c):
        travel = c.categories.get_by_code("EXP.PERSONAL.ENTERTAINMENT")
        c.categories.update(travel.id, travel.name, active=False)
        names = {row["category"].name for _, rows in c.categories.table() for row in rows}
        assert "Entertainment" not in {row["category"].name for l1, rows in c.categories.table() if l1.name == "Personal" for row in rows}
        assert travel.id in {category.id for category in c.categories.archived()}

    def test_category_suggestions_flag_near_duplicates(self, c):
        matches = c.categories.suggestions("Food and Groceries", c.categories.get_by_code("EXP.PERSONAL").id)
        assert matches and matches[0][0].code == "EXP.PERSONAL.FOOD"

    def test_bulk_category_actions_archive_activate_and_delete(self, c, monkeypatch):
        import asyncio
        from lightning.ui.routes import categories as category_routes

        personal = c.categories.get_by_code("EXP.PERSONAL")
        first = c.categories.create(personal.id, "Bulk Test A")
        second = c.categories.create(personal.id, "Bulk Test B")

        class Form(dict):
            def getlist(self, key):
                value = self.get(key, [])
                return value if isinstance(value, list) else [value]

        class Request:
            def __init__(self, form):
                self.data = form

            async def form(self):
                return self.data

        monkeypatch.setattr(category_routes, "container", lambda _request: c)
        monkeypatch.setattr(category_routes, "redirect", lambda path, message: (path, message))
        response = asyncio.run(category_routes.category_bulk_action(Request(Form(
            action="archive", category_ids=[str(first.id), str(second.id)]))))
        assert response[0] == "/categories"
        assert not c.categories.get(first.id).active and not c.categories.get(second.id).active

        asyncio.run(category_routes.category_bulk_action(Request(Form(
            action="activate", category_ids=[str(first.id), str(second.id)]))))
        assert c.categories.get(first.id).active and c.categories.get(second.id).active

        asyncio.run(category_routes.category_bulk_action(Request(Form(action="delete", category_id=str(first.id)))))
        with pytest.raises(NotFoundError):
            c.categories.get(first.id)

    def test_roots_and_system_categories_are_protected(self, c):
        with pytest.raises(ValidationError):
            c.categories.update(c.categories.get_by_code("EXP").id, "Expenses", active=False)
        with pytest.raises(ValidationError):
            c.categories.update(c.categories.get_by_code("EXP.UNACCOUNTED").id, "X", code="OOPS")

    def test_inactive_hidden_from_forms(self, c):
        food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
        c.categories.update(food.id, food.name, active=False)
        assert food.id not in {x.id for x in c.categories.pickable(Movement.OUTFLOW)}
        personal = c.categories.get_by_code("EXP.PERSONAL")
        c.categories.update(personal.id, personal.name, active=False)
        dining = c.categories.get_by_code("EXP.PERSONAL.DINING")
        assert dining.id not in {x.id for x in c.categories.pickable(Movement.OUTFLOW)}


def test_categories_table_edits_in_place_and_keeps_flags_with_the_budget(c):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    client = TestClient(create_app(c))
    page = client.get("/categories").text
    assert "Personal" in page and "System Categories" in page and 'class="cat-item level-2' in page
    assert "Personal ›" not in page  # names, never a breadcrumb list
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    r = client.post("/categories/add-row", data={"parent_id": food.id, "name": "Groceries", "direction": "OUT"})
    assert r.status_code == 200 and "Added Groceries under Food &amp; Groceries" in r.text
    groceries = c.categories.get_by_code("EXP.PERSONAL.FOOD.GROCERIES")
    assert 'class="cat-item level-3' in client.get("/categories").text
    travel = c.categories.get_by_code("EXP.PERSONAL.ENTERTAINMENT")
    client.post(f"/categories/{travel.id}/row", data={"name": "Entertainment", "direction": "OUT", "one_off": "1"})
    assert travel.id in c.budgets.one_off_ids()
    saved = client.post(f"/categories/{travel.id}/row", data={"name": "Entertainment", "direction": "OUT", "one_off": ""},
                        headers={"X-Requested-With": "fetch"})
    assert saved.status_code == 204 and travel.id not in c.budgets.one_off_ids()  # saved in place, toggled off
    client.post(f"/categories/{travel.id}/row", data={"name": "Entertainment", "direction": "OUT", "one_off": "1"})
    bonus = c.categories.get_by_code("EXP.WORK.BONUS")
    salary = c.categories.get_by_code("EXP.WORK.SALARY")
    assert salary.id in c.budgets.recurring_income_ids() and bonus.id not in c.budgets.recurring_income_ids()
    client.post(f"/categories/{bonus.id}/row", data={"name": "Bonus", "direction": "IN", "recurring": "1"})
    assert bonus.id in c.budgets.recurring_income_ids()
    client.post(f"/categories/{groceries.id}/row", data={"action": "archive"})
    assert not c.categories.get(groceries.id).active
    assert "Archived (1)" in client.get("/categories").text


def test_one_off_spending_stays_in_cash_flow_but_out_of_the_budget(c, setup):
    accounts, cats = setup
    travel = c.categories.get_by_code("EXP.PERSONAL.ENTERTAINMENT")
    c.transactions.record_outflow("2026-09-12", accounts["cib"].id, "5000", travel.id)
    c.transactions.record_outflow("2026-09-13", accounts["cib"].id, "200", cats["EXP.PERSONAL.FOOD"].id)
    before = c.budgets.month_view("2026-09", schedule=c.schedules.view())
    c.budgets.set_one_off(travel.id, True)
    after = c.budgets.month_view("2026-09", schedule=c.schedules.view())
    personal = lambda view: next(g for s in view.sections for g in s.groups if g.name == "Personal")
    assert personal(before).actual == 5200 and personal(after).actual == 200
    assert after.one_off == 5000
    assert c.reporting.cash_flow("2026-09-01", "2026-09-30").outflows == 5200  # cash flow still sees it


def test_category_pickers_group_under_l1_and_never_show_breadcrumbs(c):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    c.categories.create(food.id, "Groceries")
    groups = {g["label"]: g["options"] for g in c.categories.select_groups()}
    assert list(groups)[:4] == ["Personal", "Work", "Investment", "System Categories"]
    names = [(o["name"], o["level"], o["header"]) for o in groups["Personal"]]
    at = names.index(("Food & Groceries", 2, True))
    assert names[at + 1] == ("Groceries", 3, False)  # the detail sits under its L2
    page = TestClient(create_app(c)).get("/counterparties").text
    assert '<optgroup label="Personal">' in page and "Personal › " not in page


def test_a_fresh_profile_has_no_travel_category(c):
    names = {row["category"].name for l1, rows in c.categories.table() if l1.name in ("Personal", "Work") for row in rows}
    assert "Travel" not in names
    for code in ("EXP.PERSONAL.TRAVEL", "EXP.WORK.TRAVEL"):
        with pytest.raises(NotFoundError):
            c.categories.get_by_code(code)


def test_account_form_says_cash_not_cash_at_hand_and_has_no_more_details(c):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    page = client.get("/accounts/new").text
    assert ">Cash<" in page and "Cash at hand" not in page
    assert "More details" not in page and 'name="last4"' not in page and 'name="notes"' in page


def test_editing_an_account_keeps_its_last4(c):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    a = c.account_flows.open_account("CIB Current", "BANK", "2026-09-01", "100", institution="CIB", last4="1234")
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    r = client.post(f"/accounts/{a.id}/edit", data={"name": "CIB Main", "account_type": "BANK", "institution": "CIB",
                    "opening_balance_date": "2026-09-01", "notes": ""}, follow_redirects=False)
    assert r.status_code == 303
    assert c.accounts.get(a.id).last4 == "1234" and c.accounts.get(a.id).name == "CIB Main"
