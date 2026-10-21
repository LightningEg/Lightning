"""The HTML UI end to end: every page renders, forms create real records."""

import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from lightning.ui.web import create_app


@pytest.fixture
def client(c):
    return TestClient(create_app(c))


def test_register_category_picker_data_groups_children_under_alphabetical_parents(c):
    from lightning.ui.routes.register import _lists

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(container=c)))
    choices = _lists(request)["category_choices"]
    parents = list(dict.fromkeys(row["parent"] for row in choices))
    assert parents == sorted(parents, key=str.casefold)
    assert all(row["label"] == f"{row['parent']} › {row['name']}" for row in choices)


def test_welcome_then_first_account(client, c):
    r = client.get("/")
    assert r.status_code == 200 and "Where do you keep your money?" in r.text
    r = client.post("/accounts/new", data={"name": "CIB Current", "institution": "CIB", "account_type": "BANK",
                                           "opening_balance_date": "2026-09-01", "opening_balance": "50,000"})
    assert r.status_code == 200 and "CIB Current" in r.text and "CIB-CUR-EGP" not in r.text
    r = client.get("/")
    assert "What you own" in r.text and "50,000" in r.text


def test_full_flow(client, c):
    client.post("/accounts/new", data={"name": "CIB Current", "account_type": "BANK", "institution": "CIB",
                                       "opening_balance_date": "2026-09-01", "opening_balance": "50000"})
    client.post("/accounts/new", data={"name": "Wallet", "account_type": "CASH",
                                       "opening_balance_date": "2026-09-01", "opening_balance": "1000"})
    cib = c.accounts.find_by_text("CIB Current")
    wallet = c.accounts.find_by_text("Wallet")
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")

    # the sidebar lists every account with its balance
    page = client.get(f"/accounts/{cib.id}")
    sidebar_total = re.search(r'<span>In your accounts</span><span class="num"[^>]*>([^<]+)</span>', page.text)
    assert sidebar_total and sidebar_total.group(1) == "51,000" and "CIB Current" in page.text
    assert "CIB-CUR-EGP" not in page.text  # ordinary account UI leads with the name, not its code

    r = client.post(f"/accounts/{cib.id}/register", data={"date": "2026-09-25", "counterparty": "Carrefour",
                    "counterparty_choice": "create", "category": "Personal › Food & Groceries",
                    "amount": "-450", "notes": "Groceries"})
    assert r.status_code == 200 and "Saved OUT-2026-09-25-001" in r.text
    txn = c.transactions.get_by_ref("OUT-2026-09-25-001")

    # one of your accounts as Counterparty = a transfer (no category needed)
    r = client.post(f"/accounts/{cib.id}/register", data={"date": "2026-09-26", "counterparty": "Wallet", "amount": "-2000"})
    assert "Saved TRF-2026-09-26-001" in r.text

    # validation errors re-render the register with the message and the typed values
    r = client.post(f"/accounts/{cib.id}/register", data={"date": "2026-13-01", "category": "food & groceries",
                    "amount": "-12"})
    assert r.status_code == 400 and 'value="-12"' in r.text

    # search inside the register
    r = client.get(f"/accounts/{cib.id}?q=carrefour")
    assert "Carrefour" in r.text and 'class="pill transfer"' not in r.text

    # edit in place: the row becomes a form, saving keeps the ref
    r = client.get(f"/accounts/{cib.id}?edit={txn.id}&acct={cib.id}")
    assert 'id="f-edit"' in r.text and 'value="-450.00"' in r.text
    r = client.post(f"/accounts/{cib.id}/register/{txn.id}", data={"date": "2026-09-25", "counterparty": "Carrefour",
                    "category": "Personal › Food & Groceries", "amount": "-540", "notes": ""})
    assert "Saved OUT-2026-09-25-001" in r.text
    assert c.reporting.account_balance(cib.id) == 50000 - 540 - 2000

    # void from the edit bar returns to the register
    r = client.post(f"/transactions/{txn.id}/void?back=/accounts/{cib.id}")
    assert "is void" in r.text and r.url.path == f"/accounts/{cib.id}"
    r = client.post(f"/transactions/{txn.id}/restore")
    assert "restored" in r.text

    r = client.get("/?month=2026-09")
    assert "What you own" in r.text and "Free cash" in r.text
    assert "Where money in went" in client.get("/birdview/expenses?month=2026-09").text  # on Spending since 2026-10-21

    r = client.post(f"/accounts/{wallet.id}/deactivate")
    assert "Move the balance" in r.text

    assert client.get("/t/OUT-2026-09-25-001", follow_redirects=False).status_code == 303


