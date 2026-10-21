"""Chart geometry, key notes and the sample household (the demo pass on every tab)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from starlette.testclient import TestClient

from lightning.demo import build_demo
from lightning.ui import charts, keynotes
from lightning.ui.web import create_app

D = Decimal


# ---------------------------------------------------------------- chart geometry

def test_a_trend_with_one_month_says_so_instead_of_drawing():
    assert charts.trend(["2026-09"], [{"name": "Money out", "tone": "spend", "values": [D(100)]}])["too_short"]
    assert charts.trend([], [])["too_short"]


def test_a_trend_starts_at_zero_and_marks_months_over_plan():
    t = charts.trend(["2026-07", "2026-08", "2026-09"],
                     [{"name": "Money out", "tone": "spend", "values": [D(800), D(1200), None]}], plan=D(1000))
    assert not t["too_short"]
    assert [tick["value"] for tick in t["ticks"]][-1] == 0 and t["ticks"][-1]["y"] == 100  # the axis starts at zero
    dots = t["series"][0]["dots"]
    assert [d["label"] for d in dots] == ["2026-07", "2026-08"]  # a missing month is not drawn as zero
    assert [d["over"] for d in dots] == [False, True]
    assert 0 < t["plan"]["y"] < 100 and t["series"][0]["last"]["value"] == D(1200)


def test_bars_are_largest_first_and_fold_the_rest():
    b = charts.bars([{"label": name, "value": D(value)} for name, value in
                     (("Food", 400), ("Rent", 1000), ("Fees", 15), ("Gifts", 200), ("Zero", 0))], limit=3)
    assert [r["label"] for r in b["rows"]] == ["Rent", "Food", "Gifts"]
    assert b["rows"][0]["width"] == 100 and b["rows"][1]["width"] == 40
    assert b["more"] == 1 and b["more_total"] == D(15)  # a zero row is left out, not counted


def test_grouped_bars_put_each_l2_under_its_l1():
    b = charts.grouped_bars([{"group": "Work", "label": "Software", "value": D(300)},
                             {"group": "Personal", "label": "Food", "value": D(400)},
                             {"group": "Personal", "label": "Rent", "value": D(1000)},
                             {"group": "Work", "label": "Travel", "value": D(50)}], limit=3)
    assert [(r.get("header", False), r["label"]) for r in b["rows"]] == [
        (True, "Personal"), (False, "Rent"), (False, "Food"), (True, "Work"), (False, "Software")]
    assert b["rows"][0]["value"] == D(1400) and b["rows"][1]["width"] == 100  # one scale across groups
    assert b["more"] == 1 and b["more_total"] == D(50)


def test_a_meter_over_plan_fills_and_says_so():
    over = charts.meter(D(90), D("67.50"))
    # Shown as "90 of 68", so it is 22 over, not 23 (22.50 rounded on its own).
    assert over["over"] and over["width"] == 100 and over["left"] == D("-22") and over["over_by"] == D(22)
    under = charts.meter(D(50), D(200))
    assert not under["over"] and under["width"] == 25 and under["left"] == D(150)
    assert charts.meter(D(10), None)["left"] is None


def test_class_tones_pick_the_most_specific_code():
    # One colour family per kind of asset; the fund version is a lighter shade of it.
    assert charts.class_tone("GOLD") == "gold" and charts.class_tone("FUND.GOLD") == "gold-fund"
    assert charts.class_tone("DEPOSIT.CD") == "deposits" and charts.class_tone("FUND.MONEY_MARKET") == "money-market"
    assert charts.class_tone("FUND.FIXED_INCOME") == "fixed-income"
    assert charts.class_tone("STOCK") == "equity" and charts.class_tone("FUND.EQUITY") == "equity-fund"
    assert charts.class_tone("CASH.BANK") == "cash" and charts.class_tone("FUND.OTHER") == "other-fund"
    assert charts.class_tone("CRYPTO") == "other"


def test_a_donut_keeps_the_largest_parts_in_class_order():
    slices = [{"label": "Stocks", "value": D(500), "tone": "equity"},
              {"label": "Cash", "value": D(100), "tone": "cash"},
              {"label": "Gold", "value": D(300), "tone": "gold"},
              {"label": "Deposits", "value": D(200), "tone": "deposits"},
              {"label": "Watch", "value": D(5), "tone": "other"},
              {"label": "Car", "value": D(4), "tone": "other"}]
    d = charts.donut(slices, limit=5)
    assert [s["label"] for s in d["segments"]] == ["Cash", "Deposits", "Gold", "Stocks", "Other"]
    assert d["segments"][-1]["value"] == D(9)  # the two smallest folded, the large equity slice kept
    assert d["total"] == D(1109)
    assert round(sum(s["share"] for s in d["segments"]), 6) == 100
    assert d["segments"][0]["offset"] == 25  # starts at 12 o'clock
    assert charts.donut([{"label": "Nothing", "value": D(0), "tone": "cash"}])["segments"] == []


# ---------------------------------------------------------------- key notes

def test_budget_notes_speak_plainly_about_the_days_left():
    assert keynotes.per_day(D(300), 10) == "About 30 a day for 10 days"
    assert keynotes.per_day(D(300), 1) == "Today is the last day of the month"
    assert keynotes.per_day(D(-5), 3) == "Spending passed the plan"
    assert keynotes.budget_left(D(300), 10, [], "#m") == []  # the Left in plan card already says it
    notes = keynotes.budget_left(D(-50), 0, ["Food", "Fuel", "Fees"], "#m")
    assert len(notes) == 1 and notes[0]["title"] == "Food, Fuel and 1 more over plan" and notes[0]["tone"] == "attention"
    assert keynotes.budget_left(D(-50), 0, [], "#m")[0]["title"] == "50 over plan this month"


def test_needs_you_leads_with_the_first_item_and_counts_the_rest():
    items = [{"label": "Bill due: Rent", "detail": "Due 2026-09-03", "href": "/plan", "action": "Mark paid", "popup": True},
             {"label": "Loan payment due: Car", "detail": "Due 2026-09-05", "href": "/plan"}]
    first = keynotes.needs_you(items, D(100), "2026-10-01")
    assert first["title"] == "Bill due: Rent and 1 more" and first["popup"] and first["tone"] == "attention"
    calm = keynotes.needs_you([], D(1500), "2026-10-01")
    assert calm["title"] == "1,500 safe to spend until 2026-10-01" and calm["tone"] == "info"


def test_loan_notes_answer_the_end_date():  # Recurring's share of income is its Fixed costs card now
    class Payment:
        amount, due_date = D(2500), "2026-10-05"
    progress = {"still_to_pay": D(52500), "last_date": "2028-06-05", "due": [], "paid": 3, "total": 24, "next": Payment()}
    loan = keynotes.loans_summary([{"progress": progress}])
    assert loan["title"] == "Paid off on 2028-06-05"
    assert loan["text"] == "3 of 24 payments made."  # the next payment is on the loan card
    due = keynotes.loans_summary([{"progress": {**progress, "due": [Payment()]}}])
    assert due["title"] == "1 loan payment due now" and due["tone"] == "attention"


def test_comparing_spending_with_the_month_before():
    assert keynotes.compared(D(900), D(1000), "2026-08")["title"] == "100 less than 2026-08"
    assert keynotes.compared(D(1100), D(1000), "2026-08")["tone"] == "attention"
    assert keynotes.compared(D(1100), None, "") is None


# ---------------------------------------------------------------- the sample household

@pytest.fixture
def demo(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    summary = build_demo(c)
    return c, summary


def test_the_demo_household_adds_up(demo):
    c, summary = demo
    assert summary == {"accounts": 6, "from": "2026-07-01", "to": "2026-09-30"}
    position = c.position.at(date(2026, 9, 30))
    assert position.holdings_value == D("177902.50")   # the 100,000 CD is a holding (owner decision 2026-10-04)
    assert position.held_for_others == D(10000)
    assert position.loans_still_to_pay == D(52500)  # 21 car-loan payments left
    assert position.net_worth == position.what_you_own - position.what_you_owe
    assert position.free_cash == position.cash_you_own - position.kept_apart - position.reserves - position.bills_due
    assert c.budgets.income_average("2026-09").amount == D(45000)
    assert c.budgets.has_plan("2026-09")
    assert position.reserves == D(20000)  # the emergency fund
    # Every recurring payment that went out is matched to its transaction: nothing is due.
    assert position.bills_due == 0


def test_the_demo_only_fills_an_empty_lightning(demo):
    c, _ = demo
    with pytest.raises(ValueError):
        build_demo(c)


def test_every_tab_of_the_demo_opens_with_its_key_notes(demo):
    c, _ = demo
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    with_notes = ["/", "/budget", "/birdview", "/birdview/expenses", "/investments", "/plan", "/plan/recurring",
                  "/plan/loans", "/plan/reserves"]
    for url in with_notes + ["/money-from-others", "/transactions", "/settings"]:
        page = client.get(url)
        assert page.status_code == 200, url
        if url in ("/", "/birdview"):  # Birdview redirects to the Overview
            assert page.text.count('class="stat-tile surface-') == 4, url  # four stat cards, no key notes
        elif url == "/birdview/expenses":  # four KPI cards give the gist of the period
            assert page.text.count('class="stat-tile surface-') == 4, url
        elif url == "/plan":  # safe to spend, free cash, what's due and the lowest point ahead, each compared (3.32)
            assert page.text.count('<article class="kpi-card') == 4 and "chart-waterfall" in page.text, url
            assert "timeline" in page.text and "section-tabs" in page.text, url
        elif url == "/budget":  # left in plan, everyday spending against pace, and what needs you (3.32)
            assert 2 <= page.text.count('<article class="kpi-card') <= 4 and 'class="key-note' not in page.text, url
        elif url == "/plan/recurring":  # its Fixed costs card says the share of income, once (UX plan 10)
            assert page.text.count('class="stat-tile surface-') == 1 and 'class="key-note' not in page.text, url
        elif url == "/investments":  # the period's waffle, result and six-month value line
            assert page.text.count('class="stat-tile surface-') == 3 and 'class="key-note' not in page.text, url
        elif url in with_notes:
            assert 'class="key-note' in page.text or 'class="stat-card key-note' in page.text, url
    overview = client.get("/").text
    assert "chart-donut" in overview and "chart-sankey-plot" in overview
    assert "chart-cfall-plot" not in overview  # the Net flow list says it; no column waterfall repeats it (UX plan 5)
    # No chart hides behind a toggle; only the one-row investment figures fold (Codex 2026-10-10), with their summary showing.
    assert "overview-month-toggle" not in overview
    assert "chart-trend" in client.get("/birdview").text  # month by month lives on Birdview


def test_the_demo_certificate_pays_what_its_rate_says_and_match_all_clears_it(demo):
    """3V1: the bought rate, the posted payouts and the payout day agree, so the one Needs-you item can be cleared."""
    from lightning.workflows.review import ReviewInbox
    c, _ = demo
    cd = next(a for a in c.accounts.list() if a.name == "NBE CDs")
    terms = c.deposits.list_certificates(cd.id)[0].terms
    monthly = (terms.principal * terms.annual_rate / 100 / 12).quantize(D("0.01"))
    payouts = [r for r in c.planning.repo.history("2026-07-01", "2026-09-30") if r["counterparty"] == "NBE"]
    assert len(payouts) == 2 and {r["amount"] for r in payouts} == {monthly}   # 22% of 100,000 over twelve
    assert {r["date"][8:] for r in payouts} == {terms.start_date[8:]}          # on the purchase's payout day
    day = date(2026, 9, 30)
    items = [i for i in ReviewInbox(c).items(day) if "interest payment" in i["label"]]
    assert len(items) == 1 and items[0]["post"]["label"] == "Match all suggested"
    result = c.deposit_receipts.confirm_suggested(cd.id, terms.id, "2026-09-30")
    assert result["matched"] == len(payouts)
    assert not [i for i in ReviewInbox(c).items(day) if "interest payment" in i["label"]]


def test_the_demo_has_an_untracked_subscription_for_looks_recurring(demo):
    """3V3: an early-month payment, three months running and not planned, always shows under Looks recurring."""
    c, _ = demo
    found = {s["name"]: s for s in c.planning.suggestions(date(2026, 9, 30))}
    assert "Fitness Time Gym" in found and found["Fitness Time Gym"]["amount"] == D("900.00")
    assert found["Fitness Time Gym"]["day"] == 4 and found["Fitness Time Gym"]["months"] == 3
    assert "Mom" in found  # a bill left untracked as well
    for early in ("2026-09-04", "2026-09-10"):  # from the 4th on, not only after the 25th
        assert any(s["name"] == "Fitness Time Gym" for s in c.planning.suggestions(date.fromisoformat(early)))


def test_the_welcome_button_adds_the_demo_only_once(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    added = client.post("/demo", follow_redirects=False)  # the route stays; the welcome page just no longer offers it
    assert added.status_code == 303 and "Sample+household+added" in added.headers["location"].replace("%20", "+")
    assert len(c.accounts.list()) == 6
    again = client.post("/demo", follow_redirects=False)
    assert again.status_code == 303 and len(c.accounts.list()) == 6


def test_welcome_screen_can_set_the_profile_currency_before_the_first_account(c):
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    page = client.get("/")
    assert 'action="/setup/currency"' in page.text and "USD — US Dollar" in page.text
    saved = client.post("/setup/currency", data={"currency": "USD"}, follow_redirects=False)
    assert saved.status_code == 303
    assert c.base_currency == "USD"


def test_setup_currency_registers_the_base_and_the_others_held(c):
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    before = client.get("/").text
    assert "Save your currencies first." in before and 'class="setup-row is-off"' in before
    assert 'href="/accounts/new?type=BANK"' not in before
    saved = client.post("/setup/currency", data={"currency": "EGP", "extra": ["USD", "EUR"]}, follow_redirects=False)
    assert saved.status_code == 303
    assert {row["code"] for row in c.currencies.list()} == {"EGP", "USD", "EUR"} and c.base_currency == "EGP"
    after = client.get("/").text
    assert "EGP · USD · EUR" in after or "EGP · EUR · USD" in after
    assert 'href="/accounts/new?type=BANK"' in after and "Save your currencies first." not in after


def test_the_account_form_lists_only_registered_currencies(c):
    c.currencies.register("USD")
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    page = client.get("/accounts/new").text
    assert '<datalist id="account-currencies">' not in page
    assert '<option value="USD" ' in page and '<option value="EGP" selected' in page and '<option value="GBP"' not in page


def test_the_demo_launcher_never_touches_another_database(tmp_path):
    from lightning.main import main
    real = tmp_path / "lightning.db"
    real.write_bytes(b"my real money")
    with pytest.raises(SystemExit):
        main(["--demo", "--db", str(real), "--no-browser"])
    assert real.read_bytes() == b"my real money"


def test_the_demo_reuses_an_investment_added_before_any_account(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    comi = c.assets.create_investment("CIB", "STOCK", "COMI")
    assert build_demo(c)["accounts"] == 6
    thndr = next(a for a in c.accounts.list() if a.name == "THNDR")
    assert c.investments.holding(thndr.id, comi.id, "2026-09-30") == 150  # the same COMI, not a second one


def test_the_spending_trend_follows_a_chosen_category(demo):
    from lightning.ui import visuals
    c, _ = demo
    food = visuals.spending_trend(c, date(2026, 9, 30), "EXP.PERSONAL.FOOD")
    assert food["series"][0]["values"] == [D("4568.50"), D("4762.80"), D("4671.15")]  # Carrefour + Seoudi
    personal = visuals.spending_trend(c, date(2026, 9, 30), "EXP.PERSONAL")
    assert all(v > 0 for v in personal["series"][0]["values"])
    assert personal["plan"] is None  # the dashed plan line is the whole month's plan, so only unfiltered
    everything = visuals.spending_trend(c, date(2026, 9, 30))
    assert everything["plan"]["value"] == c.budgets.month_view("2026-09").available


def test_a_month_is_only_over_plan_against_its_own_plan(demo):
    from lightning.ui import visuals
    c, _ = demo
    # The demo plans September only: July and August can't be "over plan", whatever they spent.
    t = visuals.spending_trend(c, date(2026, 9, 30))
    assert not c.budgets.has_plan("2026-07") and not c.budgets.has_plan("2026-08")
    over = {d["label"]: d["over"] for d in t["series"][0]["dots"]}
    assert over["2026-07"] is False and over["2026-08"] is False
    assert over["2026-09"] is (t["series"][0]["values"][-1] > t["plan"]["value"])


def test_money_added_lists_only_money_that_crossed_into_investments(demo):
    c, _ = demo
    rows = c.investments.report_transactions("flows", "2026-07-01", "2026-09-30")
    # The THNDR transfer and the ring bought from CIB; never groceries, rent or salary.
    assert all(r["type"] in ("TRF", "BUY", "SEL", "IN", "OUT", "ADJ") for r in rows)
    assert not any(r["counterparty"] in ("Carrefour", "Landlord", "ACME Egypt", "Talabat") for r in rows)
    report_new = sum(r["amount"] for r in rows if r["amount"] > 0)
    from lightning.investments.report import build_investment_report
    report = build_investment_report(c.db, c.accounts, c.assets, c.reporting, "2026-07-01", "2026-09-30")
    assert report_new == report["new_money"]  # the list adds up to the figure


def test_target_allocation_says_how_much_to_invest(demo):
    from lightning.investments.report import allocation_plan
    plan = allocation_plan({"Gold": D(600), "Stocks": D(400)}, {"Gold": D(50), "Stocks": D(40)}, ["Gold", "Stocks", "Money Market Fund"])
    gold, stocks, money_market = plan["rows"]  # every class, heaviest first
    # Sell 200 of gold alone: 400 of 800 left is 50%, with stocks untouched.
    assert gold["current"] == 60 and gold["difference"] == -10 and gold["adjust"] == -200
    assert stocks["adjust"] == 0 and plan["required"] == 90 and not plan["complete"]
    assert money_market["name"] == "Money Market Fund" and money_market["target"] is None
    c, _ = demo
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    saved = client.post("/investments/targets", data={"bucket": "Gold", "target_weight": "40"}, headers={"X-Requested-With": "fetch"})
    assert saved.status_code == 204  # saved in place, no page load
    fragment = client.get("/investments/targets?fragment=1").text
    assert "Value to adjust" in fragment and "<html" not in fragment
    assert "Add a class" not in fragment and "pts" not in fragment and 'class="info-tip"' in fragment
    too_much = client.post("/investments/targets", data={"bucket": "Stocks", "target_weight": "70"}, headers={"X-Requested-With": "fetch"})
    assert too_much.status_code == 400 and "up to 60%" in too_much.text  # Gold already takes 40%
    cleared = client.post("/investments/targets", data={"bucket": "Gold", "target_weight": ""}, headers={"X-Requested-With": "fetch"})
    assert cleared.status_code == 204 and "Gold" not in c.investments.target_weights()
    assert "Target allocation" in client.get("/settings?section=targets").text


def test_the_planner_remembers_how_to_split_new_money(demo):
    c, _ = demo
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    for name, weight in (("Gold", "40"), ("Stocks", "40"), ("Money Market Fund", "20")):
        client.post("/investments/targets", data={"bucket": name, "target_weight": weight}, headers={"X-Requested-With": "fetch"})
    assert sum(c.investments.target_weights().values()) == 100
    page = client.get("/investments/planner").text
    assert 'value="prorata" checked' in page and "same share of its gap" in page
    page = client.post("/investments/planner", data={"amount": "5000", "mode": "fill_gaps"}).text
    assert 'value="fill_gaps" checked' in page and "furthest below its target" in page
    assert c.settings.get("investment_planner_mode") == "fill_gaps"
    assert 'value="fill_gaps" checked' in client.get("/investments/planner").text  # remembered
    client.post("/investments/planner", data={"amount": "5000", "mode": "nonsense"})
    assert c.settings.get("investment_planner_mode") == "fill_gaps"


def test_visuals_and_breakdowns_add_up(demo):
    from lightning.ui import visuals
    c, _ = demo
    first, last = date(2026, 9, 1), date(2026, 9, 30)
    trend = visuals.net_worth_trend(c, last)
    assert [lab["text"] for lab in trend["labels"]] == ["2026-07", "2026-08", "2026-09"]
    assert trend["series"][0]["values"][-1] == c.position.at(last).net_worth  # the same figure as the card
    steps = visuals.free_cash_steps(c.position.at(last))
    assert [r["kind"] for r in steps["rows"]] == ["total", "down", "down", "down", "end"]  # kept apart, reserves, bills
    assert steps["rows"][-1]["value"] == c.position.at(last).free_cash
    out = c.reporting.cash_flow(first, last).outflows
    assert sum(v for _, v in c.reporting.spending_by_counterparty(first, last)) == out  # who you paid
    assert sum(v for _, v in c.reporting.spending_by_account(first, last)) == out  # paid from
    usual = {r["label"].split(" › ")[-1]: r for r in c.reporting.spending_vs_usual(first, last)}
    food = usual["Food & Groceries"]
    assert food["usual"] == (D("4568.50") + D("4762.80")) / 2 and food["change"] == D("5.50")
    assert c.reporting.largest_payments(first, last, 1)[0]["counterparty"] == "Landlord"


def test_expense_analysis_compares_big_categories_with_their_usual_month(c, setup, monkeypatch):
    from datetime import date
    from lightning.ui import visuals
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-12-31")
    accounts, cats = setup
    cib = accounts["cib"].id
    housing = c.categories.get_by_code("EXP.PERSONAL.HOUSING").id
    fees = c.categories.get_by_code("EXP.PERSONAL.FEES").id
    c.transactions.record_inflow("2026-09-02", cib, "40000", cats["EXP.WORK.SALARY"].id)
    for month, rent in (("2026-09", "10000"), ("2026-10", "10000"), ("2026-11", "11000"), ("2026-12", "15000")):
        c.transactions.record_outflow(f"{month}-05", cib, rent, housing)
        c.transactions.record_outflow(f"{month}-06", cib, "1000", cats["EXP.PERSONAL.FOOD"].id)
    c.transactions.record_outflow("2026-12-07", cib, "20", fees)  # under 1%: folded away
    a = visuals.expense_analysis(c, date(2026, 12, 1), date(2026, 12, 31))
    names = [r["name"] for r in a["rows"]]
    assert names == ["Housing & Rent", "Food & Groceries", "Other"] and a["small"] == D("20")  # under 1% folds into Other
    housing_row = a["rows"][0]
    assert housing_row["usual"] == D("31000") / 3 and housing_row["above"]  # 15,000 beats its 10–11k range
    assert (housing_row["low"], housing_row["high"]) == (D("10000"), D("11000"))
    assert [t["label"] for t in a["tiles"]][-1] == "Other"
    assert len(a["heat"][0]["cells"]) == len(a["heat_keys"]) and a["heat"][0]["cells"][-1]["step"] == 3  # 1.3× its own average
    page = TestClient(create_app(c)).get("/birdview/expenses?period=month&month=2026-12").text
    assert [r["name"] for r in a["flow_heat"]] == ["Money in", "Money out", "Net flow"]
    for question in ("Where did it go?", "Is this period unusual?", "How each one moved", "Day by day"):
        assert question in page
    assert "Net cash flow" not in page  # feedback ticket 85: by month on the Overview, not by day here
    assert page.count('class="stat-tile surface-') == 4
    # Every usual-range bar is the same size: the pill runs 8% to 92%, and above its range sits past it.
    assert (housing_row["range"]["low"], housing_row["range"]["high"]) == (8.0, 92.0) and housing_row["range"]["now"] > 92
    # The day calendar: one month, the rent day darkest, no category rows and no outlined month.
    days = visuals.day_calendars(c, date(2026, 12, 1), date(2026, 12, 31))
    cells = {d["date"]: d for w in days["months"][0]["weeks"] for d in w if d}
    assert days["single"] and len(cells) == 31 and days["busiest"] == ("2026-12-05", D(15000))
    assert cells["2026-12-05"]["spend_step"] == 4 and cells["2026-12-05"]["net_tone"] == "out" and cells["2026-12-01"]["spend_step"] == 0
    assert days["weekdays"][0] == "Sat" and "is-now" not in page and "cal-day heat-4" in page


def test_flows_by_date_add_up_to_the_period_cash_flow(demo):
    c, _ = demo
    by_day = c.reporting.flows_by_date("2026-07-01", "2026-09-30")
    by_month = c.reporting.flows_by_date("2026-07-01", "2026-09-30", "month")
    flow = c.reporting.cash_flow("2026-07-01", "2026-09-30")
    for rows in (by_day, by_month):
        assert sum(r["inflows"] for r in rows.values()) == flow.inflows
        assert sum(r["outflows"] for r in rows.values()) == flow.outflows
        assert sum(r["net"] for r in rows.values()) == flow.net
    assert set(by_month) == {"2026-07", "2026-08", "2026-09"}


def test_the_overview_ends_with_a_calendar_of_months(demo, monkeypatch):
    from lightning.ui import visuals
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-02")
    c, _ = demo
    cal = visuals.month_calendar(c, date(2026, 10, 2))
    year = cal["years"][0]
    assert [r["year"] for r in cal["years"]] == [2026] and len(year["cells"]) == 12
    assert [x["known"] for x in year["cells"]] == [False] * 6 + [True] * 4 + [False] * 2  # July to today
    assert cal["count"] == 4 and sum(x["net"] for x in year["cells"][6:9]) == c.reporting.cash_flow("2026-07-01", "2026-09-30").net
    page = TestClient(create_app(c), base_url="http://127.0.0.1").get("/").text
    assert "Month by month" in page and page.index("Month by month") > page.index("Where money in went")


def test_setup_guide_can_be_dismissed_and_shown_again_without_changing_accounts(c, setup):
    client = TestClient(create_app(c))
    account_ids = [a.id for a in c.accounts.list()]
    assert "Get set up" in client.get("/").text
    saved = client.post("/setup/guide", data={"action": "dismiss"})
    assert saved.status_code == 200 and "Get set up" not in saved.text
    assert c.settings.get("setup_guide_dismissed") == "1"
    assert "Show setup guide" in client.get("/settings").text
    shown = client.post("/setup/guide", data={"action": "show"})
    assert shown.status_code == 200 and "Get set up" in shown.text
    assert [a.id for a in c.accounts.list()] == account_ids


def test_the_welcome_page_offers_four_sample_boxes_and_nothing_else(c):
    import re
    page = TestClient(create_app(c), base_url="http://127.0.0.1").get("/").text
    forms = re.findall(r'<form method="post" action="(/sample/[^"]+)"', page)
    assert forms == ["/sample/mohab-2026", "/sample/amr", "/sample/menna", "/sample/fatma"]
    assert 'action="/demo"' not in page and "Just looking?" not in page and "abdelrahman" not in page
    assert "/samples/mohab-2026/" not in page  # no CSV download links
    assert "Samples fill this profile" in page or "--demo" in page
