from lightning.ui.web import create_app
from tests.screens import _ScreenClient, said, visible_text


def test_financial_health_page_is_directly_reachable_and_shows_missing_values(c, monkeypatch):
    def no_matching(_day):
        raise AssertionError("reading Health must not settle scheduled payments")

    monkeypatch.setattr(c.planning, "match_payments", no_matching)
    browser = _ScreenClient(create_app(c), "http://testserver")
    response = browser.get("/financial-health")
    assert response.status_code == 200
    assert "Financial health" in response.text
    assert "Against your limits" in response.text
    assert "Debt and monthly commitments" in response.text
    assert "Over time" in response.text
    assert "Net worth" in response.text
    # Feedback ticket 87: each limit is one row that opens its numbers; Over time comes before the limits.
    assert response.text.count('<details class="health-row-wrap">') >= 6 and "See details" in response.text
    assert response.text.index("Over time") < response.text.index("Against your limits")
    assert "Unavailable" in visible_text(response.text)
    assert 'href="/financial-health"' in response.text


def test_health_settings_save_and_restore_a_profile_limit(c):
    browser = _ScreenClient(create_app(c), "http://testserver")
    response = browser.get("/settings?section=financial-health")
    assert response.status_code == 200
    assert "At least 6 months" in response.text
    assert "Emergency fund" in response.text
    saved = browser.post("/settings/financial-health-limit", data={"key": "savings_rate", "value": "25"})
    assert saved.status_code == 200
    assert c.health.limit_values()["savings_rate"] == 25
    reset = browser.post("/settings/financial-health-limit", data={"key": "savings_rate", "action": "reset"})
    assert reset.status_code == 200
    assert c.health.limit_values()["savings_rate"] == 20


def test_emergency_health_limit_is_read_only_and_matches_reserves(c):
    browser = _ScreenClient(create_app(c), "http://testserver")
    settings = browser.get("/settings?section=financial-health").text
    health = browser.get("/financial-health").text
    assert "At least 6 months" in settings
    assert "At least 6 months" in health
    assert 'name="key" value="emergency_fund"' not in settings
    assert 'href="/plan/reserves"' in settings


def test_as_of_date_is_validated_and_rendered(c):
    browser = _ScreenClient(create_app(c), "http://testserver")
    response = browser.get("/financial-health?as_of=2026-09-15")
    assert response.status_code == 200
    assert said("Balances as of <bdi dir=\"ltr\">2026-09-15</bdi>") in response.text
    future = browser.get("/financial-health?as_of=2027-01-01")
    assert future.status_code == 200
    assert "Choose today or an earlier as-of date" in visible_text(future.text)


def test_a_month_with_far_more_out_than_in_is_said_in_words(c, setup):
    # November: 1,000 in, 5,000 out (the pay came in October). A rate of −400% says nothing: the card and the
    # six-month table say the gap as the Overview does, and the card still says it missed the limit.
    accounts, cats = setup
    cib = accounts["cib"].id
    c.transactions.record_inflow("2026-11-15", cib, "1,000", cats["EXP.WORK.SALARY"].id)
    c.transactions.record_outflow("2026-11-20", cib, "5,000", cats["EXP.PERSONAL.FOOD"].id)
    page = visible_text(_ScreenClient(create_app(c), "http://testserver").get("/financial-health").text)
    assert said("Savings rate — Needs you 4,000 more went out than the 1,000 that came in 2026-11") in page
    assert said("2026-11 4,000 more went out than the 1,000 that came in") in page
    assert "-400" not in page


def test_health_trend_includes_zero_and_does_not_join_missing_months():
    from decimal import Decimal as D
    from lightning.ui.routes.financial_health import _health_trend

    months = [f'2026-0{i}' for i in range(1, 7)]
    chart = _health_trend(months, [D('30'), D('32'), None, D('35'), D('36'), D('37')], 'Savings rate', 'in')
    assert not chart['too_short'] and any(t['value'] == 0 for t in chart['ticks'])
    assert len(chart['runs']) == 2
    assert [len(run["line"].split()) for run in chart['runs']] == [2, 3]
    assert all(run["area"].endswith(",100.00 Z") for run in chart["runs"])
    assert _health_trend(months, [None, D('30'), None, D('35'), None, None], 'Savings rate', 'in')['too_short']
    negative = _health_trend(months, [D('-5'), D('0'), D('5'), None, None, None], 'Savings rate', 'in')
    assert min(t['value'] for t in negative['ticks']) < 0 < max(t['value'] for t in negative['ticks'])
    assert any(t['value'] == 0 for t in negative['ticks'])


def test_pc_savings_chart_has_zero_axis_and_percent_labels(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-12-15')
    accounts, cats = setup
    for month in ('09', '10', '11'):
        c.transactions.record_inflow(f'2026-{month}-05', accounts['cib'].id, '1000', cats['EXP.WORK.SALARY'].id)
        c.transactions.record_outflow(f'2026-{month}-06', accounts['cib'].id, '500', cats['EXP.PERSONAL.FOOD'].id)
    page = _ScreenClient(create_app(c), 'http://testserver').get('/financial-health').text
    chart = page.split('<figure class="chart chart-trend"', 1)[1].split('</figure>', 1)[0]
    assert 'chart-grid-zero' in chart and '0.0%' in chart
    assert '50.0%' in chart and 'class="chart-line tone-in"' in chart
