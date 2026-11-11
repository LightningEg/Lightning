"""Zakat is an estimate by the common rule (Architecture › Zakat): 2.5% of zakatable wealth at or above the nisab
(85 g of 24K gold). Built from the one position calculation; money held for others never counts; a payment is
ordinary spending in the Zakat category and lowers Still to pay only inside the zakat year."""
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app
from lightning.zakat import LUNAR_YEAR_DAYS, zakat_days

D = Decimal
GOLD_24K = D("3000")        # EGP a gram, so the nisab is 85 × 3,000 = 255,000
NISAB = D("255000")


@pytest.fixture(autouse=True)
def zakat_on(c):
    c.zakat.set_enabled(True)   # off by default (owner, 2026-10-14); test_zakat_is_off_until_turned_on checks that


@pytest.fixture
def gold(c):
    reference = c.assets.get_asset_by_code("REF:GLD-24K")
    c.assets.set_price(reference.id, "2026-09-01", str(GOLD_24K))
    return reference


def _bank(c, amount, day="2026-01-01"):
    return c.account_flows.open_account("CIB", "BANK", day, str(amount))


def _lines(found):
    return {line.key: line for line in found.lines}


def test_the_nisab_is_85_grams_of_24k_gold_at_the_days_price(c, gold):
    found = c.zakat.assess("2026-12-31")
    assert (found.nisab, found.nisab_source, found.nisab_date) == (NISAB, "gold", "2026-09-01")
    c.assets.set_price(gold.id, "2026-12-01", "3100")
    assert c.zakat.assess("2026-12-31").nisab == D("263500")
    assert c.zakat.assess("2026-11-30").nisab == NISAB     # the price of that day, not today's


def test_the_nisab_follows_another_karat_when_there_is_no_24k_price(c):
    c.assets.set_price(c.assets.get_asset_by_code("GLD:18K").id, "2026-09-01", "2250")  # 18K is 3/4 of 24K
    assert c.zakat.assess("2026-12-31").nisab == NISAB


def test_below_the_nisab_nothing_is_due_and_at_the_nisab_it_is_two_and_a_half_percent(c, gold):
    bank = _bank(c, "254999.99")
    below = c.zakat.assess("2026-12-31")
    assert below.zakatable_wealth == D("254999.99") and below.reaches_nisab is False
    assert below.zakat_due == D("0")
    c.transactions.record_inflow("2026-12-01", bank.id, "0.01", c.categories.get_by_code("EXP.WORK.BONUS").id)
    at = c.zakat.assess("2026-12-31")
    assert at.zakatable_wealth == NISAB and at.reaches_nisab is True
    assert at.zakat_due == D("6375.00")                      # 2.5% of 255,000


def test_a_typed_nisab_stands_in_only_without_a_gold_price(c):
    _bank(c, "100000")
    assert c.zakat.assess("2026-12-31").zakat_due is None
    assert "nisab" in c.zakat.assess("2026-12-31").unavailable_reason
    c.zakat.save_settings(None, "90000", False, True)
    found = c.zakat.assess("2026-12-31")
    assert (found.nisab, found.nisab_source, found.nisab_date) == (D("90000"), "typed", "2026-12-31")
    assert found.zakat_due == D("2500.00")
    gold = c.assets.get_asset_by_code("REF:GLD-24K")
    c.assets.set_price(gold.id, "2026-09-01", str(GOLD_24K))
    assert c.zakat.assess("2026-12-31").nisab_source == "gold"
    assert c.zakat.settings().typed_nisab == D("90000")      # kept, dated, for when the gold price goes missing


def test_the_lines_come_from_the_position_and_add_up(c, gold, setup):
    accounts, _ = setup                                     # CIB 50,000, wallet 1,200, a CD account 5,000
    c.transactions.record_transfer("2026-12-05", accounts["cib"].id, accounts["thndr"].id, "10000")
    found = c.zakat.assess("2026-12-31")
    position = c.position.at(date(2026, 12, 31))
    lines = _lines(found)
    assert lines["cash"].amount == position.cash_you_own == D("51200")   # THNDR's cash is cash you own
    assert lines["deposits"].amount == position.deposits == D("5000")
    assert found.zakatable_wealth == sum(line.signed for line in found.lines) == D("56200")


