"""NF-12S: a flexible category whose pace passes its limit before the month ends is one row in Needs you, with Move
room and Raise; it is gone when back on pace or snoozed. NF-12AL2: only the flexible part (the limit less the month's
bills) is paced, against the category's own share-by-day curve when two of the last three months had spending; with
less history the row says "may"."""
from datetime import date
from decimal import Decimal

from lightning.workflows.review import ReviewInbox


def _needs(c, on):
    """Needs you's rows and Budget's What changed rows (NF-12AL3): plan changes moved to Budget's card."""
    inbox = ReviewInbox(c)
    return [*inbox.items(on), *inbox.changes(on)]

MONTH = "2026-12"
DAY = date(2026, 12, 10)  # ten days gone of 31


def _ids(c):
    return (c.categories.get_by_code("EXP.PERSONAL.FOOD").id, c.categories.get_by_code("EXP.PERSONAL.TRANSPORT").id)


def _plan(c, setup, food_spent="1500"):
    accounts, _ = setup
    food, transport = _ids(c)
    s = c.schedules.view()
    c.budgets.set_budget(food, MONTH, "3000", schedule=s)
    c.budgets.set_budget(transport, MONTH, "2000", schedule=s)
    c.transactions.record_outflow("2026-12-04", accounts["cib"].id, food_spent, food)
    c.transactions.record_outflow("2026-12-04", accounts["cib"].id, "100", transport)
    return food, transport


def test_ahead_of_pace_names_the_day_and_a_category_to_move_from(c, setup):
    food, transport = _plan(c, setup)
    [row] = c.budgets.running_out(MONTH, DAY, schedule=c.schedules.view())
    assert (row["category_id"], row["day"], row["limit"]) == (food, 20, Decimal("3000"))
    assert row["amount"] == Decimal("1650") and row["can_move"] and row["from_id"] == transport
    # No earlier months: the straight line, so "may" (NF-12AL2).
    item = {i["label"]: i for i in _needs(c, DAY)}["Food & groceries may run out around the 20th"]
    assert "too little history" in item["detail"]
    assert item["action"] == "Move room" and item["href"].startswith(f"/budget/move?month={MONTH}&to={food}&from={transport}")
    assert item["alt"]["label"] == "Raise"


def test_on_pace_early_in_the_month_and_over_already_say_nothing(c, setup):
    _plan(c, setup, food_spent="900")  # 900 / 10 x 31 = 2,790, inside 3,000
    assert c.budgets.running_out(MONTH, DAY, schedule=c.schedules.view()) == []
    _plan(c, setup, food_spent="1500")
    assert c.budgets.running_out(MONTH, date(2026, 12, 5), schedule=c.schedules.view()) == []  # after day 5 only
    assert c.budgets.running_out(MONTH, date(2027, 1, 10), schedule=c.schedules.view()) == []  # not this month


def test_a_category_with_bills_paces_its_flexible_part(c, setup):
    # NF-12AL2 replaces "bills are never paced": a bill no longer turns pacing off, it comes off the limit.
    food, _ = _plan(c, setup)
    c.planning.create(kind="BILL", name="Groceries club", amount="200", frequency="MONTHLY",
                      start_date="2026-12-20", category_id=food)
    [row] = c.budgets.running_out(MONTH, DAY, schedule=c.schedules.view())
    # 1,500 / 10 x 31 = 4,650 against the flexible 2,800: 1,850 short, out on day 19 (1,500 x 19 / 10 >= 2,800).
    assert (row["category_id"], row["limit"], row["bills"], row["day"], row["amount"]) == (
        food, Decimal("2800"), Decimal("200"), 19, Decimal("1850"))


def test_snoozed_row_leaves_needs_you_and_without_a_donor_it_offers_only_raise(c, setup):
    food, transport = _plan(c, setup)
    c.budgets.set_budget(transport, MONTH, "1000", schedule=c.schedules.view())
    inbox = ReviewInbox(c)
    [item] = [i for i in _needs(c, DAY) if "run out" in i["label"]]
    assert item["action"] == "Raise" and "alt" not in item and f"limit-{food}" in item["href"]
    inbox.decide(item["review_id"], "snoozed", DAY, "2026-12-20")
    assert not [i for i in _needs(c, DAY) if "run out" in i["label"]]


def test_move_dialog_says_why_from_the_evidence_not_two_months(c, setup, monkeypatch):
    # #626: a pace offer's Move room dialog said "over its plan two months running" with no such history.
    from tests.screens import _ScreenClient, visible_text
    from lightning.ui.web import create_app
    food, transport = _plan(c, setup)
    monkeypatch.setenv("LIGHTNING_TODAY", DAY.isoformat())
    browser = _ScreenClient(create_app(c), "http://testserver")
    href = f"/budget/move?month={MONTH}&to={food}&from={transport}&amount=1650"
    text = visible_text(browser.get(href).text)
    assert "two months running" not in text
    assert "At this pace Food & groceries passes its plan before the month ends; Transportation has room left." in text
    c.transactions.record_outflow("2026-12-09", setup[0]["cib"].id, "2000", food)  # now over: 3,500 of 3,000
    text = visible_text(browser.get(href).text)
    assert "Food & groceries is over its plan this month; Transportation has room left." in text
    assert "two months running" not in text


