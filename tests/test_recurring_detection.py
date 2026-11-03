from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit
import re

from fastapi.testclient import TestClient
from lightning.ui.web import create_app


def record(
    c, setup, name, code, amounts, dates=("2026-07-10", "2026-08-10", "2026-09-10")
):
    account = setup[0]["cib"].id
    category = c.categories.get_by_code(code).id
    for day, amount in zip(dates, amounts):
        c.transactions.record_outflow(
            day, account, str(amount), category, counterparty=name
        )


def offers(c):
    return {s["name"]: s for s in c.planning.suggestions(date(2026, 10, 6))}


def test_fixed_entertainment_is_subscription_after_last_payment(c, setup):
    record(c, setup, "Shahid", "EXP.PERSONAL.ENTERTAINMENT", [99, 99, 99])
    s = offers(c)["Shahid"]
    assert s["kind"] == "SUBSCRIPTION" and s["start_date"] == "2026-10-10"
    assert s["match_tolerance_pct"] == 10 and s["amount"] == Decimal("99")


def test_variable_utilities_get_observed_tolerance_but_outliers_are_refused(c, setup):
    record(c, setup, "Electricity", "EXP.PERSONAL.UTILITIES", [68, 100, 132])
    record(c, setup, "Erratic", "EXP.PERSONAL.UTILITIES", [10, 100, 200])
    found = offers(c)
    assert found["Electricity"]["kind"] == "BILL"
    assert found["Electricity"]["match_tolerance_pct"] == 32
    assert "Erratic" not in found


def test_frequent_or_nonmonthly_purchases_are_not_subscriptions(c, setup):
    record(
        c,
        setup,
        "Daily shop",
        "EXP.PERSONAL.FOOD",
        [100, 100, 100, 100],
        ["2026-07-10", "2026-08-10", "2026-09-10", "2026-09-15"],
    )
    record(
        c,
        setup,
        "Irregular",
        "EXP.PERSONAL.SHOPPING",
        [100, 100, 100],
        ["2026-06-10", "2026-08-10", "2026-09-10"],
    )
    record(
        c,
        setup,
        "Scattered",
        "EXP.PERSONAL.FOOD",
        [100, 100, 100],
        ["2026-07-01", "2026-08-15", "2026-09-28"],
    )
    assert not offers(c)