def test_shares_funds_and_gold_are_counted_at_full_value(c, gold):
    broker = c.account_flows.open_account("THNDR", "BROKERAGE", "2026-01-01", "0", institution="THNDR")
    bank = _bank(c, "1000")
    share = c.assets.create_investment("Test Bank", "STOCK", "TBNK")
    fund = c.assets.create_investment("Test Fund", "FUND.EQUITY", "TFND")
    c.investments.add_holding(broker.id, share.id, "100", "5000", "2026-01-02")
    c.investments.add_holding(broker.id, fund.id, "10", "2000", "2026-01-02")
    c.assets.set_price(share.id, "2026-12-01", "70")
    c.assets.set_price(fund.id, "2026-12-01", "300")
    c.transactions.record_inflow("2026-12-02", bank.id, "10", c.categories.get_by_code("EXP.WORK.BONUS").id)
    lines = _lines(c.zakat.assess("2026-12-31"))
    assert lines["shares"].amount == D("7000") + D("3000")  # the latest price, not the sale-factor value
    assert lines["cash"].amount == D("1010")


def _gold_piece(c, worn=False, grams="10", karat=24):
    home = next((a for a in c.accounts.list() if a.name == "Gold at home"), None) or \
        c.account_flows.open_account("Gold at home", "PHYSICAL_ASSET", "2026-01-01", "0")
    reference = c.assets.get_asset_by_code("REF:GLD-24K")
    item = c.physical_items.create(home.id, f"Bracelet {grams}", "Bracelet", grams, karat, reference.id, worn=worn)
    c.investments.add_holding(home.id, item, "1", "20000", "2026-01-02")
    return item


def test_gold_you_hold_is_counted_and_gold_you_wear_only_with_the_setting(c, gold):
    _bank(c, "1000")
    _gold_piece(c, worn=False)                                # 10 g × 3,000 = 30,000
    _gold_piece(c, worn=True, grams="5")                      #  5 g × 3,000 = 15,000
    found = c.zakat.assess("2026-12-31")
    lines = _lines(found)
    assert lines["gold"].amount == D("30000")
    assert lines["worn"].amount == D("15000") and lines["worn"].counted is False
    assert found.zakatable_wealth == D("31000")
    c.zakat.save_settings(None, "", True, True)
    found = c.zakat.assess("2026-12-31")
    assert _lines(found)["worn"].counted is True and found.zakatable_wealth == D("46000")


def test_marking_a_piece_as_worn_is_saved_and_audited(c, gold):
    item = _gold_piece(c)
    assert c.physical_items.get(item)["worn"] == 0 and c.physical_items.worn_asset_ids() == set()
    old = c.physical_items.get(item)
    c.physical_items.update(item, "Bracelet", "Bracelet", "10", 24, old["reference_asset_id"], "", worn=True)
    assert c.physical_items.worn_asset_ids() == {item}
    c.physical_items.update(item, "Bracelet", "Bracelet", "12", 24, old["reference_asset_id"])   # unchanged flag
    assert c.physical_items.get(item)["worn"] == 1


def test_money_held_for_others_never_counts(c, gold):
    bank = _bank(c, "1000")
    custody = c.categories.get_by_code("EXP.SYSTEM.CUSTODY")
    dad = c.counterparties.get(c.counterparties.create("Dad"))["name"]
    receipt = c.transactions.record_in_account(bank.id, "2026-09-10", "500000", custody.id)
    c.money_from_others.sync_transaction(receipt.id, receipt.date, dad, bank.id, D("500000"))
    found = c.zakat.assess("2026-12-31")
    assert c.position.at(date(2026, 12, 31)).held_for_others == D("500000")
    assert _lines(found)["cash"].amount == D("1000") and found.zakat_due == D("0")