def test_money_out_by_day_matches_the_month_total(c, setup):
    # NF-12AL2: the share-by-day curve reads spending by day, counted the way the month total counts it.
    accounts, _ = setup
    food, _ = _ids(c)
    for day, amount in (("2026-11-02", "800"), ("2026-11-02", "200"), ("2026-11-20", "500")):
        c.transactions.record_outflow(day, accounts["cib"].id, amount, food)
    by_day = c.reporting.money_out_by_category_by_day("2026-11-01", "2026-11-30")
    assert by_day["2026-11-02"][food] == Decimal("1000") and by_day["2026-11-20"][food] == Decimal("500")
    total = c.reporting.money_out_by_category("2026-11-01", "2026-11-30")[food]
    assert sum(day.get(food, 0) for day in by_day.values()) == total


def _front_loaded(c, setup, months=("2026-10", "2026-11")):
    """#626: a big shop on the 2nd and a top-up on the 20th, in each of these earlier months."""
    accounts, _ = setup
    food, _ = _ids(c)
    for month in months:
        c.transactions.record_outflow(f"{month}-02", accounts["cib"].id, "2400", food)
        c.transactions.record_outflow(f"{month}-20", accounts["cib"].id, "500", food)


def test_front_loaded_shopper_with_that_history_is_on_their_own_curve(c, setup):
    # #626: 2,400 on the 2nd against 3,000. Two earlier months spent 2,400 of 2,900 by the 2nd, so 83% by day 10 is
    # their usual pace: no day-8 warning.
    _front_loaded(c, setup)
    _plan(c, setup, food_spent="2400")
    assert c.budgets.running_out(MONTH, DAY, schedule=c.schedules.view()) == []
    assert not [i for i in _needs(c, DAY) if "run out" in i["label"]]


def test_past_their_own_curve_by_more_than_ten_percent_will_run_out(c, setup):
    food, _ = _ids(c)
    _front_loaded(c, setup)
    _plan(c, setup, food_spent="2400")
    c.transactions.record_outflow("2026-12-08", setup[0]["cib"].id, "600", food)  # 3,000 by day 10: 517 past the curve
    [row] = c.budgets.running_out(MONTH, DAY, schedule=c.schedules.view())
    assert row["category_id"] == food and not row["may"] and row["amount"] == Decimal("650")
    assert [i for i in _needs(c, DAY) if i["label"].startswith("Food & groceries will run out")]


def test_same_spend_without_history_says_may(c, setup):
    # #626's spend with one earlier month only: not enough for a curve, so the straight line, and "may".
    _front_loaded(c, setup, months=("2026-11",))
    food, _ = _plan(c, setup, food_spent="2400")
    [row] = c.budgets.running_out(MONTH, DAY, schedule=c.schedules.view())
    assert (row["category_id"], row["may"], row["day"]) == (food, True, 13)  # 2,400 x 13 / 10 >= 3,000
    labels = [i["label"] for i in _needs(c, DAY)]
    assert "Food & groceries may run out around the 13th" in labels


def test_a_100_bill_paces_the_flexible_2900(c, setup):
    # #626: adding a 100 bill turned pacing off for the whole category; now the other 2,900 is paced.
    food, _ = _plan(c, setup, food_spent="2400")
    c.planning.create(kind="BILL", name="Water", amount="100", frequency="MONTHLY",
                      start_date="2026-12-20", category_id=food)
    [row] = c.budgets.running_out(MONTH, DAY, schedule=c.schedules.view())
    assert (row["category_id"], row["limit"], row["bills"]) == (food, Decimal("2900"), Decimal("100"))
    [item] = [i for i in _needs(c, DAY) if "run out" in i["label"]]
    assert "passes the 2,900 EGP left after bills" in item["detail"]


def test_the_may_row_reads_in_arabic(c, setup):
    # NF-12AL2: the label, the bills sentence and the history sentence are all Arabic, each sentence on its own.
    import re
    from lightning.ui.i18n import translate
    food, _ = _plan(c, setup, food_spent="2400")
    c.planning.create(kind="BILL", name="Water", amount="100", frequency="MONTHLY",
                      start_date="2026-12-20", category_id=food)
    [item] = [i for i in _needs(c, DAY) if "run out" in i["label"]]
    assert translate(item["label"], "ar") == "الأكل والبقالة ممكن يخلص حوالي يوم 13"
    detail = translate(item["detail"], "ar")
    assert "لسه مفيش تاريخ كفاية" in detail and "بعد الفواتير" in detail and "محتاج حوالي" in detail
    assert not re.search(r"[A-Za-z]{2,}", detail.replace("EGP", ""))