def test_all_accounts_register(client, c, setup):
    accounts, cats = setup
    wallet, cib = accounts["wallet"], accounts["cib"]
    r = client.post("/transactions/register", data={"date": "2026-09-20", "account_id": wallet.id, "counterparty": "Kiosk",
                    "counterparty_choice": "create", "category": "Food & Groceries", "amount": "-30"})
    assert "Saved OUT-2026-09-20-001" in r.text
    t = client.post("/transactions/register", data={"date": "2026-09-21", "account_id": cib.id,
                    "counterparty": wallet.label, "amount": "-100"})
    assert "Saved TRF" in t.text
    page = client.get("/transactions")
    assert page.text.count('class="pill transfer"') == 2  # one row per account
    r = client.post("/transactions/register", data={"date": "2026-09-21", "counterparty": "Wallet", "amount": "-100"})
    assert r.status_code == 400 and "Choose an account" in r.text


def test_edit_changing_kind_replaces_transaction(client, c, setup):
    accounts, cats = setup
    w, cib = accounts["wallet"], accounts["cib"]
    txn = c.transactions.record_transfer("2026-09-10", cib.id, w.id, "100")
    r = client.post(f"/accounts/{w.id}/register/{txn.id}", data={"date": "2026-09-10", "counterparty": "Kiosk",
                    "counterparty_choice": "create", "category": "Food & Groceries", "amount": "-100"})
    assert "Saved as OUT-2026-09-10-001" in r.text
    assert c.transactions.get(txn.id).is_void
    assert c.reporting.account_balance(w.id) == 1100


@pytest.mark.parametrize("path", ["/", "/accounts", "/accounts/new", "/transactions", "/transactions?q=x&month=2026-09",
                                  "/accounts/1", "/accounts/1?month=2026-09", "/categories", "/settings",
                                  "/categories/new?parent=1", "/transactions/1"])
def test_pages_render(client, setup, path):
    assert client.get(path).status_code == 200


def test_overview_invalid_custom_range_keeps_mode_and_dates(client, c):
    c.account_flows.open_account("Wallet", "CASH", "2026-09-01", "1000")  # an empty Lightning shows the welcome page
    # Reports are picked by the month: an end month before the start month is refused, and the
    # page keeps Custom and both months so the user can fix them.
    response = client.get("/?period=custom&date_from=2026-10&date_to=2026-09")
    assert response.status_code == 200
    assert "The end month must be the same as or after the start month." in response.text
    assert 'name="period" value="custom" class="period-button selected"' in response.text
    assert 'name="date_from" value="2026-10"' in response.text
    assert 'name="date_to" value="2026-09"' in response.text


def test_overview_horizons_keep_the_same_status_layout_and_popup_range(client, c):
    wallet = c.account_flows.open_account("Wallet", "CASH", "2026-09-01", "1000")
    c.transactions.record_outflow("2026-09-10", wallet.id, "1", c.categories.get_by_code("EXP.PERSONAL.FOOD").id)
    for query in ("period=all", "period=ytd", "period=month&month=2026-09",
                  "period=custom&date_from=2026-09-10&date_to=2026-09-20"):
        response = client.get(f"/?{query}")
        assert response.status_code == 200
        labels = ("What you own", "Free cash", "Net flow")
        assert [response.text.index(label) for label in labels] == sorted(response.text.index(label) for label in labels)
        assert 'class="overview-disclosure"' in response.text
        assert 'name="period" value="custom"' in response.text
        assert 'href="/plan"' in response.text  # Free cash links to cash planning
    popup = client.get("/explain/flow?period=custom&date_from=2026-09-10&date_to=2026-09-20")
    assert popup.status_code == 200
    assert "/?period=custom&amp;date_from=2026-09-10&amp;date_to=2026-09-20" in popup.text