def test_debts_due_now_are_taken_off_only_with_the_setting(c, gold):
    _bank(c, "300000")
    c.planning.create(kind="BILL", name="Rent", amount="60000", frequency="MONTHLY", start_date="2026-12-20")
    on = c.zakat.assess("2026-12-31")
    assert _lines(on)["debts"].amount == D("60000") and _lines(on)["debts"].signed == D("-60000")
    assert on.zakatable_wealth == D("240000") and on.zakat_due == D("0")          # under the nisab once the rent is off
    c.zakat.save_settings(None, "", False, False)
    off = c.zakat.assess("2026-12-31")
    assert _lines(off)["debts"].counted is False and off.zakatable_wealth == D("300000")
    assert off.zakat_due == D("7500.00")


def test_a_missing_price_means_no_estimate_not_zero(c, gold):
    _bank(c, "300000")
    c.currencies.register("USD")                              # dollars whose only rate is a year old: no value today
    c.fx.save("USD", "2026-01-01", "48")
    c.account_flows.open_account("Dollars", "BANK", "2026-01-01", "1000", currency="USD")
    found = c.zakat.assess("2026-12-31")
    assert found.zakat_due is None and "price is missing" in found.unavailable_reason


def test_the_zakat_day_is_picked_once_and_the_next_is_354_days_later():
    first = "2026-03-01"
    assert zakat_days(first, date(2026, 1, 1)) == (date(2025, 3, 12), date(2026, 3, 1))
    assert zakat_days(first, date(2026, 3, 1)) == (date(2025, 3, 12), date(2026, 3, 1))     # the day itself
    previous, following = zakat_days(first, date(2026, 3, 2))
    assert (previous, (following - previous).days) == (date(2026, 3, 1), LUNAR_YEAR_DAYS)
    assert following == date(2027, 2, 18)
    assert zakat_days(first, date(2027, 2, 19))[1] == date(2028, 2, 7)
    assert zakat_days("", date(2026, 1, 1)) is None


def test_settings_are_validated_and_audited(c):
    with pytest.raises(ValidationError):
        c.zakat.save_settings("not a date", "", False, True)
    with pytest.raises(ValidationError):
        c.zakat.save_settings(None, "0", False, True)
    assert c.zakat.settings().count_worn_gold is False and c.zakat.settings().deduct_debts_due is True
    c.zakat.save_settings("2026-03-01", "255000", True, False)
    saved = c.zakat.settings()
    assert (saved.zakat_day, saved.typed_nisab, saved.count_worn_gold, saved.deduct_debts_due) == (
        "2026-03-01", D("255000"), True, False)
    assert c.audit.history("zakat_settings", 1)[0]["action"] == "edit"
    c.zakat.save_settings("", "", False, True)
    assert c.zakat.settings().zakat_day is None and c.zakat.settings().typed_nisab is None


def _pay(c, bank, day, amount):
    category = c.categories.get_by_code("EXP.SYSTEM.ZAKAT")
    c.transactions.record_outflow(day, bank.id, str(amount), category.id, "Zakat")


def test_paying_in_the_zakat_category_lowers_still_to_pay_and_a_payment_before_the_year_does_not(c, gold):
    bank = _bank(c, "400000")
    c.zakat.save_settings("2026-12-31", "", False, True)      # the zakat year runs 2026-01-11 (354 days earlier) to 2026-12-31
    before = c.zakat.assess("2026-12-31")
    assert before.zakat_due == D("10000.00") and (before.paid, before.still_to_pay) == (D("0"), D("10000.00"))
    assert before.previous_day == "2026-01-11"
    _pay(c, bank, "2026-01-11", "700")                         # on the previous zakat day: that year's, not this one's
    assert c.zakat.assess("2026-12-31").paid == D("0")
    _pay(c, bank, "2026-06-01", "4000")
    c.zakat.save_settings("2026-12-31", "", False, True)
    # the payment also lowered the cash (400,000 − 700 − 4,000), so the due amount follows what is left
    found = c.zakat.assess("2026-12-31")
    assert found.paid == D("4000") and found.zakatable_wealth == D("395300")
    assert found.zakat_due == D("9882.50") and found.still_to_pay == D("5882.50")
    _pay(c, bank, "2026-12-20", "9000")
    assert c.zakat.assess("2026-12-31").still_to_pay == D("0")  # never below zero