def test_month_end_start_and_pc_phone_track_parameters(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    record(
        c,
        setup,
        "Month end",
        "EXP.PERSONAL.ENTERTAINMENT",
        [99, 99, 99],
        ["2026-07-31", "2026-08-31", "2026-09-30"],
    )
    s = offers(c)["Month end"]
    assert s["start_date"] == "2026-10-31"
    app = create_app(c)
    for phone in (False, True):

        async def wrapped(scope, receive, send):
            if scope["type"] == "http":
                scope.setdefault("state", {})["phone"] = phone
            await app(scope, receive, send)

        with TestClient(wrapped) as browser:
            page = browser.get("/plan/recurring").text.replace("&amp;", "&")
            links = re.findall(r'href="([^"]*/plan/items/new\?[^"]+)"', page)
            query = next(
                parse_qs(urlsplit(link).query) for link in links if "Month" in link
            )
            assert query["start_date"] == ["2026-10-31"] and query["kind"] == [
                "SUBSCRIPTION"
            ]
            assert query["match_tolerance_pct"] == ["10"]
            form = browser.get(next(link for link in links if "Month" in link)).text
            assert "2026-10-31" in form


def test_dismissed_suggestion_can_be_restored_idempotently_without_money_writes(
    c, setup, monkeypatch
):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    record(c, setup, "Shahid", "EXP.PERSONAL.ENTERTAINMENT", [99, 99, 99])
    s = offers(c)["Shahid"]
    before = c.db.scalar("SELECT COUNT(*) FROM transactions")
    with TestClient(create_app(c)) as client:
        client.post(f"/plan/suggestions/{s['counterparty_id']}/not-recurring")
        assert not offers(c)
        page = client.get("/plan/recurring").text
        assert "Restore suggestion" in page and "Shahid" in page
        for _ in range(2):
            assert (
                client.post(
                    f"/plan/suggestions/{s['counterparty_id']}/restore",
                    follow_redirects=False,
                ).status_code
                == 303
            )
    assert "Shahid" in offers(c)
    assert c.db.scalar("SELECT COUNT(*) FROM transactions") == before
    assert c.db.scalar("SELECT COUNT(*) FROM planned_items") == 0


def test_utility_tolerance_is_confirmable_without_relaxing_other_items(c, setup):
    import pytest
    from lightning.core.errors import ValidationError

    category = c.categories.get_by_code("EXP.PERSONAL.UTILITIES").id
    item = c.planning.create(
        kind="BILL",
        name="Electricity",
        amount="100",
        frequency="MONTHLY",
        start_date="2026-10-10",
        category_id=category,
        match_tolerance_pct="32",
    )
    assert c.planning.get(item).match_tolerance_pct == 32
    c.planning.update(
        item,
        kind="BILL",
        name="Electricity",
        amount="100",
        frequency="MONTHLY",
        start_date="2026-10-10",
        category_id=category,
        match_tolerance_pct="10",
    )
    assert c.planning.get(item).match_tolerance_pct == 10
    assert (
        c.db.scalar(
            "SELECT match_tolerance_override_pct FROM planned_items WHERE id=?", (item,)
        )
        is None
    )
    with pytest.raises(ValidationError, match="25 percent"):
        c.planning.create(
            kind="BILL",
            name="Other bill",
            amount="100",
            frequency="MONTHLY",
            start_date="2026-10-10",
            category_id=setup[1]["EXP.PERSONAL.FOOD"].id,
            match_tolerance_pct="32",
        )


def test_foreign_subscription_uses_native_amount_despite_changing_fx(c, setup):
    from lightning.database.currencies import CurrencyRegistry

    CurrencyRegistry(c.db).register("USD")
    account = c.account_flows.open_account(
        "USD", "BANK", "2026-07-01", "0", institution="Test", currency="USD"
    )
    category = c.categories.get_by_code("EXP.PERSONAL.ENTERTAINMENT").id
    for month, rate in [("07", 50), ("08", 51), ("09", 52)]:
        c.db.execute(
            "INSERT INTO fx_rates(date,base,quote,rate_e6,source,created_at) VALUES(?,?,?,?,?,?)",
            (
                f"2026-{month}-01",
                "USD",
                "EGP",
                rate * 1000000,
                "MANUAL",
                "2026-07-01T00:00:00Z",
            ),
        )
        c.transactions.record_inflow(
            f"2026-{month}-01", account.id, "20", setup[1]["EXP.WORK.SALARY"].id
        )
        c.transactions.record_outflow(
            f"2026-{month}-10", account.id, "9.99", category, counterparty="Stream USD"
        )
    s = offers(c)["Stream USD"]
    assert (
        s["amount"] == Decimal("9.99")
        and s["currency"] == "USD"
        and s["kind"] == "SUBSCRIPTION"
    )


from test_journal_finance import devices  # noqa: F401


def test_restore_uses_existing_synchronized_settings_command(devices):
    home, phone = devices
    phone.command("counterparties.ensure_person", name="Hidden")
    phone.sync_with(home.home)
    party = phone.c.counterparties.resolve("Hidden")
    phone.command(
        "planning.not_recurring",
        counterparty_id=phone.adapter.uid("counterparties", party["id"]),
    )
    phone.sync_with(home.home)
    assert phone.c.planning.dismissed_suggestions()[0]["name"] == "Hidden"
    phone.command(
        "settings.set",
        key="recurring_not_suggested",
        value=phone.c.planning.restored_suggestion_setting(party["id"]),
    )
    phone.sync_with(home.home)
    assert (
        phone.c.planning.dismissed_suggestions()
        == home.c.planning.dismissed_suggestions()
        == []
    )
    assert phone.store.fingerprint() == home.store.fingerprint()


def test_upgrade_preserves_existing_plans_and_payment_links(tmp_path, monkeypatch):
    import shutil
    from lightning.database.connection import Database
    from lightning.database import migrator

    scripts = tmp_path / "old-migrations"
    scripts.mkdir()
    for source in migrator._BUNDLED_MIGRATIONS_DIR.glob("*.sql"):
        if int(source.name[:4]) <= 70:
            shutil.copy(source, scripts / source.name)
    db = Database(tmp_path / "old.db")
    try:
        with monkeypatch.context() as patch:
            patch.setattr(migrator, "MIGRATIONS_DIR", scripts)
            migrator.migrate(db)
        db.execute(
            "INSERT INTO planned_items(id,kind,name,amount_e6,frequency,start_date,created_at,updated_at) VALUES(1,'BILL','Existing',100000000,'MONTHLY','2026-09-01','stamp','stamp')"
        )
        db.execute(
            "INSERT INTO planned_payments(planned_item_id,due_date,status,created_at) VALUES(1,'2026-09-01','SKIPPED','stamp')"
        )
        before = dict(db.one("SELECT * FROM planned_items WHERE id=1"))
        payment = dict(db.one("SELECT * FROM planned_payments"))
        migrator.migrate(db)
        after = dict(db.one("SELECT * FROM planned_items WHERE id=1"))
        assert after.pop("match_tolerance_override_pct") is None and after == before
        assert dict(db.one("SELECT * FROM planned_payments")) == payment
        assert not db.all("PRAGMA foreign_key_check")
    finally:
        db.close()