def test_birdview_other_assets_has_no_empty_disclosure(client, setup):
    response = client.get("/birdview")
    assert response.status_code == 200
    assert "What it is made of" in response.text
    assert "If you sold today" in response.text


def test_not_found(client):
    assert client.get("/accounts/999").status_code == 404
    assert client.get("/t/OUT-2000-01-01-001").status_code == 404


def test_category_pages(client, c):
    personal = c.categories.get_by_code("EXP.PERSONAL")
    r = client.post(f"/categories/new?parent={personal.id}", data={"name": "Pets", "code": ""})
    assert "Added Pets under Personal" in r.text
    pets = c.categories.get_by_code("EXP.PERSONAL.PETS")
    r = client.post(f"/categories/{pets.id}/edit", data={"name": "Pets & Vet", "code": "PETS", "active": "1"})
    assert "Category saved" in r.text and c.categories.get(pets.id).name == "Pets & Vet"


def test_backup_button(client, c):
    r = client.post("/settings/backup")
    files = c.backup_files()
    assert len(files) == 1
    assert f"Backup saved as {files[0].name}" in r.text
    assert re.fullmatch(r"test_backup_\d{4}-\d{2}-\d{2}_001_[0-9a-f]{8}\.db", files[0].name)


def test_register_entry(client, c, setup):
    accounts, cats = setup
    wallet, cib = accounts["wallet"], accounts["cib"]
    page = client.get(f"/accounts/{wallet.id}")
    assert 'action="/accounts/%d/register"' % wallet.id in page.text
    assert 'id="category-catalogue"' in page.text and 'role="listbox"' in page.text
    assert 'list="category-options"' not in page.text
    assert "Payee" not in page.text and ">Counterparty<" in page.text
    assert "EXP.PERSONAL" not in page.text  # plain names only

    r = client.post(f"/accounts/{wallet.id}/register", data={"date": "2026-09-20", "counterparty": "Carrefour",
                    "counterparty_choice": "create", "category": "Personal › Food & Groceries",
                    "amount": "-150", "notes": "milk"})
    assert "Saved OUT-2026-09-20-001" in r.text and 'title="Personal › Food &amp; Groceries">Food &amp; Groceries<' in r.text
    assert c.reporting.account_balance(wallet.id) == 1200 - 150

    r = client.post(f"/accounts/{wallet.id}/register", data={"date": "2026-09-21", "counterparty": "CIB Current",
                    "amount": "500"})
    assert "Saved TRF-2026-09-21-001" in r.text
    assert c.reporting.account_balance(wallet.id) == 1200 - 150 + 500
    assert c.reporting.account_balance(cib.id) == 50000 - 500

    # The signed register records the direction the user entered, even for a
    # regular category whose usual direction differs.
    r = client.post(f"/accounts/{wallet.id}/register", data={"date": "2026-09-22", "counterparty": "Employer",
                    "counterparty_choice": "create", "category": "Salary", "amount": "-99"})
    assert r.status_code == 200 and "Saved OUT-2026-09-22-001" in r.text
    assert c.reporting.account_balance(wallet.id) == 1200 - 150 + 500 - 99

    # an ambiguous category name asks which one
    r = client.post(f"/accounts/{wallet.id}/register", data={"date": "2026-09-22", "category": "Transportation",
                    "amount": "-10"})
    assert r.status_code == 400 and "Choose a broad category" in r.text

    # a transfer to the same account is refused
    r = client.post(f"/accounts/{wallet.id}/register", data={"date": "2026-09-22", "counterparty": "Wallet", "amount": "-1"})
    assert r.status_code == 400 and "same account" in r.text

    # Counterparty remembers its category
    page = client.get(f"/accounts/{wallet.id}")
    assert "Carrefour" in page.text and "Personal › Food &amp; Groceries" in page.text