def test_the_zakat_category_is_a_normal_spending_category(c):
    category = c.categories.get_by_code("EXP.SYSTEM.ZAKAT")
    assert category.name == "Zakat" and category.movement.value == "OUTFLOW" and not category.is_system
    assert category in c.categories.pickable()
    bank = _bank(c, "1000")
    _pay(c, bank, "2026-12-01", "100")
    assert c.reporting.cash_flow("2026-12-01", "2026-12-31").outflows == D("100")   # spending: it leaves net flow


def test_the_forecast_line_is_the_next_zakat_day_and_what_is_still_to_pay(c, gold):
    _bank(c, "400000")
    assert c.zakat.forecast("2026-12-31") is None             # nothing until a zakat day is set
    c.zakat.save_settings("2027-03-01", "", False, True)
    line = c.zakat.forecast("2026-12-31")
    assert (line.day, line.amount) == ("2027-03-01", D("10000.00"))
    before = c.position.at(date(2026, 12, 31)).what_you_own
    c.zakat.forecast("2026-12-31")
    assert c.position.at(date(2026, 12, 31)).what_you_own == before   # a forecast moves nothing


def test_the_page_says_it_is_an_estimate_once_and_shows_the_figures(c, gold):
    _bank(c, "400000")
    c.zakat.save_settings("2026-12-31", "", False, True)
    page = TestClient(create_app(c)).get("/zakat")
    assert page.status_code == 200
    for text in ("Zakatable wealth", "Nisab", "Zakat due", "Paid this zakat year", "Still to pay", "10,000",
                 "zakat day today", "lunar year", "scholar"):
        assert text in page.text, text
    assert page.text.count("a scholar answers your own case") == 1


def test_the_gear_saves_the_settings_and_the_first_time_form_keeps_the_rest(c, gold):
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    assert "Zakat settings" in client.get("/settings?section=zakat").text
    saved = client.post("/zakat/settings", data={"zakat_day": "2027-03-01", "typed_nisab": "90000",
                                                 "count_worn_gold": "1"}, follow_redirects=False)
    assert saved.status_code == 303 and "Zakat%20settings%20saved" in saved.headers["location"]
    settings = c.zakat.settings()
    assert (settings.zakat_day, settings.typed_nisab, settings.count_worn_gold, settings.deduct_debts_due) == (
        "2027-03-01", D("90000"), True, False)                # an unticked box is off
    client.post("/zakat/settings", data={"only_day": "1", "zakat_day": "2027-04-01"})
    settings = c.zakat.settings()
    assert (settings.zakat_day, settings.typed_nisab, settings.count_worn_gold) == ("2027-04-01", D("90000"), True)
    refused = client.post("/zakat/settings", data={"zakat_day": "2027-04-01", "typed_nisab": "-5"}, follow_redirects=False)
    assert "nisab" in refused.headers["location"].lower() and c.zakat.settings().typed_nisab == D("90000")


def _phone(app):
    async def phone_app(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)
    return phone_app


def test_the_page_works_on_a_phone_and_in_arabic(c, gold):
    _bank(c, "400000")
    c.zakat.save_settings("2026-12-31", "", False, True)
    for phone in (False, True):
        app = create_app(c)
        client = TestClient(_phone(app) if phone else app, base_url="http://127.0.0.1")
        assert "10,000" in client.get("/zakat").text
        client.post("/settings/locale", data={"locale": "ar"})
        arabic = client.get("/zakat").text
        assert "الزكاة المستحقة" in arabic and ">Zakat due<" not in arabic and "Zakatable wealth<" not in arabic
        client.post("/settings/locale", data={"locale": "en"})


