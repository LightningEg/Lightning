"""Same-category repayments reduce spending; pairing only annotates existing cash."""

from datetime import date
from decimal import Decimal
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ConflictError
from lightning.ui.web import create_app


@pytest.fixture
def payments(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    account = setup[0]["cib"]
    category = c.categories.get_by_code("EXP.WORK.TRANSPORT")
    expense = c.transactions.record_outflow(
        "2026-09-08", account.id, "1200", category.id, counterparty="Uber"
    )
    return account, category, expense


def receipt(c, payments, amount="1200", category=None, payer="ACME", day="2026-09-21"):
    account, original, _ = payments
    return c.transactions.record_inflow(
        day, account.id, amount, (category or original).id, counterparty=payer
    )


def flows(c):
    totals = c.reporting.cash_flow(date(2026, 9, 1), date(2026, 10, 6))
    return totals.inflows, totals.outflows


def state(c, account):
    return (
        c.reporting.account_balance(account.id, "2026-10-06"),
        flows(c),
        [tuple(r) for r in c.db.all("SELECT * FROM ledger_entries ORDER BY id")],
    )


def pairs(c):
    return c.reimbursements.suggested_pairs(date(2026, 10, 6))


def test_unclaimed_same_category_pair_is_suggested_without_creating_money_or_claim(
    c, payments
):
    incoming = receipt(c, payments)
    before = state(c, payments[0])
    (pair,) = pairs(c)
    assert pair["expense_id"] == payments[2].id and pair["receipt_id"] == incoming.id
    assert pair["claim_id"] is None and pair["category_id"] == payments[1].id
    assert pair["amount"] == Decimal("1200") and not pair["ambiguous"]
    assert not c.reimbursements.list_claims()
    assert state(c, payments[0]) == before
    from lightning.workflows.review import ReviewInbox

    assert any(
        i["href"] == "/reimbursements#suggested-pairs"
        for i in ReviewInbox(c).items(date(2026, 10, 6))
    )


def test_partial_receipts_leave_remainder_and_annotation_can_be_undone(c, payments):
    incoming = receipt(c, payments, "600")
    claim = c.reimbursements.create_claim(payments[2].id, "1200")
    (pair,) = pairs(c)
    assert pair["amount"] == Decimal("600") and pair["claim_id"] == claim["id"]
    before = state(c, payments[0])
    link = c.reimbursements.link_receipt(claim["id"], incoming.id, pair["amount"])
    updated = c.reimbursements.list_claims()[0]
    assert updated["outstanding"] == Decimal("600") and updated["received"] == Decimal(
        "600"
    )
    assert state(c, payments[0]) == before and not pairs(c)
    with pytest.raises(ConflictError):
        c.reimbursements.link_receipt(claim["id"], incoming.id, "600")
    undo = c.undo.available()["undo"]
    assert undo and undo["label"] == "Link reimbursement receipt"
    c.undo.replay(expected_id=undo["id"])
    assert link["id"] is not None
    assert c.reimbursements.list_claims()[0]["outstanding"] == Decimal("1200")
    assert len(pairs(c)) == 1 and state(c, payments[0]) == before


def test_payer_category_currency_dates_and_used_receipts_constrain_suggestions(
    c, payments, monkeypatch
):
    salary = c.categories.get_by_code("EXP.WORK.SALARY")
    receipt(c, payments, category=salary)
    receipt(c, payments, day="2026-09-01")
    with monkeypatch.context() as patch:
        patch.setenv("LIGHTNING_TODAY", "2027-02-01")
        receipt(c, payments, day="2027-02-01")
    incoming = receipt(c, payments, payer="Wrong payer")
    payer = c.counterparties.ensure_person("ACME")
    payer_id = c.counterparties.resolve("ACME")["id"]
    c.reimbursements.create_claim(payments[2].id, "1200", payer_id=payer_id)
    assert not pairs(c)
    valid = receipt(c, payments, payer="ACME")
    assert [p["receipt_id"] for p in pairs(c)] == [valid.id]
    c.transactions.void(valid.id, "duplicate")
    assert not pairs(c)
    assert incoming.id != valid.id and payer is not None
    assert not c.reimbursements.suggested_pairs(
        date(2027, 2, 1)
    )  # the February receipt is over 90 days later


def test_ambiguous_expenses_are_choices_not_auto_links(c, payments):
    account, category, _ = payments
    c.transactions.record_outflow(
        "2026-09-09", account.id, "1200", category.id, counterparty="Taxi"
    )
    receipt(c, payments)
    found = pairs(c)
    assert len(found) == 2 and all(p["ambiguous"] for p in found)
    assert c.db.scalar("SELECT COUNT(*) FROM reimbursement_receipts") == 0


def test_partial_unclaimed_and_already_planned_receipts_are_not_guessed(c, payments):
    receipt(c, payments, "600")
    assert not pairs(c)
    incoming = receipt(c, payments)
    item = c.planning.create(
        kind="INCOME",
        name="Already tracked",
        amount="1200",
        frequency="ONCE",
        start_date="2026-09-21",
        account_id=payments[0].id,
        category_id=payments[1].id,
    )
    # Simulate a pre-existing settlement; the suggestion engine must not reuse its receipt.
    c.db.execute(
        "INSERT INTO planned_payments(planned_item_id,due_date,status,transaction_id,amount_e6,created_at) "
        "VALUES(?,?,'PAID',?,1200000000,'stamp')",
        (item, "2026-09-21", incoming.id),
    )
    assert not pairs(c)


@pytest.mark.parametrize("phone", [False, True])
def test_review_prefills_claim_then_confirms_existing_pair_on_pc_and_phone(
    c, payments, phone
):
    incoming = receipt(c, payments)
    original_app = create_app(c)

    async def app(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = phone
        await original_app(scope, receive, send)

    before = state(c, payments[0])
    with TestClient(app) as browser:
        page = browser.get("/reimbursements")
        assert page.status_code == 200 and "Possible reimbursement pairs" in page.text
        url = next(
            link.replace("&amp;", "&")
            for link in re.findall(r'href="([^"]+)"', page.text)
            if "expense_id=" in link
        )
        form = browser.get(url).text
        assert Decimal(
            re.search(r'name="expected" value="([^\"]+)"', form).group(1)
        ) == Decimal("1200")
        values = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        values["transaction_id"] = values.pop("expense_id")
        assert (
            browser.post(
                "/reimbursements", data=values, follow_redirects=False
            ).status_code
            == 303
        )
        claim = c.reimbursements.list_claims()[0]
        (pair,) = pairs(c)
        response = browser.post(
            f"/reimbursements/{claim['id']}/pair",
            data={"receipt_id": incoming.id, "amount": str(pair["amount"])},
        )
        assert response.status_code == 200 and "Linked the receipt" in response.text
        assert c.reimbursements.list_claims()[0]["outstanding"] == 0
        # Double submission cannot duplicate links or cash.
        assert (
            browser.post(
                f"/reimbursements/{claim['id']}/pair",
                data={"receipt_id": incoming.id, "amount": str(pair["amount"])},
            ).status_code
            == 400
        )
    assert c.db.scalar("SELECT COUNT(*) FROM reimbursement_receipts") == 1
    assert state(c, payments[0]) == before


def test_changed_suggestion_is_refused_before_linking(c, payments):
    incoming = receipt(c, payments)
    claim = c.reimbursements.create_claim(payments[2].id, "1200")
    (pair,) = pairs(c)
    c.transactions.update_refund(
        incoming.id,
        "2026-09-21",
        payments[0].id,
        "1200",
        c.categories.get_by_code("EXP.PERSONAL.FOOD").id,
    )
    with TestClient(create_app(c)) as browser:
        response = browser.post(
            f"/reimbursements/{claim['id']}/pair",
            data={"receipt_id": incoming.id, "amount": str(pair["amount"])},
        )
        assert response.status_code == 400 and "suggested pair changed" in response.text
    assert not c.reimbursements.list_claims()[0]["receipts"]


def test_record_repayment_shortcut_preserves_category_and_reduces_spending_once(
    c, payments
):
    account, category, expense = payments
    claim = c.reimbursements.create_claim(expense.id, "1200")
    with TestClient(create_app(c)) as browser:
        page = browser.get("/reimbursements").text
        url = next(
            link.replace("&amp;", "&")
            for link in re.findall(r'href="([^"]+)"', page)
            if "/transaction/new?" in link
        )
        values = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        assert values["kind"] == "in" and values["category_id"] == str(category.id)
        values["date"] = "2026-10-06"
        values["amount"] = "600"
        form = browser.get(url).text
        values["submission"] = re.search(
            r'name="submission" value="([^"]+)"', form
        ).group(1)
        endpoint = urlsplit(url).path
        first = browser.post(endpoint, data=values, follow_redirects=False)
        assert first.status_code == 303 and first.headers["location"].startswith(
            "/reimbursements"
        )
        assert (
            browser.post(endpoint, data=values, follow_redirects=False).status_code
            == 303
        )
        (pair,) = pairs(c)
        assert pair["amount"] == Decimal("600") and pair["claim_id"] == claim["id"]
        before = state(c, account)
        assert (
            browser.post(
                f"/reimbursements/{claim['id']}/pair",
                data={"receipt_id": pair["receipt_id"], "amount": str(pair["amount"])},
            ).status_code
            == 200
        )
    assert state(c, account) == before
    money_in, money_out = flows(c)
    assert money_in == 0 and money_out == Decimal("600")
    assert c.reimbursements.list_claims()[0]["outstanding"] == Decimal("600")


def test_foreign_receipt_does_not_match_equal_base_amount_in_another_currency(
    c, payments
):
    from lightning.database.currencies import CurrencyRegistry

    CurrencyRegistry(c.db).register("USD")
    account = c.account_flows.open_account(
        "USD", "BANK", "2026-09-01", "0", institution="Test", currency="USD"
    )
    c.db.execute(
        "INSERT INTO fx_rates(date,base,quote,rate_e6,source,created_at) VALUES(?,?,?,?,?,?)",
        ("2026-09-01", "USD", "EGP", 50000000, "MANUAL", "2026-09-01T00:00:00Z"),
    )
    c.transactions.record_inflow(
        "2026-09-21", account.id, "24", payments[1].id, counterparty="ACME"
    )
    assert not pairs(c)
    # A foreign claim still stores its expectation in profile currency, never prefill that as USD.
    c.transactions.record_inflow(
        "2026-09-01", account.id, "100", c.categories.get_by_code("EXP.WORK.SALARY").id
    )
    expense = c.transactions.record_outflow(
        "2026-09-08", account.id, "24", payments[1].id
    )
    c.reimbursements.create_claim(expense.id, "1200")
    with TestClient(create_app(c)) as browser:
        page = browser.get("/reimbursements").text
        url = next(
            link.replace("&amp;", "&")
            for link in re.findall(r'href="([^\"]+)"', page)
            if "/transaction/new?" in link
        )
        query = parse_qs(urlsplit(url).query, keep_blank_values=True)
        assert query["amount"] == [""] and query["category_id"] == [str(payments[1].id)]


def test_shared_and_split_cash_is_left_for_manual_review(c, payments):
    owner = c.counterparties.ensure_person("Other owner")
    owner_id = c.counterparties.resolve("Other owner")["id"]
    c.transactions.record_inflow(
        "2026-09-21", payments[0].id, "1200", payments[1].id, owner_id=owner_id
    )
    assert not pairs(c) and owner is not None
    receipt(c, payments)
    assert len(pairs(c)) == 1
    c.transactions.update_expense_split(
        payments[2].id,
        [
            (payments[1].id, "600"),
            (c.categories.get_by_code("EXP.PERSONAL.FOOD").id, "600"),
        ],
    )
    assert not pairs(c)


from test_journal_finance import devices, groups  # noqa: F401


def test_same_category_partial_pair_replays_through_existing_commands(
    devices, monkeypatch
):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    home, phone = devices
    for amount, name in [("-100", "Uber"), ("60", "Employer")]:
        values = groups(phone, amount=amount)
        values["details"]["counterparty"] = name
        phone.save(values)
    phone.sync_with(home.home)
    expense = phone.c.db.scalar("SELECT id FROM transactions WHERE counterparty='Uber'")
    incoming = phone.c.db.scalar(
        "SELECT id FROM transactions WHERE counterparty='Employer'"
    )
    phone.command(
        "reimbursements.create_claim",
        transaction_id=phone.adapter.uid("transactions", expense),
        expected="100",
        payer_id=None,
        due_date=None,
    )
    phone.sync_with(home.home)
    (pair,) = pairs(phone.c)
    assert pair["receipt_id"] == incoming and pair["amount"] == Decimal("60")
    before = phone.balances()
    phone.command(
        "reimbursements.link_receipt",
        claim_id=phone.adapter.uid("reimbursement_claims", pair["claim_id"]),
        transaction_id=phone.adapter.uid("transactions", incoming),
        amount="60",
    )
    phone.sync_with(home.home)
    assert phone.balances() == before
    assert phone.c.reimbursements.list_claims()[0]["outstanding"] == Decimal("40")
    assert home.c.reimbursements.list_claims()[0]["outstanding"] == Decimal("40")
    assert phone.store.fingerprint() == home.store.fingerprint()


def test_sample_uber_and_employer_repayment_are_found_without_a_prebuilt_claim(
    c, monkeypatch
):
    from lightning.samples import SAMPLE_TODAY, load_mohab_2026

    monkeypatch.setenv("LIGHTNING_TODAY", SAMPLE_TODAY.isoformat())
    load_mohab_2026(c)
    claim = c.reimbursements.list_claims()[0]
    expense = claim["expense_id"]
    incoming = claim["receipts"][0]["receipt_id"]
    before = [
        tuple(row) for row in c.db.all("SELECT * FROM ledger_entries ORDER BY id")
    ]
    c.reimbursements.delete_claim(claim["id"])
    found = [
        pair
        for pair in c.reimbursements.suggested_pairs(SAMPLE_TODAY)
        if pair["expense_id"] == expense and pair["receipt_id"] == incoming
    ]
    assert len(found) == 1 and found[0]["amount"] == Decimal("1200")
    assert (
        found[0]["expense"]["date"] == "2026-06-08"
        and found[0]["receipt"]["date"] == "2026-06-21"
    )
    assert [
        tuple(row) for row in c.db.all("SELECT * FROM ledger_entries ORDER BY id")
    ] == before