def test_account_form_has_no_class_picker(client):
    r = client.get("/accounts/new")
    assert "cash_class_code" not in r.text and "Shown under" not in r.text and " › " not in r.text.split("<main", 1)[-1]
    assert "Credit card" not in r.text and "Loan" not in r.text


def test_settings_registers_and_selects_profile_currencies(client, c):
    from lightning.database.currencies import CurrencyRegistry

    CurrencyRegistry(c.db).register("USD")
    page = client.get("/settings?section=currencies")
    assert 'data-currency-search' in page.text
    assert 'data-search="usd us dollar"' in page.text.lower()
    assert 'Set active' in page.text and 'Active' in page.text
    fx_page = client.get('/settings?section=currencies&tab=rates')
    assert 'FX reevaluation history' in fx_page.text and 'name="currency"' in fx_page.text
    assert client.post("/settings/currency", data={"action": "base", "base_currency": "USD"}).status_code == 200
    assert c.settings.base_currency == "USD"


def test_fullscreen_control_is_only_in_settings(client):
    assert 'data-fullscreen-toggle' not in client.get('/').text
    assert 'data-fullscreen-toggle' in client.get('/settings').text


def test_account_form_offers_registered_currencies(client, c):
    from lightning.database.currencies import CurrencyRegistry

    CurrencyRegistry(c.db).register("USD")
    page = client.get("/accounts/new")
    assert 'id="currency" name="currency"' in page.text
    assert '<option value="USD" >USD — US Dollar</option>' in page.text or 'USD — US Dollar' in page.text


def test_other_currency_accounts_show_native_balance_and_unavailable_conversion(client, c):
    from lightning.database.currencies import CurrencyRegistry

    CurrencyRegistry(c.db).register("USD")
    client.post("/accounts/new", data={"name": "Dollar wallet", "account_type": "CASH", "currency": "USD",
                                       "opening_balance_date": "2026-09-01", "opening_balance": "0"})
    page = client.get("/accounts/currencies")
    assert "Dollar wallet" in page.text and "0.00" in page.text and "Unavailable" in page.text
    main = client.get("/accounts")
    assert "Dollar wallet" in main.text and "Unavailable" in main.text


def test_settings_saves_and_lists_dated_fx_rates(client, c):
    from lightning.core.dates import today
    from lightning.database.currencies import CurrencyRegistry

    CurrencyRegistry(c.db).register("USD")
    response = client.post("/settings/fx-rate", data={"currency": "USD", "date": today().isoformat(), "rate": "31.5"})
    assert response.status_code == 200
    page = client.get("/settings?section=currencies&tab=rates")
    assert "USD" in page.text and "31.5" in page.text


def test_categories_page_is_plain(client):
    r = client.get("/categories")
    assert "Food &amp; Groceries" in r.text and "EXP.PERSONAL.FOOD" not in r.text


def test_counterparties_tab_lists_and_creates_canonical_names(client, c):
    page = client.get("/counterparties")
    assert page.status_code == 200 and "Counterparties" in page.text
    response = client.post("/counterparties", data={"name": "Talabat"})
    assert response.status_code == 200 and "Review this Counterparty" in response.text
    response = client.post("/counterparties", data={"name": "Talabat", "counterparty_action": "create"})
    assert response.status_code == 200 and "Saved Talabat" in response.text
    assert "Talabat" in client.get("/counterparties").text


def test_counterparty_review_offers_canonical_match_or_explicit_new_name(client, c, setup):
    accounts, _ = setup
    cib = accounts["cib"]
    canonical_id = c.counterparties.create("Talabat")
    values = {"date": "2026-09-25", "counterparty": "Talabaat",
              "category": "Food & Groceries", "amount": "-20"}
    response = client.post(f"/accounts/{cib.id}/register", data=values)
    assert response.status_code == 400 and "Review this Counterparty" in response.text
    assert "Use Talabat" in response.text and "Create “Talabaat”" in response.text
    assert c.counterparties.resolve("Talabaat") is None

    response = client.post(f"/accounts/{cib.id}/register", data={**values,
                          "counterparty_choice": f"existing:{canonical_id}"})
    assert response.status_code == 200 and c.counterparties.resolve("Talabaat")["id"] == canonical_id