def test_the_plan_names_the_zakat_day_and_the_worn_box_reaches_the_service(c, gold):
    _bank(c, "400000")
    c.planning.create(kind="INCOME", name="Salary", amount="30000", frequency="MONTHLY", start_date="2026-12-25")
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    assert "Zakat day" not in client.get("/plan").text        # nothing until a zakat day is set
    c.zakat.save_settings("2027-03-01", "", False, True)
    plan = client.get("/plan").text
    assert "1 Mar 2027" in plan and "10,000" in plan and "changes no balance" in plan
    home = c.account_flows.open_account("Gold at home", "PHYSICAL_ASSET", "2026-01-01", "0")
    reference = c.assets.get_asset_by_code("REF:GLD-24K")
    made = client.post(f"/accounts/{home.id}/items/new", data={
        "name": "Bangle", "kind": "Bangle", "weight": "10", "karat": "24", "reference_asset_id": str(reference.id),
        "details": "", "worn": "1"}, follow_redirects=False)
    assert made.status_code == 303 and len(c.physical_items.worn_asset_ids()) == 1
    item = next(iter(c.physical_items.worn_asset_ids()))
    assert "I wear this piece" in client.get(f"/accounts/{home.id}/items/{item}/edit").text


def test_gameya_paid_in_counts_and_instalments_due_on_a_pot_taken_early_come_off(c):
    bank = _bank(c, "300000")
    early = c.account_flows.open_account("Office gam'eya", "GAMEYA", "2026-01-01", "0")
    c.gameya.save_terms(early.id, organiser="Um Ali", members=10, installment="2000", first_date="2026-01-05",
                        my_turn=2, funding_account_id=bank.id, payout_account_id=bank.id)
    c.gameya.record_instalment(early.id, "2026-01-05")
    c.gameya.record_payout(early.id, "2026-02-05")                    # took 20,000 with 2,000 paid in
    late = c.account_flows.open_account("Family gam'eya", "GAMEYA", "2026-09-01", "0")
    c.gameya.save_terms(late.id, organiser="Aunt Hoda", members=10, installment="2000", first_date="2026-09-05",
                        my_turn=10, funding_account_id=bank.id, payout_account_id=bank.id)
    c.gameya.record_instalment(late.id, "2026-09-05")                 # its October instalment is late: saving, not debt
    lines = _lines(c.zakat.assess("2026-10-10"))
    assert lines["gameya_paid"].amount == D("2000")
    assert lines["gameya_due"].amount == D("18000") and lines["gameya_due"].minus      # nine due, capped at 18,000 owed
    assert c.zakat.assess("2026-10-10").zakatable_wealth == D("316000") + D("2000") - D("18000")
    for day in ("2026-02-05", "2026-03-05", "2026-04-05"):
        c.gameya.record_instalment(early.id, day)
    assert _lines(c.zakat.assess("2026-10-10"))["gameya_due"].amount == D("12000")
    c.zakat.save_settings(None, "", False, False)
    assert not _lines(c.zakat.assess("2026-10-10"))["gameya_due"].counted


def test_zakat_is_off_until_turned_on_in_settings_and_then_shows_everywhere(tmp_path):
    from lightning.bootstrap import build
    fresh = build(tmp_path / "fresh.db")
    try:
        client = TestClient(create_app(fresh))
        assert fresh.zakat.enabled() is False and fresh.zakat.forecast("2026-12-31") is None
        accounts = client.get("/accounts").text
        assert 'href="/zakat"' not in accounts
        page = client.get("/zakat", follow_redirects=False)
        assert page.status_code in (302, 303) and page.headers["location"].startswith("/settings")
        assert client.get("/settings?section=zakat", follow_redirects=False).status_code in (302, 303)
        settings = client.get("/settings").text
        assert "Show zakat" in settings and "Zakat settings" not in settings
        found = client.get("/search?q=zakat&format=json").json()["results"]
        assert not any(row["href"] == "/zakat" for row in found)
        on = client.post("/zakat/enabled", data={"on": "1"})
        assert on.status_code == 200 and "Zakat is on." in on.text and "What counts" in on.text
        assert 'href="/zakat"' in client.get("/accounts").text
        assert "Zakat settings" in client.get("/settings").text
        off = client.post("/zakat/enabled", data={})
        assert "Zakat is off." in off.text and fresh.zakat.enabled() is False
    finally:
        fresh.db.close()