def test_category_create_requires_review_when_a_similar_l2_exists(client, c):
    personal = c.categories.get_by_code("EXP.PERSONAL")
    response = client.post(f"/categories/new?parent={personal.id}", data={"name": "Food and Groceries"})
    assert response.status_code == 400 and "Check for a similar category" in response.text
    assert "Use Food &amp; Groceries <small>in Personal</small>" in response.text
    assert c.db.scalar("SELECT 1 FROM categories WHERE code=?", ("EXP.PERSONAL.FOOD_AND_GROCERIES",)) is None


def test_register_selection_controls_and_bulk_delete_work(client, c, setup):
    accounts, cats = setup
    account = accounts["cib"]
    txn = c.transactions.record_outflow("2026-09-25", account.id, "25", cats["EXP.PERSONAL.FOOD"].id)
    page = client.get(f"/accounts/{account.id}")
    assert 'id="select-visible"' in page.text
    assert 'id="delete-selected"' in page.text
    assert '/static/app.js?' in page.text
    assert "<td>Money out</td>" not in page.text

    response = client.post("/transactions/bulk-delete", data={"back": f"/accounts/{account.id}", "txn_ids": str(txn.id)})
    assert response.status_code == 200 and response.url.path == f"/accounts/{account.id}"
    assert "Deleted 1 transaction" in response.text
    assert c.transactions.get(txn.id).is_void
    assert c.reporting.account_balance(account.id) == 50_000


def test_register_manual_counterparty_alias_uses_canonical_record(client, c, setup):
    accounts, cats = setup
    account = accounts["cib"]
    counterparty_id = c.counterparties.create("Talabat", alias="Talabaat")
    response = client.post(f"/accounts/{account.id}/register", data={
        "date": "2026-09-20", "counterparty": "Talabaat", "category": "Food & Groceries", "amount": "-25"
    })
    assert response.status_code == 200
    row = c.db.one("SELECT counterparty,counterparty_id FROM transactions WHERE counterparty_id=?", (counterparty_id,))
    assert row["counterparty"] == "Talabat" and row["counterparty_id"] == counterparty_id


def test_register_near_match_requires_explicit_reuse_or_create(client, c, setup):
    accounts, cats = setup
    account = accounts["cib"]
    c.counterparties.create("Talabat")
    values = {"date": "2026-09-20", "counterparty": "Talabaat",
              "category": "Food & Groceries", "amount": "-25"}
    response = client.post(f"/accounts/{account.id}/register", data=values)
    assert response.status_code == 400 and "Review this Counterparty" in response.text
    assert c.db.scalar("SELECT COUNT(*) FROM transactions WHERE counterparty='Talabat'") == 0
    counterparty_id = c.counterparties.resolve("Talabat")["id"]
    response = client.post(f"/accounts/{account.id}/register", data={**values, "counterparty_choice": f"existing:{counterparty_id}"})
    assert response.status_code == 200
    row = c.db.one("SELECT counterparty,counterparty_id FROM transactions WHERE counterparty_id=?", (counterparty_id,))
    assert row["counterparty"] == "Talabat" and row["counterparty_id"] == counterparty_id


def test_register_learns_alias_and_fills_the_usual_category(client, c, setup):
    accounts, cats = setup
    account = accounts["cib"]
    food = cats["EXP.PERSONAL.FOOD"].id
    talabat = c.counterparties.create("Talabat")
    c.counterparties.create("Careem")
    for day in ("2026-09-01", "2026-09-02"):
        c.transactions.record_outflow(day, account.id, "10", food, counterparty="Talabat")
    # Typed "Talabaat", then picked Talabat from the list: the spelling becomes an alias, and with no
    # category typed the transaction is filed under Talabat's usual category.
    response = client.post(f"/accounts/{account.id}/register", data={
        "date": "2026-09-20", "counterparty": "Talabat", "counterparty_typed": "Talabaat", "amount": "-25"})
    assert response.status_code == 200
    assert c.counterparties.resolve("Talabaat")["id"] == talabat
    row = c.db.one("SELECT le.category_id FROM transactions t JOIN ledger_entries le ON le.transaction_id=t.id "
                   "WHERE t.date='2026-09-20' AND le.category_id IS NOT NULL")
    assert row["category_id"] == food
    # A different name picked instead of what was typed is not a spelling: no alias.
    client.post(f"/accounts/{account.id}/register", data={
        "date": "2026-09-21", "counterparty": "Careem", "counterparty_typed": "Uber", "category": "Food & Groceries", "amount": "-25"})
    assert c.counterparties.resolve("Uber") is None
    # The register picker offers the usual category for autofill.
    page = client.get(f"/accounts/{account.id}")
    assert '"Talabat": {"id": %d' % food in page.text.replace("&#34;", '"')


def test_the_period_picked_in_a_header_carries_over_between_pages(client, c, setup):
    first = client.get("/birdview/expenses?period=month&month=2026-08")
    assert first.status_code == 200
    moved = client.get("/budget", follow_redirects=False)
    assert moved.status_code == 303 and "period=month" in moved.headers["location"] and "month=2026-08" in moved.headers["location"]
    other = client.get("/investments?msg=Saved", follow_redirects=False)  # other parameters are kept
    assert "msg=Saved" in other.headers["location"] and "month=2026-08" in other.headers["location"]
    client.get("/?period=ytd")  # a new pick replaces the old one
    assert "period=ytd" in client.get("/budget", follow_redirects=False).headers["location"]
    client.get("/budget?period=month&month=2999-01")  # a pick that fails is not remembered
    assert "period=ytd" in client.get("/budget", follow_redirects=False).headers["location"]


def test_start_fresh_sets_the_database_aside_and_opens_an_empty_one(client, c, setup):
    from pathlib import Path
    accounts, cats = setup
    c.transactions.record_outflow("2026-09-10", accounts["cib"].id, "25", cats["EXP.PERSONAL.FOOD"].id)
    old_path = Path(c.db.path)
    # The UI's async test client uses a portal thread, while this fixture seeded
    # its database on the test thread. Release that thread-local SQLite handle as
    # well; Windows does not allow renaming a database while any thread holds it.
    # Avoid a separate GET first: TestClient may use a short-lived portal thread
    # per request, whose thread-local SQLite handle cannot be closed by this test.
    c.db.close()
    response = client.post("/settings/fresh", follow_redirects=False)
    from urllib.parse import unquote
    assert response.status_code == 303 and "Started a fresh database" in unquote(response.headers["location"])
    fresh = client.app.state.container
    assert Path(fresh.db.path) == old_path and fresh.accounts.list() == []
    kept = [p for p in old_path.parent.iterdir() if "_before-fresh_" in p.name]
    assert len(kept) == 1  # nothing deleted: the old data sits beside the new file
    import sqlite3
    assert sqlite3.connect(kept[0]).execute("SELECT COUNT(*) FROM transactions").fetchone()[0] >= 1
    assert c.backup_files()  # and a backup was taken first
    fresh.db.close()


# The period picked in a page header is remembered, but "this month" moves on with the calendar (review 2026-10-04).
def test_this_month_moves_on_and_a_past_month_stays(c, setup, monkeypatch):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    client = TestClient(create_app(c))
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-31")
    client.get("/budget?period=month&month=2026-10")                      # the current month
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-01")
    assert client.get("/budget", follow_redirects=False).headers["location"].endswith("month=2026-11")
    client.get("/budget?period=month&month=2026-08")                      # a past month on purpose
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-12-01")
    assert client.get("/budget", follow_redirects=False).headers["location"].endswith("month=2026-08")