SILVER = D("50")            # EGP a gram of pure silver, so the silver nisab is 595 × 50 = 29,750


def test_the_silver_nisab_is_595_grams_and_the_lower_basis_picks_the_smaller(c, gold):
    """NF-9D6: gold stays the default; silver is 595 g at the typed gram price; the lower basis takes the smaller."""
    assert c.zakat.settings().nisab_basis == "gold"
    c.zakat.save_nisab_basis("silver", "50")
    found = c.zakat.assess("2026-12-31")
    assert (found.nisab, found.nisab_source, found.nisab_date) == (D("29750"), "silver", "2026-12-31")
    c.zakat.save_nisab_basis("lower", "50")
    assert (c.zakat.assess("2026-12-31").nisab, c.zakat.assess("2026-12-31").nisab_source) == (D("29750"), "lower")
    c.zakat.save_nisab_basis("lower", "500")              # 595 × 500 = 297,500 is above gold's 255,000
    assert c.zakat.assess("2026-12-31").nisab == NISAB
    c.zakat.save_nisab_basis("gold", "500")
    assert c.zakat.assess("2026-12-31").nisab_source == "gold"
    with pytest.raises(ValidationError):
        c.zakat.save_nisab_basis("copper", "")


def test_a_missing_silver_price_gives_no_estimate_and_says_why(c):
    _bank(c, "400000")
    c.zakat.save_nisab_basis("silver", "")
    found = c.zakat.assess("2026-12-31")
    assert found.nisab is None and found.zakat_due is None and "silver price" in found.unavailable_reason
    c.zakat.save_settings(None, "30000", False, True)     # a typed nisab still stands in
    assert c.zakat.assess("2026-12-31").nisab_source == "typed"


def test_the_gear_saves_the_nisab_basis(c, gold):
    """NF-9D7: three radio choices and the silver price in the gear; the page names the basis, PC, phone, Arabic."""
    _bank(c, "400000")
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    assert "Silver (595 g)" in client.get("/settings?section=zakat").text
    client.post("/zakat/settings", data={"zakat_day": "2026-12-31", "nisab_basis": "silver", "typed_silver": "50"})
    settings = c.zakat.settings()
    assert (settings.nisab_basis, settings.typed_silver, settings.zakat_day) == ("silver", SILVER, "2026-12-31")
    for phone in (False, True):
        app = create_app(c)
        page = TestClient(_phone(app) if phone else app, base_url="http://127.0.0.1")
        assert "595 g of silver at the price of today" in page.get("/zakat").text
        page.post("/settings/locale", data={"locale": "ar"})
        assert "595 جرام فضة" in page.get("/zakat").text
        page.post("/settings/locale", data={"locale": "en"})


def test_an_older_profile_keeps_its_zakat_settings_and_takes_gold(monkeypatch, tmp_path):
    """Migration 0077: a profile at schema 76 keeps its day and typed nisab, and gets the gold basis."""
    import shutil

    from lightning.database import migrator
    from lightning.database.connection import Database

    old = tmp_path / "migrations_76"
    old.mkdir()
    for path in migrator.MIGRATIONS_DIR.glob("*.sql"):
        if int(path.name[:4]) <= 76:
            shutil.copy(path, old / path.name)
    bundled = migrator.MIGRATIONS_DIR
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", old)
    db = Database(tmp_path / "old.db")
    migrator.migrate(db)
    db.execute("UPDATE zakat_settings SET zakat_day='2026-03-01',typed_nisab_e6=90000000000 WHERE id=1")
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", bundled)
    migrator.migrate(db)
    row = db.one("SELECT * FROM zakat_settings WHERE id=1")
    assert (row["zakat_day"], row["typed_nisab_e6"], row["nisab_basis"], row["typed_silver_e6"]) == (
        "2026-03-01", 90000000000, "gold", None)
    migrator.migrate(db)                                   # a second run does nothing
    assert migrator.inspect_schema(db).current_version == migrator.BUNDLED_LATEST_VERSION
    db.close()
